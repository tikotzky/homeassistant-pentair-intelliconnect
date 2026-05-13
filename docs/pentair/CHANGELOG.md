# Changelog (development sessions)

Notable code-level changes during reverse-engineering / iteration sessions. Higher-level project status is in `STATUS.md`.

## 2026-05-12 — Session 2 (HA integration brought live)

Starting state: integration files copied into the HACS blueprint template, HA running in a VS Code devcontainer, config flow returning `"Invalid handler specified"`.

### Fixes landed

1. **`const.py` — restored options-flow legacy constants.** Removed earlier; the blueprint's `options_flow.py` still imported `DEFAULT_ENABLE_DEBUGGING` and `DEFAULT_UPDATE_INTERVAL_HOURS`. The missing import was crashing the config-flow load, which surfaced to the UI as "Invalid handler specified."

2. **`api/client.py` — Cognito Identity MIME guard.** Pentair's Cognito Identity service returns `Content-Type: application/x-amz-json-1.1`, which aiohttp rejects by default. All four `resp.json()` callsites against `cognito-identity.us-west-2.amazonaws.com` now pass `content_type=None`. (Cognito IDP and the Pentair Cloud API itself use plain `application/json`; only Cognito Identity uses the AWS variant.)

3. **`coordinator/base.py` — get_device response shape.** Captured response is `{"response": {"data": [{...}]}}`, not `{"response": [{...}]}`. The original parsing did `response[0]` which raises `KeyError: 0` against a dict. Replaced with a two-shape-tolerant accessor (`response.data[0]` first, falling back to `response[0]`).

4. **`api/client.py` — async_get_device body.** The Pentair API silently swallows `{"deviceId": id}` and returns `200 OK` with `response.data: []`. The captured app body is `{"deviceIds": [id]}` (plural key, list value). Body shape now matches the capture verbatim.

5. **`switch/pump.py` — `is_on` reads from `ra4` not `ra0`.** The user reported the pump switch desynchronizing: showing OFF while the pump was actually drawing 1392 W (because Daily Schedule was firing). Root cause: `ra0` is user intent, `ra4` is physical state. Switched `is_on` to `int(ra4_value) > 0` so the switch reflects truth. Writes still go to `ra0` (intent). Added `extra_state_attributes` exposing `ra0` and `ra4_watts` for debugging and automations.

6. **`time/` — new platform.** Added `time.daily_schedule_start` (binds to `ra1`) and `time.daily_schedule_end` (binds to `ra2`). Built-in UTC↔local conversion using `hass.config.time_zone`. Added `Platform.TIME` to `PLATFORMS` in `__init__.py`.

7. **Display ordering of schedule times.** User wanted start to appear before end in HA's alphabetical name sort. Renamed display label "Daily schedule end" → "Daily schedule stop" so `start` < `stop` alphabetically. Entity ID `time.intelliconnect_daily_schedule_end` kept unchanged for backwards compat. The rename required directly patching `config/.storage/core.entity_registry` because HA caches `original_name` at first registration and doesn't re-read it from the platform on subsequent restarts.

### Dev tooling added

- **`script/pentair_test`** — host-side bash wrapper. Detects whether it's running on the host or inside the container; on host, finds the VS Code devcontainer via `docker ps` (filters by image-name prefix `vsc-hacs-pentair-pool-*`) and `docker exec`s the Python driver inside. Means all HA traffic happens over container loopback — VS Code port-forwarding is irrelevant.

- **`script/_pentair_test.py`** — in-container Python driver. Reads the user's stored refresh token from `config/.storage/auth`, mints a short-lived access token, and runs commands against HA's HTTP API. Subcommands: `logs`, `errors`, `entries`, `remove`, `flow`, `restart`, `loop`, `states`, `call`.

- **`script/_probe.py`** — direct probe against `PentairPoolApiClient` using HA's Python venv. Useful for poking the raw API without bouncing through HA.

- **`script/_cooldown_capture.py`** — polling-diff capture template. Sets up a phase machine (idle → bump setpoint → wait for heating → kill pump → watch for cooldown countdown). Reusable for any "drive UI then watch field changes" investigation.

### Outstanding from this session

- Cooldown live-countdown field still unidentified (test conditions weren't right; see STATUS.md §2).
- Salt-cell boost control not yet exposed as an entity.
- `ics3` alarm code raised on this device but not decoded.

## 2026-05-11 — Session 1 (reverse-engineering)

Reverse-engineering work happened in a separate research workspace outside this repo. High-level summary:

- Set up Frida + mitmproxy intercept of the Pentair Android app on a rooted emulator.
- Captured the full Cognito SRP → STS → SigV4 auth chain.
- Captured every device control (pump on/off, Daily Schedule on/off + time edit, heater on/off + setpoint, chlorine output, IntelliChlor boost start/stop).
- Decoded the `ra0` filter-pump state machine from the JS bundle.
- Documented the Pentair Cloud API (auth flow, REST endpoints, WS protocol, signed-headers list, field-code reference, captured PUT-body catalogue) for internal reference.
- Built first scaffold of the HA integration, later migrated into the HACS blueprint that became this repo.
