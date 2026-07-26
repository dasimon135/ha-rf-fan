# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-07-26

Audit pass: the fixes below all come with regression tests (the suite goes from
34 to 59 tests).

### Fixed

- **Echo suppression is now keyed on the transmitted code** instead of muting all
  RF reception for a second. A press on a *different* remote button right after a
  Home Assistant command is no longer swallowed, and a late echo of our own frame
  can no longer flip the toggle actions (`light_toggle`, `sound_toggle`,
  `fan_reverse`, `fan_natural`) straight back. The window is also armed *before*
  the service call, closing a race where the echo could land first.
- **The sleep-timer sensor now clears itself when the switch-off time is reached.**
  Nothing scheduled a refresh at that moment, so the entity kept publishing a
  timestamp that was already in the past.
- **`fan.turn_on` now applies `preset_mode`.** The service schema accepted it and
  the entity silently dropped it.
- **Disabling a capability removes its entities.** Turning `has_sound`,
  `has_timers` or `has_color_temp` off during a reconfiguration left the registry
  rows behind as permanently unavailable ghosts.
- **The colour select no longer moves its assumed position when nothing was
  transmitted** (unmapped `light_kelvin` code), and a timer button no longer
  records a switch-off time when its code is missing.
- **Setting up without the frontend no longer logs an error with a stack trace.**
  `after_dependencies` only orders the setup, it does not guarantee the frontend
  exists; the card file stays served either way.
- **Card: HTML is escaped.** Entity friendly names are user-editable and were
  interpolated into `innerHTML` verbatim.
- **Card: the version banner matches the shipped build again** (was stuck at
  1.4.1 while the integration was 1.5.0 — misleading precisely when diagnosing a
  stale browser cache).

### Added

- **Light toggle on the `tile` layout.** The light is the other thing you reach for
  on a ceiling fan; it no longer requires opening the popup. Shown only when the
  fan actually has a light, and it lights up amber while the light is on.
- **First tests for the bundled card** (`tests/frontend/`), run by `node --test`
  against a minimal DOM stub — no dependency, no build step, and a new CI job.
- **Diagnostics now carry the assumed state** (`runtime` section: colour
  position, light, sleep timer, number of armed anti-echo windows). The fan
  reports nothing back, so this was the one thing a bug report could not show.
- **Duplicate captured codes are rejected.** The repeats of a held button kept
  arriving after the learning flow had moved on, so the same frame was easily
  stored for two actions — which makes the received-frame lookup ambiguous and
  silently unreachable from the remote. Both the guided and the manual flow now
  refuse it (new `duplicate_code` error, translated in en/fr).
- `scripts/run-tests.ps1` / `scripts/run-tests.sh` / `scripts/Dockerfile.tests`:
  run the full Home Assistant suite locally on Windows (HA's runner imports the
  POSIX-only `fcntl`, so it needs a Linux container).
- Tests for the previously uncovered areas: echo suppression, sleep timer,
  registry cleanup, entry migration, card registration.

### Changed

- `ECHO_SUPPRESS_SEC` 1.0 → 2.0 s. Now that suppression is per code, a wider
  window costs far less and covers a slow or congested gateway.
- **The card classifies buttons by their registry `translation_key`** instead of
  guessing from the entity_id. Renaming a timer button's entity_id used to make
  it masquerade as the colour-calibrate button — and fire the wrong RF code. The
  id pattern remains as a fallback for registries that do not expose the key.
- The setup step that picks manual vs guided learning is translated (it showed
  the raw `manual` / `learn` keys; `vol.In` labels are never translated).
- Ruff `target-version` py313 → py314, matching CI and the HA 2026.5 target.
- README: documented the `rc_switch` protocol-1 limitation of the reference
  gateway, the anti-echo trade-off, and the Docker test workflow.

### Known limitation (unchanged)

The reference ESPHome gateway publishes the sniffed frame without `x.protocol`
and replays it with `protocol: 1`. Remotes on `rc_switch` protocols 2–8 learn
fine but do not actuate the fan. Fixing this means changing the firmware contract
and re-learning every code, so it is deliberately left out of this release.

## [1.5.0] - 2026-07-18

Visible transmit failures, gateway repair issue, config entry migration.

## [1.4.0] - 2026-07-17

Tile card layout with tap-to-open popup.

## [1.3.0] - 2026-07-14

Blueprint, sleep timer, card polish, badges, more tests.

## [1.2.1] - 2026-07-14

CI green (hassfest / HACS / pytest).

## [1.2.0] - 2026-07-14

CI, diagnostics, robust learning, compact card.

[1.6.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.6.0
[1.5.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.5.0
[1.4.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.4.0
[1.3.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.3.0
[1.2.1]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.2.1
[1.2.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.2.0
