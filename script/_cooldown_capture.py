"""Drive a heater-cooldown capture.

Phases:
  A. Read current state, bump heater setpoint +1 degF.
  B. Poll fields every 1.5s, watch for htd1 to transition (idle -> heating).
  C. Once heating, turn the pump switch OFF.
  D. Keep polling for up to 5 min, dumping every field whose value changes,
     so we can spot a cooldown-countdown indicator.
  E. Restore original setpoint, restore pump switch state.

Output:
  /workspaces/hacs-pentair-pool/script/_cooldown_capture.jsonl
       one JSON record per change, with ts, phase, field, old, new, name
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pentair_test as t  # noqa: E402

DOMAIN = "pentair_pool"
LOG_PATH = Path(__file__).with_suffix(".jsonl")


def _coordinator_devices(token: str) -> dict[str, dict]:
    """Call diagnostics for the integration's first config entry.

    Devices nest at `data.devices.<id>` in the HA-wrapped diagnostics response.
    """
    s, entries = t._api("GET", f"/api/config/config_entries/entry?domain={DOMAIN}", token=token)
    if not isinstance(entries, list) or not entries:
        sys.exit("no pentair_pool config entry")
    entry_id = entries[0]["entry_id"]
    s, diag = t._api("GET", f"/api/diagnostics/config_entry/{entry_id}", token=token)
    if s != 200 or not isinstance(diag, dict):
        sys.exit(f"diagnostics failed: {s} {diag}")
    return ((diag.get("data") or {}).get("devices") or {})


def _snap(token: str) -> tuple[str, dict[str, str]]:
    """Return (device_id, {field_code: value}) for the first device."""
    devs = _coordinator_devices(token)
    if not devs:
        return "", {}
    did = next(iter(devs))
    fields = devs[did].get("fields") or {}
    return did, {k: (v or {}).get("value") for k, v in fields.items()}


def _diff(prev: dict[str, str], cur: dict[str, str]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for k in sorted(set(prev) | set(cur)):
        if prev.get(k) != cur.get(k):
            out.append((k, prev.get(k), cur.get(k)))
    return out


def log(rec: dict) -> None:
    rec["ts"] = time.time()
    LOG_PATH.open("a").write(json.dumps(rec) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "ts"}, ensure_ascii=False))


def main() -> None:
    LOG_PATH.write_text("")  # truncate
    token = t._get_access_token()

    did, snap = _snap(token)
    if not did:
        sys.exit("no device")
    print(f"# device: {did}")
    print(f"# starting state: htd1={snap.get('htd1')}, htd2={snap.get('htd2')}, htd14={snap.get('htd14')}, ra0={snap.get('ra0')}, ra4={snap.get('ra4')}")
    original_setpoint = snap.get("htd2") or "890"
    original_ra0 = snap.get("ra0")

    new_setpoint = str(int(original_setpoint) + 10)  # +1 degF
    log({"phase": "A", "event": "set_temperature", "from": original_setpoint, "to": new_setpoint})

    # Use HA service to set the new target temp (entity_id resolves through the climate platform).
    target_f = int(new_setpoint) / 10
    t._api(
        "POST",
        "/api/services/climate/set_temperature",
        body={"entity_id": "climate.intelliconnect_heater", "temperature": target_f},
        token=token,
    )

    # Poll for changes
    start = time.time()
    heating_started_at = None
    pump_turned_off_at = None
    last = snap

    while True:
        elapsed = time.time() - start
        if elapsed > 300:  # 5 min cap
            log({"event": "timeout"})
            break

        try:
            _, cur = _snap(token)
        except urllib.error.URLError:
            time.sleep(1.5)
            continue
        for k, before, after in _diff(last, cur):
            log({"phase": _phase(heating_started_at, pump_turned_off_at), "field": k, "from": before, "to": after})
        last = cur

        # Phase transitions
        if heating_started_at is None and cur.get("htd1") == "1":
            heating_started_at = time.time()
            log({"event": "heating_started"})

        if heating_started_at is not None and pump_turned_off_at is None and time.time() - heating_started_at >= 10:
            # Heater has been heating for >=10s; turn the pump off.
            log({"event": "turn_off_pump"})
            t._api(
                "POST",
                "/api/services/switch/turn_off",
                body={"entity_id": "switch.intelliconnect_filter_pump"},
                token=token,
            )
            pump_turned_off_at = time.time()

        if pump_turned_off_at is not None and time.time() - pump_turned_off_at >= 90:
            # Watched cooldown for ~90 s, we're done.
            log({"event": "capture_complete"})
            break

        time.sleep(1.5)

    # Restore
    log({"event": "restore_setpoint", "to": original_setpoint})
    t._api(
        "POST",
        "/api/services/climate/set_temperature",
        body={"entity_id": "climate.intelliconnect_heater", "temperature": int(original_setpoint) / 10},
        token=token,
    )
    # Restore pump intent
    if original_ra0 in ("1", "3"):
        log({"event": "restore_pump_on"})
        t._api(
            "POST",
            "/api/services/switch/turn_on",
            body={"entity_id": "switch.intelliconnect_filter_pump"},
            token=token,
        )

    print(f"\n# done. {LOG_PATH}")


def _phase(heating_at: float | None, pump_off_at: float | None) -> str:
    if pump_off_at is not None:
        return "D-cooldown"
    if heating_at is not None:
        return "C-heating"
    return "B-bumped"


if __name__ == "__main__":
    main()
