# Changelog

All notable changes to this project are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-05-13

### Changed

- **Subscribe to both `poolScreen` and `product` WebSocket screens.** The Pentair cloud only pushes the field set the official app would render on the screen named in the most recent `registerEvent`, and the two screens cover disjoint fields. With a single `poolScreen` subscription, real-time pushes for `ra0` / `ra4` (filter pump), `htd1` / `htd14` (heater mode + cooldown raw), and `icd1` (chlorine setpoint) were missing and only the 60 s REST poll caught changes. The integration now runs two WS subscriptions in parallel per controller, so the union covers every field the entities consume. The REST poll is now a true fallback.
- **Send `appuse=1` keepalive on the `product` subscription.** Mirrors what the official app does while a device-detail screen is open. `appuse` is documented and observed as a presence ping with no mapped device control, and is what (almost certainly) keeps high-rate `product`-screen pushes flowing on long-lived sessions.
- **Manifest cleanup.** Fixed `documentation` and `issue_tracker` URLs (now point at `tikotzky/homeassistant-pentair-intelliconnect`, matching the actual repo). Declared `pycognito` under `loggers` so Home Assistant's "Enable debug logging" toggle reaches the auth chain.

### Docs

- Rewrote the README against the actual entity set the integration creates (pool heater climate, filter pump + daily schedule switches, schedule start/stop times, chlorine setpoint number, salt-cell + temperature sensors, cooldown countdown, online / alarm / pump-running binary sensors, and the `pentair_pool.reload_data` service). Removed the air-purifier placeholder content (AQI, PM2.5, child lock, LED display, fan select, `example_action`) and options-flow fields inherited from the blueprint that aren't wired to behavior.

## [0.2.0] - 2026-05-12

### Added

- First working build against a live Pentair IntelliConnect (PIF0) controller.
- Climate entity for the pool heater (HVAC modes, setpoint in °F, current temperature, heater-mode / cooldown attributes).
- Filter pump switch with optimistic toggle that follows real pump wattage (`ra4`), preserving Daily Schedule on writes.
- Daily Schedule switch + Daily Schedule start / stop time entities (UTC seconds-of-day on the wire, displayed in HA's local timezone).
- IntelliChlor entities: chlorine output number, plus salt-cell telemetry sensors (chlorine %, salt ppm, cell temperature, hours, boost remaining, model, firmware).
- Heater cooldown countdown sensor with 1 Hz local tick between server pushes, snapping to 0 the moment the pump reports 0 W.
- Online / alarm / filter-pump-running binary sensors.
- `pentair_pool.reload_data` service to force an immediate REST poll.
- Real-time WebSocket subscription (`registerEvent` against `g44t970cbi.execute-api.us-west-2.amazonaws.com`) with auto-reconnect and 60 s REST fallback poll.
- Brand icons shipped inside the integration for the HA 2026.3+ proxy API.

[0.3.0]: https://github.com/tikotzky/homeassistant-pentair-intelliconnect/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/tikotzky/homeassistant-pentair-intelliconnect/releases/tag/v0.2.0
