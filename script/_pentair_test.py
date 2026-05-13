#!/usr/bin/env python3
"""
Drive the running Home Assistant instance to exercise the pentair_pool config flow.

Reads the user's stored refresh token from ./config/.storage/auth, mints a short-
lived access token, and runs commands against HA's HTTP API on localhost:8123.

Usage:
    script/pentair_test logs          tail the last 200 log lines for our domain
    script/pentair_test errors        same, but only errors / tracebacks
    script/pentair_test entries       list existing pentair_pool config entries
    script/pentair_test remove        delete every pentair_pool config entry
    script/pentair_test flow EMAIL PW submit a fresh config flow (start to entry)
    script/pentair_test restart       POST homeassistant.restart and wait for /api/
    script/pentair_test loop EMAIL PW restart -> wait -> flow -> errors (one shot)
    script/pentair_test states        list every pentair_pool entity + state
    script/pentair_test call SVC ENTITY=value [k=v ...]
                                      call DOMAIN.SVC with entity_id + service data,
                                      e.g.  call switch.turn_on entity_id=switch.pump

Env overrides:
    HA_URL    default http://localhost:8123
    HA_USER   pick a specific user_id when multiple users exist (prefix match ok)
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_STORE = REPO_ROOT / "config" / ".storage" / "auth"
LOG_FILE = REPO_ROOT / "config" / "home-assistant.log"
HA_URL = os.environ.get("HA_URL", "http://localhost:8123").rstrip("/")
HA_USER_PREFIX = os.environ.get("HA_USER", "")
DOMAIN = "pentair_pool"


# -------------------------------------------------------- auth / http helpers


def _load_refresh_token() -> tuple[str, str]:
    """Return (refresh_token, client_id) for the first matching `normal` token."""
    if not AUTH_STORE.exists():
        die(f"{AUTH_STORE} not found — is HA running?")
    auth = json.loads(AUTH_STORE.read_text())
    rts = auth.get("data", {}).get("refresh_tokens", [])
    candidates = [
        rt for rt in rts
        if rt.get("token_type") == "normal"
        and (not HA_USER_PREFIX or (rt.get("user_id") or "").startswith(HA_USER_PREFIX))
    ]
    if not candidates:
        die("no `normal` refresh token found in auth store")
    rt = candidates[0]
    return rt["token"], rt.get("client_id") or f"{HA_URL}/"


def _get_access_token(retries: int = 8) -> str:
    """Exchange the stored refresh token for a short-lived access token.

    Devcontainer port-forwarding can hiccup briefly; retry with backoff so the
    driver script doesn't die when HA is just transitioning.
    """
    refresh_token, client_id = _load_refresh_token()
    data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
    ).encode()
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{HA_URL}/auth/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)["access_token"]
        except Exception as err:
            last_err = err
            time.sleep(2 + attempt)
    die(f"could not mint access token after {retries} retries: {last_err}")


def _api(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
    """GET/POST/DELETE the HA API; return (status, parsed_json_or_text)."""
    if token is None:
        token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    data: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(f"{HA_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status = r.status
            text = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        status = err.code
        text = err.read().decode("utf-8", errors="replace")
    except Exception as err:
        return (-1, str(err))
    try:
        return (status, json.loads(text))
    except (json.JSONDecodeError, ValueError):
        return (status, text)


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------- commands


def cmd_logs(*_args: str) -> None:
    if not LOG_FILE.exists():
        die(f"{LOG_FILE} not found")
    lines = LOG_FILE.read_text(errors="replace").splitlines()
    keep = [ln for ln in lines if DOMAIN in ln or "Invalid handler" in ln]
    for ln in keep[-200:]:
        print(ln)


def cmd_errors(*_args: str) -> None:
    if not LOG_FILE.exists():
        die(f"{LOG_FILE} not found")
    text = LOG_FILE.read_text(errors="replace")
    # Find blocks: ERROR/Traceback lines + their immediate context
    keep: list[str] = []
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if DOMAIN in ln and ("ERROR" in ln or "Traceback" in ln):
            start = max(0, i - 2)
            end = min(len(lines), i + 25)
            keep.append("--- " + ln[:80])
            keep.extend(lines[start:end])
            keep.append("")
        elif "cannot import name" in ln or "Invalid handler" in ln:
            keep.append(ln)
    for ln in keep[-300:]:
        print(ln)


def cmd_entries(*_args: str) -> None:
    status, data = _api("GET", "/api/config/config_entries/entry?domain=" + DOMAIN)
    if isinstance(data, list):
        for e in data:
            print(f"  {e['entry_id']:32s} title={e.get('title')!r} state={e.get('state')}")
        if not data:
            print("(no entries)")
    else:
        print(status, data)


def cmd_remove(*_args: str) -> None:
    status, data = _api("GET", "/api/config/config_entries/entry?domain=" + DOMAIN)
    if not isinstance(data, list):
        die(f"could not list entries: {data}")
    for e in data:
        s, _ = _api("DELETE", f"/api/config/config_entries/entry/{e['entry_id']}")
        print(f"  deleted {e['entry_id']}: {s}")


def cmd_flow(*args: str) -> None:
    if len(args) < 2:
        die("usage: flow EMAIL PASSWORD")
    email, password = args[0], args[1]
    token = _get_access_token()

    print("  -> POST /api/config/config_entries/flow")
    status, data = _api(
        "POST",
        "/api/config/config_entries/flow",
        body={"handler": DOMAIN, "show_advanced_options": False},
        token=token,
    )
    if status != 200 or not isinstance(data, dict) or "flow_id" not in data:
        die(f"flow start failed: {status} {data}")
    flow_id = data["flow_id"]
    print(f"  flow_id={flow_id}  step={data.get('step_id')}")

    print(f"  -> POST flow/{flow_id} with credentials")
    status, data = _api(
        "POST",
        f"/api/config/config_entries/flow/{flow_id}",
        body={"username": email, "password": password},
        token=token,
    )
    print(f"  status={status}  type={data.get('type') if isinstance(data, dict) else '?'}")
    if isinstance(data, dict):
        if data.get("type") == "create_entry":
            print(f"  success! entry_id={data.get('result', {}).get('entry_id')} title={data.get('title')}")
        else:
            print(json.dumps(data, indent=2)[:1500])


def cmd_restart(*_args: str) -> None:
    """Restart HA in a way that doesn't leave the process dead.

    `homeassistant.restart` via the service API kills the foreground hass
    process; if there's no supervisor inside the devcontainer (which is the
    case for the blueprint's `script/develop`), nothing brings it back.

    So when we're running inside the container we bypass the service call
    and exec hass directly: `pkill -f "hass --config"` then start a new
    nohup'd hass in the background.

    Outside the container we fall back to the service-call path (your
    deployment is presumably managed by a supervisor).
    """
    import os
    import subprocess

    in_container = os.path.exists("/.dockerenv")

    if in_container:
        print("  -> docker-side hass kill + relaunch")
        repo_root = "/workspaces/hacs-pentair-pool"
        venv_python = "/home/vscode/ha-venv/bin/python3"
        venv_hass = "/home/vscode/ha-venv/bin/hass"
        subprocess.run(["pkill", "-f", "hass --config"], check=False)
        time.sleep(2)
        # Detach via setsid + redirect so HA survives this script exiting.
        subprocess.Popen(
            ["setsid", venv_python, venv_hass, "--config", f"{repo_root}/config"],
            stdin=subprocess.DEVNULL,
            stdout=open("/tmp/ha-bg.log", "ab"),
            stderr=subprocess.STDOUT,
            close_fds=True,
            start_new_session=True,
        )
    else:
        print("  -> homeassistant.restart")
        s, _ = _api("POST", "/api/services/homeassistant/restart", body={})
        print(f"  status={s}")

    start = time.time()
    deadline = start + 180
    while time.time() < deadline:
        time.sleep(2)
        try:
            with urllib.request.urlopen(f"{HA_URL}/", timeout=3) as r:
                if r.status == 200:
                    print(f"  back up after {int(time.time() - start)}s")
                    return
        except Exception:
            continue
    die("HA did not return in 180s")


def cmd_loop(*args: str) -> None:
    """One pass of restart -> wait -> remove existing -> flow -> errors."""
    if len(args) < 2:
        die("usage: loop EMAIL PASSWORD")
    print("[1/4] restart")
    cmd_restart()
    print("[2/4] remove existing entries")
    with contextlib.suppress(SystemExit):
        cmd_remove()
    print("[3/4] submit flow")
    cmd_flow(*args)
    print("[4/4] errors")
    cmd_errors()


def cmd_states(*_args: str) -> None:
    """List every HA entity whose entity_id namespace contains a pentair device id."""
    status, data = _api("GET", "/api/states")
    if not isinstance(data, list):
        die(f"could not list states: {data}")
    pentair = []
    # First pull the integration's devices to filter by their ids in unique_id.
    s, entries = _api("GET", "/api/config/config_entries/entry?domain=" + DOMAIN)
    entry_ids = {e["entry_id"] for e in (entries or [])} if isinstance(entries, list) else set()
    # Heuristic: pentair entities all carry "intelliconnect", "salt", "filter_pump",
    # "daily_schedule", "heater", "chlorine", or the bare device id in entity_id.
    needles = ("intelliconnect", "filter_pump", "daily_schedule", "salt_cell", "salt_level",
               "chlorine", "heater", "boost_remaining", "pnra1pif")
    for st in data:
        eid = st.get("entity_id", "")
        if any(n in eid.lower() for n in needles):
            pentair.append(st)
    pentair.sort(key=lambda s: s["entity_id"])
    for st in pentair:
        attrs = st.get("attributes", {}) or {}
        unit = attrs.get("unit_of_measurement", "")
        unit_str = f" {unit}" if unit else ""
        print(f"  {st['entity_id']:55s} = {st['state']!s:>20}{unit_str}")
    print(f"\n  ({len(pentair)} entities)")


def cmd_watch(*args: str) -> None:
    """Poll selected pentair fields + climate state at 1 Hz.

    Usage:
        watch              -- run forever, one line per second
        watch SECONDS      -- run for SECONDS, then exit

    Prints a TSV-ish row of: htd1 htd14 htd3rpm htd13 ra0 ra4 t0 htd2set
    plus the climate entity's hvac_action. Use this while toggling the
    heater on/off / setpoint up/down to map htd1 values to real heater
    behavior (firing vs. holding vs. cooling down).
    """
    duration = float(args[0]) if args else float("inf")
    token = _get_access_token()
    _, cfg = _api("GET", f"/api/config/config_entries/entry?domain={DOMAIN}", token=token)
    if not isinstance(cfg, list) or not cfg:
        die("no pentair_pool config entry found")
    entry_id = cfg[0]["entry_id"]

    def snapshot() -> dict[str, str]:
        _, diag = _api("GET", f"/api/diagnostics/config_entry/{entry_id}", token=token)
        if not isinstance(diag, dict):
            return {}

        def _find_fields(obj):
            if isinstance(obj, dict):
                if "htd1" in obj or "ra0" in obj:
                    return obj
                for v in obj.values():
                    r = _find_fields(v)
                    if r:
                        return r
            elif isinstance(obj, list):
                for v in obj:
                    r = _find_fields(v)
                    if r:
                        return r
            return None

        fields = _find_fields(diag) or {}
        return {k: (fields[k].get("value") if isinstance(fields[k], dict) else fields[k])
                for k in ("htd1", "htd14", "htd3", "htd13", "ra0", "ra3", "ra4", "ras0", "t0", "htd2")
                if k in fields}

    print(f"{'wall':>8} | {'htd1':>4} {'htd14':>5} {'ras0':>5} {'ra3':>5} {'htd3rpm':>7} {'htd13':>5} | "
          f"{'ra0':>3} {'ra4':>5} | {'t0':>4} {'set':>4} | hvac_action")
    start = time.monotonic()
    while time.monotonic() - start < duration:
        snap = snapshot()
        _, climate = _api(
            "GET", "/api/states/climate.intelliconnect_heater", token=token,
        )
        action = (climate or {}).get("attributes", {}).get("hvac_action") if isinstance(climate, dict) else "?"
        setpt = snap.get("htd2", "")
        try:
            setpt = f"{int(setpt) / 10:.1f}" if setpt else ""
        except ValueError:
            pass
        wall = time.strftime("%H:%M:%S")
        print(f"{wall:>8} | {snap.get('htd1',''):>4} {snap.get('htd14',''):>5} "
              f"{snap.get('ras0',''):>5} {snap.get('ra3',''):>5} "
              f"{snap.get('htd3',''):>7} {snap.get('htd13',''):>5} | "
              f"{snap.get('ra0',''):>3} {snap.get('ra4',''):>5} | "
              f"{snap.get('t0',''):>4} {setpt:>4} | {action}", flush=True)
        time.sleep(1)


def cmd_call(*args: str) -> None:
    """Invoke a service. First arg is `domain.svc`, rest are k=v service-data items."""
    if not args:
        die("usage: call DOMAIN.SVC [k=v ...]")
    svc = args[0]
    if "." not in svc:
        die("service must be in 'domain.svc' form, e.g. switch.turn_on")
    domain, name = svc.split(".", 1)
    body: dict[str, str] = {}
    for kv in args[1:]:
        if "=" not in kv:
            die(f"service data must be k=v (got {kv!r})")
        k, _, v = kv.partition("=")
        body[k] = v
    print(f"  -> {domain}.{name} {body}")
    s, d = _api("POST", f"/api/services/{domain}/{name}", body=body)
    print(f"  status={s}")
    if isinstance(d, (list, dict)):
        print(json.dumps(d, indent=2)[:2000])
    else:
        print(d)


COMMANDS = {
    "logs": cmd_logs,
    "errors": cmd_errors,
    "entries": cmd_entries,
    "remove": cmd_remove,
    "flow": cmd_flow,
    "restart": cmd_restart,
    "loop": cmd_loop,
    "states": cmd_states,
    "watch": cmd_watch,
    "call": cmd_call,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(__doc__)
        sys.exit(0 if "-h" in sys.argv or "--help" in sys.argv else 1)
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        die(f"unknown command: {cmd}")
    COMMANDS[cmd](*sys.argv[2:])


if __name__ == "__main__":
    main()
