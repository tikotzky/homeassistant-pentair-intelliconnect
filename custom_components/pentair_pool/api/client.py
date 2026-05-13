"""
API Client for Pentair Cloud.

Implements the auth chain captured from the official Android app:

    Cognito SRP login -> ID/access/refresh tokens
        -> Cognito Identity (GetId + GetCredentialsForIdentity) -> STS creds
            -> SigV4-signed REST calls to api.pentair.cloud
            -> Bearer-style WebSocket to g44t970cbi.execute-api...

The blueprint's class names (`PentairPoolApiClient`, the three exception
types) are preserved so the rest of the integration's wiring stays the
same as in the template.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import aiohttp

from custom_components.pentair_pool.const import (
    API_BASE,
    API_KEY_UNAUTH,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    COGNITO_USER_POOL_ID,
    DETECT_USER_URL,
    IDENTITY_POOL_ID,
    TOKEN_REFRESH_MARGIN_SECONDS,
    WS_URL,
)

_LOGGER = logging.getLogger(__name__)

COGNITO_IDP_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
COGNITO_IDENTITY_URL = f"https://cognito-identity.{COGNITO_REGION}.amazonaws.com/"
LOGINS_KEY = f"cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"


class PentairPoolApiClientError(Exception):
    """Base exception for any Pentair Cloud API failure."""


class PentairPoolApiClientCommunicationError(PentairPoolApiClientError):
    """Network/timeout error talking to Pentair Cloud."""


class PentairPoolApiClientAuthenticationError(PentairPoolApiClientError):
    """Authentication failure (bad password, expired refresh token, etc.)."""


async def async_detect_user(session: aiohttp.ClientSession, email: str) -> dict[str, Any]:
    """
    Pre-auth probe -- does this email own a Pentair account?

    Returns the parsed `response` object so callers can read `.get("userExists")`.
    """
    try:
        async with session.post(
            DETECT_USER_URL,
            headers={"x-api-key": API_KEY_UNAUTH, "Content-Type": "application/json"},
            data=json.dumps({"email": email}),
        ) as resp:
            resp.raise_for_status()
            return (await resp.json()).get("response", {})
    except (TimeoutError, aiohttp.ClientError) as err:
        raise PentairPoolApiClientCommunicationError(f"detectUser failed: {err}") from err


class PentairPoolApiClient:
    """
    Async API client + token manager.

    Construction is cheap; the heavy work happens in `async_login()` (called
    from the coordinator/config flow's first refresh). Subsequent calls
    transparently refresh tokens before each signed request.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize with credentials from the config flow."""
        self._username = username
        self._password = password
        self._session = session

        # Populated by async_login() / refresh.
        self._id_token: str | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._id_token_expiry: float = 0.0

        self._sts_ak: str | None = None
        self._sts_sk: str | None = None
        self._sts_st: str | None = None
        self._sts_expiry: float = 0.0

        self._cognito_sub: str | None = None
        self._refresh_lock = asyncio.Lock()

    # ----------------------------------------------------------------- tokens

    async def async_login(self) -> None:
        """Run SRP_AUTH end-to-end and mint STS credentials.

        pycognito's SRP helper is synchronous; offload to a thread.
        """
        from pycognito.aws_srp import AWSSRP  # noqa: PLC0415

        def _srp_authenticate() -> dict[str, Any]:
            srp = AWSSRP(
                username=self._username,
                password=self._password,
                pool_id=COGNITO_USER_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                pool_region=COGNITO_REGION,
            )
            return srp.authenticate_user()

        try:
            tokens = await asyncio.to_thread(_srp_authenticate)
        except Exception as err:  # noqa: BLE001
            # pycognito raises botocore's NotAuthorizedException for bad creds.
            raise PentairPoolApiClientAuthenticationError(str(err)) from err

        auth_result = tokens["AuthenticationResult"]
        self._id_token = auth_result["IdToken"]
        self._access_token = auth_result["AccessToken"]
        self._refresh_token = auth_result["RefreshToken"]
        self._id_token_expiry = time.time() + auth_result["ExpiresIn"] - TOKEN_REFRESH_MARGIN_SECONDS
        self._cognito_sub = self._decode_jwt_sub(self._id_token)

        await self._refresh_sts_creds()

    async def _refresh_id_token(self) -> None:
        """Use the refresh token to mint a fresh ID/access token."""
        body = {
            "AuthFlow": "REFRESH_TOKEN_AUTH",
            "ClientId": COGNITO_CLIENT_ID,
            "AuthParameters": {"REFRESH_TOKEN": self._refresh_token},
        }
        async with self._session.post(
            COGNITO_IDP_URL,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
            data=json.dumps(body),
        ) as resp:
            if resp.status != 200:  # noqa: PLR2004
                text = await resp.text()
                raise PentairPoolApiClientAuthenticationError(f"REFRESH_TOKEN_AUTH failed: {resp.status} {text}")
            # Cognito returns Content-Type: application/x-amz-json-1.1, which aiohttp
            # refuses by default — content_type=None disables the MIME guard.
            data = await resp.json(content_type=None)
        ar = data["AuthenticationResult"]
        self._id_token = ar["IdToken"]
        self._access_token = ar["AccessToken"]
        self._id_token_expiry = time.time() + ar["ExpiresIn"] - TOKEN_REFRESH_MARGIN_SECONDS

    async def _refresh_sts_creds(self) -> None:
        """Trade the Cognito ID token for AWS STS credentials."""
        try:
            async with self._session.post(
                COGNITO_IDENTITY_URL,
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": "AWSCognitoIdentityService.GetId",
                },
                data=json.dumps({"IdentityPoolId": IDENTITY_POOL_ID, "Logins": {LOGINS_KEY: self._id_token}}),
            ) as resp:
                if resp.status != 200:  # noqa: PLR2004
                    raise PentairPoolApiClientAuthenticationError(
                        f"Cognito GetId failed: {resp.status} {await resp.text()}",
                    )
                identity_id = (await resp.json(content_type=None))["IdentityId"]

            async with self._session.post(
                COGNITO_IDENTITY_URL,
                headers={
                    "Content-Type": "application/x-amz-json-1.1",
                    "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
                },
                data=json.dumps({"IdentityId": identity_id, "Logins": {LOGINS_KEY: self._id_token}}),
            ) as resp:
                if resp.status != 200:  # noqa: PLR2004
                    raise PentairPoolApiClientAuthenticationError(
                        f"GetCredentialsForIdentity failed: {resp.status} {await resp.text()}",
                    )
                data = await resp.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise PentairPoolApiClientCommunicationError(str(err)) from err

        creds = data["Credentials"]
        self._sts_ak = creds["AccessKeyId"]
        self._sts_sk = creds["SecretKey"]
        self._sts_st = creds["SessionToken"]
        self._sts_expiry = float(creds["Expiration"]) - TOKEN_REFRESH_MARGIN_SECONDS

    async def async_ensure_fresh(self) -> None:
        """Refresh tokens / STS creds if either is close to expiring."""
        now = time.time()
        if now < self._id_token_expiry and now < self._sts_expiry:
            return
        async with self._refresh_lock:
            now = time.time()
            if now >= self._id_token_expiry:
                _LOGGER.debug("Refreshing Cognito tokens")
                await self._refresh_id_token()
            if now >= self._sts_expiry:
                _LOGGER.debug("Refreshing STS credentials")
                await self._refresh_sts_creds()

    # ------------------------------------------------------------------ SigV4

    def _sigv4_headers(
        self,
        method: str,
        url: str,
        body: bytes,
        *,
        x_pha_apptype: str = "pool",
    ) -> dict[str, str]:
        """Build the unusual signed-header set Pentair Cloud expects.

        Signed headers (verbatim from a captured request):

            host;iseuropeanuser;x-amz-date;x-amz-id-token;x-amz-security-token;x-pha-apptype

        Notable departures from boto3 defaults: content-type/content-length are
        NOT signed, and `iseuropeanuser` + `x-pha-apptype` ARE signed.
        """
        parsed = urlparse(url)
        host = parsed.netloc
        canonical_uri = parsed.path or "/"
        canonical_qs = parsed.query

        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        headers = {
            "host": host,
            "iseuropeanuser": "false",
            "x-amz-date": amz_date,
            "x-amz-id-token": self._id_token or "",
            "x-amz-security-token": self._sts_st or "",
            "x-pha-apptype": x_pha_apptype,
        }
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
        payload_hash = hashlib.sha256(body).hexdigest()

        canonical_request = "\n".join(
            [method.upper(), canonical_uri, canonical_qs, canonical_headers, signed_headers, payload_hash],
        )

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{COGNITO_REGION}/execute-api/aws4_request"
        string_to_sign = "\n".join(
            [algorithm, amz_date, credential_scope, hashlib.sha256(canonical_request.encode()).hexdigest()],
        )

        def _mac(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        k_date = _mac(("AWS4" + (self._sts_sk or "")).encode(), date_stamp)
        k_region = _mac(k_date, COGNITO_REGION)
        k_service = _mac(k_region, "execute-api")
        k_signing = _mac(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

        authorization = (
            f"{algorithm} Credential={self._sts_ak}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {**headers, "Authorization": authorization}

    # ------------------------------------------------------------------- REST

    async def _request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        *,
        x_pha_apptype: str = "pool",
    ) -> dict:
        await self.async_ensure_fresh()
        url = f"{API_BASE}{path}"
        body_bytes = b"" if body is None else json.dumps(body).encode()
        headers = self._sigv4_headers(method, url, body_bytes, x_pha_apptype=x_pha_apptype)
        if body is not None:
            headers["Content-Type"] = "application/json; charset=UTF-8"
        try:
            async with self._session.request(method, url, headers=headers, data=body_bytes) as resp:
                text = await resp.text()
                if resp.status in (401, 403):
                    raise PentairPoolApiClientAuthenticationError(f"{method} {path} -> {resp.status}: {text}")
                if resp.status >= 400:  # noqa: PLR2004
                    raise PentairPoolApiClientError(f"{method} {path} -> {resp.status}: {text}")
                return json.loads(text) if text else {}
        except (TimeoutError, aiohttp.ClientError) as err:
            raise PentairPoolApiClientCommunicationError(str(err)) from err

    async def async_list_devices(self) -> dict:
        """`GET /device2/.../listdevices` -- top-level device list."""
        return await self._request("GET", "/device2/device2-service/user/listdevices")

    async def async_get_device(self, device_id: str) -> dict:
        """`POST /device2/.../device` -- full state snapshot for one device.

        Body shape is `{"deviceIds": [<id>]}` (plural, list) — matches the
        captured Android-app body verbatim. A singular `{"deviceId": id}`
        request gets a `200 OK` with `response.data: []`.
        """
        return await self._request(
            "POST",
            "/device2/device2-service/user/device",
            body={"deviceIds": [device_id]},
        )

    async def async_set_fields(self, device_id: str, payload: dict[str, Any]) -> dict:
        """Send one or more `<field>: <value>` writes.

        The Pentair API accepts only strings, so values are stringified here.
        """
        body = {"payload": {k: str(v) for k, v in payload.items()}}
        return await self._request(
            "PUT",
            f"/device/device-service/user/device/{device_id}",
            body=body,
            x_pha_apptype="",  # signed-as-empty per captured traffic
        )

    # ---------------------------------------------------- compat for template

    async def async_get_data(self) -> dict[str, Any]:
        """Compatibility entrypoint used by the blueprint's config-flow validator.

        Returns the raw `listdevices` payload; only used to verify auth works.
        """
        if self._id_token is None:
            await self.async_login()
        else:
            await self.async_ensure_fresh()
        return await self.async_list_devices()

    # --------------------------------------------------------------- WebSocket

    @property
    def access_token(self) -> str | None:
        """Current Cognito access token (used as the WS `?token=` query param)."""
        return self._access_token

    def ws_url(self) -> str:
        """Build the wss URL with the current access token."""
        return f"{WS_URL}?token={self._access_token}"

    # ------------------------------------------------------------------ utils

    @staticmethod
    def _decode_jwt_sub(token: str) -> str | None:
        """Best-effort JWT payload decode for `sub`; no signature verification."""
        try:
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        except Exception:  # noqa: BLE001
            return None
        return payload.get("sub")


class PentairPoolWebSocket:
    """Long-lived WS subscriber that pumps device deltas into a callback."""

    HEARTBEAT_INTERVAL = 1.0

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client: PentairPoolApiClient,
        device_ids: list[str],
        on_device_data: Callable[[str, dict[str, dict]], Awaitable[None]],
    ) -> None:
        """Hold refs and configure; nothing happens until start()."""
        self._session = session
        self._client = client
        self._device_ids = device_ids
        self._on_device_data = on_device_data
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        """Start the background task if not already running."""
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run_forever(), name="pentair-ws")

    async def stop(self) -> None:
        """Signal stop and wait for the background task to finish."""
        self._stop.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run_forever(self) -> None:
        """Reconnect loop with exponential backoff (capped at 30s)."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._client.async_ensure_fresh()
                async with self._session.ws_connect(self._client.ws_url(), heartbeat=30) as ws:
                    _LOGGER.info("Pentair WS connected")
                    backoff = 1.0
                    await self._register(ws)
                    hb = asyncio.create_task(self._heartbeat_loop(ws))
                    try:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_text(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                _LOGGER.warning("Pentair WS error: %s", ws.exception())
                                break
                    finally:
                        hb.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await hb
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Pentair WS disconnected: %s", err)
            if self._stop.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _register(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        for did in self._device_ids:
            await ws.send_str(
                json.dumps(
                    {
                        "action": "registerEvent",
                        "body": {
                            "device_ids": did,
                            "active_screen": "poolScreen",
                            "token": self._client.access_token,
                        },
                    },
                ),
            )

    async def _heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while not ws.closed:
            try:
                await ws.send_str("keep-alive")
            except ConnectionResetError:
                return
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    async def _handle_text(self, text: str) -> None:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return
        if obj.get("event_type") != "device_data":
            return
        device_id = obj.get("deviceId")
        fields = (obj.get("data") or {}).get("fields") or {}
        if device_id and fields:
            await self._on_device_data(device_id, fields)
