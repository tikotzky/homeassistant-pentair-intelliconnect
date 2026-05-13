<p align="center">
  <img src="icons/logo.png" alt="Pentair IntelliConnect" width="200" />
</p>

# Pentair IntelliConnect

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

A Home Assistant custom integration for **Pentair IntelliConnect** pool controllers, communicating with the Pentair Cloud over HTTPS + WebSocket. It exposes the filter pump, pool heater, IntelliChlor salt cell, and the daily schedule as native Home Assistant entities.

The integration is reverse-engineered from the official Pentair Home mobile app; there is no public Pentair API. It authenticates against the same AWS Cognito user pool as the app and subscribes to the same real-time WebSocket, so state changes from the wall panel or the official app show up in Home Assistant within a second.

## Platforms and entities

The integration is configured per Pentair account and surfaces one Home Assistant device per IntelliConnect controller on that account. Entities are only created if the controller actually reports the underlying field, so accessories you don't own (for example, a salt cell on a chlorine-tab pool) won't produce orphan entities.

| Platform        | Entities                                                                                                                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `binary_sensor` | **Online** (connectivity), **Alarm** (problem flag), **Filter pump running** (true while Relay 1 draws power)                                                                                     |
| `climate`       | **Heater** — HVAC entity wrapping the pool heater. `heat` / `off` modes, setpoint in °F, `current_temperature` from the water-temp probe, `hvac_action` reports `heating` / `idle` / `off`        |
| `number`        | **Chlorine output** — IntelliChlor salt-cell output setpoint (0–100 %, slider)                                                                                                                    |
| `sensor`        | **Water temperature**, **Air temperature**, **Heater mode** (Off / Auto idle / Heating / …), **Heater cooldown** (live 1 Hz countdown), **Filter pump power** (W)                                 |
| `sensor` (salt) | **Chlorine actual** (%), **Salt** (ppm), **Salt cell temperature**, **Salt cell hours**, **Boost remaining** (s), **Salt cell model**, **Salt cell firmware**                                     |
| `switch`        | **Filter pump** (manual override, preserves the schedule bit), **Daily schedule** (enable/disable the recurring schedule, preserves the pump on/off bit)                                          |
| `time`          | **Daily schedule start**, **Daily schedule stop** (stored as UTC seconds-of-day on the controller, displayed in your Home Assistant timezone)                                                     |

### Notable behaviors

- **Filter pump switch `is_on` follows reality, not intent.** It reads ON whenever the pump is actually circulating water — manual override, scheduled run, or heater cooldown extending the run — matching what the Pentair app shows. When you toggle the switch, an optimistic state is held until the controller's reported wattage agrees. Tap OFF during heater cooldown and the switch stays OFF for the whole cooldown window; the pump physically stops a few minutes later when the firmware releases the relay.
- **Heater cooldown sensor ticks every second.** The Pentair Cloud only pushes the cooldown counter every 10–30 s; the entity re-anchors on each push and ticks locally in between so dashboards see a smooth countdown. It snaps to 0 the moment the pump reports 0 W.
- **Schedule times are timezone-aware.** Writes always go out as UTC seconds-of-day (what the firmware expects) using Home Assistant's configured timezone for the conversion.

## Service actions

| Service                  | Description                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `pentair_pool.reload_data` | Forces an immediate REST poll of the Pentair Cloud for every configured account. Useful after changing settings at the panel. |

The WebSocket push is the primary update path; a 60 s REST fallback poll runs in the background to catch any missed pushes.

## Installation

### HACS (recommended)

This integration requires [HACS](https://hacs.xyz/).

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tikotzky&repository=hacs-pentair-pool&category=integration)

1. Click "Download" in HACS to install the integration
2. Restart Home Assistant

<details>
<summary><strong>Manual install</strong></summary>

1. Copy `custom_components/pentair_pool/` from this repository into your Home Assistant `custom_components/` directory
2. Restart Home Assistant

</details>

### Configure

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=pentair_pool)

Or: **Settings → Devices & Services → Add Integration → "Pentair IntelliConnect"**.

You will be prompted for the **username** (email) and **password** of your Pentair Home / IntelliConnect account — the same credentials you use in the mobile app. The integration verifies them against AWS Cognito and stores the resulting tokens; tokens are refreshed automatically before they expire.

#### Reauthenticate / change credentials

If your password changes, Home Assistant will automatically prompt you to reauthenticate. You can also update credentials at any time via **Settings → Devices & Services → Pentair IntelliConnect → ⋮ → Reconfigure**.

## Troubleshooting

### Debug logging

Add to `configuration.yaml` and restart Home Assistant:

```yaml
logger:
  default: info
  logs:
    custom_components.pentair_pool: debug
```

### "Pump is on but I didn't tell it to"

Check the **Daily schedule** switch and the **Daily schedule start / stop** times. The schedule fires every day at those times regardless of the **Filter pump** switch state. The **Filter pump running** binary sensor reports the physical truth (Relay 1 power), which is the source for whether the pump is actually circulating water.

### Heater shows "Idle" but I set it to Heat

The Pentair heater has a two-step state machine: writing `heat` puts the firmware into "Auto idle" (`htd1 = 1`), and the firmware itself promotes that to "Heating" (`htd1 = 3`) once both conditions are met — water below setpoint **and** the filter pump is providing flow. The HVAC action will read `idle` until flow is available.

## Compatibility

- Tested against IntelliConnect controllers (PIF0 device type) on US accounts (Cognito `us-west-2`)
- Heater, IntelliChlor IC-40 salt cell, and Daily Schedule are wired up; pumps controlled directly via Relay 1
- EU Cognito pool constants are present in the source but have not yet been exercised — open an issue if you're on a EU account and willing to test

## Contributing

Issues and pull requests are welcome. The repository ships a fully configured devcontainer (Home Assistant + Python tooling + Node.js + lint/format/test scripts).

<details>
<summary><strong>Development setup</strong></summary>

### GitHub Codespaces

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/tikotzky/hacs-pentair-pool?quickstart=1)

Click the badge, wait 2–3 minutes for the container to build, then run:

```bash
script/develop   # starts Home Assistant on port 8123
```

### Local devcontainer

Requires Docker (or OrbStack / Rancher / Colima / Docker CE) and VS Code with the Dev Containers extension. Clone the repository, open in VS Code, choose **Reopen in Container**, then `script/develop`.

### Validation

```bash
script/check    # hassfest + ruff + spellcheck
script/test     # pytest
```

</details>

## AI-assisted development

This integration was developed with substantial assistance from AI coding agents (Claude, GitHub Copilot, others). The protocol details were reverse-engineered from captures of the official Pentair Home Android app; see `docs/` for protocol notes if you're contributing. AI-generated code in this repository is reviewed and exercised against a real controller, but please [open an issue](https://github.com/tikotzky/hacs-pentair-pool/issues) if you spot something off.

## License

MIT — see [LICENSE](LICENSE).

This project is not affiliated with, endorsed by, or supported by Pentair.

[commits-shield]: https://img.shields.io/github/commit-activity/y/tikotzky/hacs-pentair-pool.svg?style=for-the-badge
[commits]: https://github.com/tikotzky/hacs-pentair-pool/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/tikotzky/hacs-pentair-pool.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40tikotzky-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/tikotzky/hacs-pentair-pool.svg?style=for-the-badge
[releases]: https://github.com/tikotzky/hacs-pentair-pool/releases
