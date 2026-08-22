# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **The reference ESPHome gateway published codes it could not replay.** The
  `rc_code` lambda returned `x.code`, which `on_rc_switch` hands over as a 64-bit
  integer — so the event carried the code's *decimal* form (`645080348`), while
  `transmit_rc_switch_raw` reads its input as a bit string, one bit per character.
  Every learned code was therefore replayed as a handful of nonsense bits. The
  gateway now rebuilds the bit string explicitly and emits `<protocol>:<bits>`,
  the shape the README documented all along and the shape the rc_switch dumper
  prints. ([#16](https://github.com/dasimon135/ha-rf-fan/issues/16))
- The frame's bit **length** is dropped by `RCSwitchData` and cannot be recovered
  from the integer, so a code with leading zeros was unrecoverable. It is now
  declared explicitly through the `rc_code_bits` substitution, and the rc_switch
  dumper is left enabled so the value can be read straight off the log.

### Added

- `last_unmatched_code` in the diagnostics, plus a debug log line listing it next
  to every learned code. Following the physical remote is exact string matching;
  when the gateway's code shape changes it stops matching anything and used to do
  so in complete silence, which is indistinguishable from the feature not
  existing. ([#16](https://github.com/dasimon135/ha-rf-fan/issues/16))
- `esphome/rf_fan_example.yaml` now uses ESPHome's built-in `cc1101:` component
  with **separate RX (GDO2) and TX (GDO0) pins**. Sharing one GDO0 pin makes the
  pin mode fight between `remote_receiver`, `remote_transmitter` and the radio
  driver, and on ESP32 that can leave RMT capture permanently deaf — reported
  independently by several users as "the log shows nothing at all, not even
  noise".
- `esphome/rf_fan_radiolib_legacy.yaml` keeps the previous RadioLib single-pin
  configuration for gateways already wired that way (with the same code-shape fix).
- Troubleshooting sections for a remote that updates nothing, and for a code that
  is learned correctly but does not actuate the fan (measuring the real timings
  with `rtl_433 -A` instead of assuming rc_switch protocol 1).

> **Upgrading:** changing the code shape a gateway emits invalidates codes learned
> under the old one — matching is exact string equality. After flashing the updated
> YAML, relearn via **⋮ → Reconfigure → Relearn RF codes**.

Thanks to @elmr91, @Relutzzzu and @Ltek, who diagnosed most of this on the forum.

## [1.6.1] - 2026-07-26

Documentation only; no code change.

### Changed

- The entities table said the sleep timer clears "when the fan is turned off". It
  also clears itself when it elapses — as of 1.6.0 the table documented the bug
  rather than the fix.
- The features list described reconfiguration as capability-only, missing the
  relearn-a-single-code path added in 1.6.0.
- The project structure listed no tests, although `tests/frontend/` has its own
  runner and CI job.
- `.github/copilot-instructions.md` claimed Python 3.12+ (3.14 is required since
  the HA 2026.5 target) and knew nothing about the bundled card, the test layout,
  or the rule that RF codes are opaque strings never to be parsed.

### Added

- A **Troubleshooting** section. The fan reports nothing back, so every state
  shown is dead-reckoned; the diagnostics `runtime` dump is the only way to see
  what the integration currently believes, and nothing pointed at it.

## [1.6.0] - 2026-07-26

Audit pass: every fix below comes with a regression test. The suite goes from 34
to 69 Python tests, plus 11 new tests for the bundled card.

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
- **Relearning a single code no longer means re-declaring the fan.** Reconfigure
  now opens on a menu: "Relearn RF codes" goes straight to the per-action recap,
  "Change the fan declaration" keeps the previous path. Re-capturing one
  mis-learned button went from four screens to two, and no longer rewrites the
  rest of the entry.
- **Renaming a fan during a reconfiguration now renames the entry.** Only the
  data field changed: the Integrations page kept showing the old title and the
  entry kept its old unique id, so the renamed fan still answered to its former
  identity. A name already used by another fan on the same gateway is refused
  (new `name_already_used` error) instead of creating an indistinguishable pair.
- **Tests for the shipped blueprint**, put through Home Assistant's own blueprint
  schema and then validated as a substituted automation.
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
- The blueprint uses the current automation syntax (`triggers:` / `trigger:` /
  `actions:` / `action:`). The pre-2024.10 spelling still works, but a shipped
  blueprint gets copied as a template, so it should teach the current form.
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

[1.6.1]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.6.1
[1.6.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.6.0
[1.5.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.5.0
[1.4.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.4.0
[1.3.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.3.0
[1.2.1]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.2.1
[1.2.0]: https://github.com/dasimon135/ha-rf-fan/releases/tag/v1.2.0
