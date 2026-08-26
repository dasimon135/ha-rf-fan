# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Stepped controls, for remotes whose buttons MOVE a value instead of setting
  one.** Three new capability shapes, all reported on
  [#18](https://github.com/dasimon135/ha-rf-fan/issues/18) by @elmr91 for an Inspire
  Aruba Plus, and all measured on real hardware before being built:
  - `light_level: relative` — two dedicated brightness keys. The light entity gains
    `ColorMode.BRIGHTNESS`, dead-reckoned over ten modelled steps. Declared only
    when the remote actually has the keys: a slider that cannot move anything is
    worse than no slider.
  - `color_control: relative` — two dedicated colour keys instead of one cycling
    key, so the walk takes whichever way round is shorter, and a press on the
    physical remote is tracked in both directions rather than only forwards.
  - `direction_control: per_speed` — for a remote with **no** reverse key at all,
    which stores the winter/summer mode itself and emits a different speed code per
    direction. The direction becomes *absolute* rather than dead-reckoned: setting
    it re-sends the current speed from the other code set, and one sniffed frame
    carries the speed and the direction together.
- **A brightness resynchronisation button and an assumed-position select** (both
  `EntityCategory.CONFIG`). Dead reckoning has no way back once it drifts, and these
  are the two ways back: the button walks the lamp into its bottom stop, which is
  audible and slow but physically true; the select simply declares the position,
  which is silent and instant but only as good as what you tell it.
- **Speed counts from 2 to 12** (was a fixed choice of 3–6). The old cap had no
  technical reason behind it; 9-speed remotes exist.
- **The number of modelled positions is now declared per fan**, for both the colour
  temperature and the brightness. Both used to be constants — ten brightness steps
  and the three named colour positions. @elmr91 measured his Inspire Aruba Plus at
  eight of each ([#18](https://github.com/dasimon135/ha-rf-fan/issues/18)), which is
  what moved them into the config flow: too few and the top of the slider never
  reaches the hardware's maximum, too many and the last presses do nothing. Existing
  entries keep the old numbers, so nothing changes until the counts are edited.
  Three colour positions keep their names — those strings are the entity's state, so
  renaming them would break automations — and any other count is numbered 1..N.
- **`esphome/rf_fan_raw_gateway.yaml`** — a protocol-agnostic gateway for remotes
  rc_switch cannot decode. It captures the frame's raw transitions through `on_raw`
  and replays them verbatim as `raw:<t1>,<t2>,…`, which the ESPHome contract already
  accepted but no shipped example produced. Reported by @Ltek on the forum, whose
  9-speed remote never fires `on_rc_switch` at all: the log shows raw timing dumps
  and no `Received RCSwitch Raw:` line, so Home Assistant was never told about the
  frame. Transmission goes through the `remote_transmitter` API (RMT-timed, and the
  existing hooks strobe the radio into TX and back) rather than toggling the pin by
  hand. Documented limitation: raw frames jitter between presses and code matching is
  exact string equality, so transmitting works while following the physical remote
  cannot. The gateway also rate-limits published receptions and drops bursts shorter
  than a threshold — a held button otherwise fills the ESPHome API queue.

### Changed

- **Three capability checkboxes became selectors**, because the remote can express
  each of them in more than one shape: `has_direction` → `direction_control`,
  `has_color_temp` → `color_control`, plus the new `light_level`. Config entries
  migrate automatically (version 3). **No learned code is invalidated** — every
  existing action key keeps its exact name, so nothing has to be relearned.

### Fixed

- **A frame repeated by the remote was counted as several presses**
  ([#24](https://github.com/dasimon135/ha-rf-fan/issues/24)). A remote does not send
  one frame per press: it sends the same frame four to six times so that at least one
  arrives, and every copy was treated as a separate press. A toggle key flickered
  on/off/on, and a step key advanced the assumed position once per frame — one press
  of "brighter" moved the brightness six steps. Receptions are now de-bounced per
  code over a sliding window, the mirror image of the anti-echo window that already
  covered our own transmissions. Absolute actions were never affected: sending speed
  3 six times still means speed 3, which is why this only surfaced once passive
  tracking ([#16](https://github.com/dasimon135/ha-rf-fan/issues/16)) started
  updating state and 1.8.0 gave it numbers to corrupt.
- **The learning screens showed raw keys** such as `relearn_fan_speed_1_reverse`.
  The translation files stopped at `fan_speed_6`: neither the reverse set nor the
  speeds 7 to 12 that this release makes reachable had ever been added.
- **The bundled card could drive the wrong sibling entity** once an entry owned two
  selects or two buttons. It picked "the first select" and "the button that is not a
  timer", so a fan with relative brightness could have its colour row wired to the
  assumed-position select (which emits nothing, so the row looked dead) and its
  "recalibrate colour" button wired to the brightness resync (which walks the lamp
  all the way down). Both are now matched on the registry translation key.
- **Two overlapping walks left the assumed position wrong.** Moving a stepped
  control while a previous move was still emitting interleaved the two, and the
  position ended up describing neither. A second move now cancels the first and
  plans from the frames that actually went on the air. Present since the colour
  cycle was introduced — rare with three colours, routine with ten brightness steps.

## [1.7.0] - 2026-08-23

### Fixed

- **The dashboard card broke when the module was loaded twice.** The integration
  registers it through `add_extra_js_url`, and a user may also add it as a Lovelace
  resource — which is the only mechanism the Android companion app loads reliably. The
  second pass hit an unguarded `customElements.define()`, which throws, and the card
  then failed everywhere rather than just once. Both registrations and the
  `window.customCards` entry are now guarded.
- **A toggle action ignored `repeat_count` entirely and always went out once**, so a
  receiver that needs several identical frames before it accepts anything never saw
  `light_toggle` — while `fan_on`, sent `repeat_count` times over the same radio with
  the same code shape, worked. Toggles now honour the configured count, rounded *down
  to the nearest odd value*: a receiver that debounces the burst registers one press
  whatever the count, and one that treats every frame as a press registers a net flip
  only when the count is odd, so an odd count is correct under both. The default
  (`repeat_count: 2`) still transmits once, so nothing changes for existing setups.
  `SINGLE_SHOT_ACTIONS` is renamed `TOGGLE_ACTIONS` and the arithmetic lives in
  `actions.transmit_repeat_count`, next to the rest of the Home-Assistant-free logic.
  ([#15](https://github.com/dasimon135/ha-rf-fan/issues/15))
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
