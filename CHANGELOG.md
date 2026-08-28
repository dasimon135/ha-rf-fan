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
- **`fan_natural_reverse`, the winter code of the natural-airflow key**
  ([#28](https://github.com/dasimon135/ha-rf-fan/issues/28), reported by @elmr91).
  `direction_control: per_speed` describes a remote whose internal winter/summer
  switch sits in front of every code it sends, and 1.8.0 modelled that for the speeds
  only — so in winter the preset button transmitted the summer code, and either
  nothing happened or the wrong thing did. One extra key to learn, asked for only
  when the fan has the preset **and** the remote is `per_speed`; existing entries of
  any other shape are untouched. A sniffed winter natural frame now reports the
  preset and the direction together, the same way a reverse speed code does.
- **A brightness row on the bundled card**, and blades that turn the way the fan
  says it is turning ([#27](https://github.com/dasimon135/ha-rf-fan/issues/27),
  reported by @elmr91). The card offered a bare on/off lamp button, so the only way
  to reach the brightness of a `light_level: relative` lamp was the standard
  more-info dialog. The row appears only when the light entity declares
  `ColorMode.BRIGHTNESS` — the card applies the same rule as the entity, and does
  not draw a slider that can move nothing. The animation used one set of keyframes
  for both directions, so a fan in winter mode was drawn turning forwards; it is now
  played in reverse, which is one CSS property and cannot drift from the forward
  case. Colour segments past the third also give up padding, so eight numbered
  positions stay on one line in a half-width dashboard column.

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
  speeds 7 to 12 that this release makes reachable had ever been added. Filling those
  in by hand then missed the four stepping keys this same release introduces —
  `light_kelvin_up` / `_down` and `light_bright_up` / `_down`, which is precisely the
  remote shape that prompted all of it. A test now derives the full action space from
  `split_actions` and fails if any reachable action lacks a label, a re-learn label,
  or a French translation, in any of the three files. This had shipped three times.
- **The card's own labels are complete in both languages.** It carries a two-language
  table rather than reading Home Assistant's translations, so every string it writes
  has to be added there by hand, and the `aria-label`s never were — a screen reader
  announced "Lower", "Raise", "On/Off" and "Close" in English on a French install.
- **The colour position rolled over at the end of its range**
  ([#18](https://github.com/dasimon135/ha-rf-fan/issues/18), measured by @elmr91 on
  `v1.8.0b2`). Pressing "warmer" on the top position moved nothing on the lamp — it
  was already at the end — while the integration jumped back to the first position.
  The walk was written when the only modelled shape was a single cycling key, for
  which coming round really is what the hardware does. A `relative` pair of +/- keys
  is a range, exactly like the brightness, and it now clamps at both ends: reception
  no longer rolls over, and a walk no longer plans a route through an end stop it
  would then believe it had taken. `color_control: cycle` is unchanged.
- **The card was served with a month of cache headers, and a stale copy said nothing**
  ([#29](https://github.com/dasimon135/ha-rf-fan/issues/29), hit by @elmr91). The file
  was registered with `cache_headers=True`, so Home Assistant served it
  `public, max-age=2678400` — 31 days. The `?v=<version>` on the URL the integration
  loads made that harmless for the integration's own copy, since the URL changes with
  every release; a dashboard resource registered by hand has no such luck, and stays
  frozen for a month whatever is on disk. He upgraded twice and his browser kept
  executing the 1.7.0 card. Now served without cache headers: one conditional request
  per page load, for a file that changes every release.

  The second half of the trap was silence. The card guards its `define()` because it
  can legitimately be loaded twice, but that means the copy that loads **first** wins
  and a defined custom element cannot be replaced — so an old build keeps rendering
  and a release looks like it changed nothing. The new copy now says so in the
  console, naming both versions and where the stale one usually lives.
- **The card's colour row drove the wrong select, and refused clicks anyway**
  ([#29](https://github.com/dasimon135/ha-rf-fan/issues/29), reported by @elmr91).
  Two separate defects behind one symptom. The row was bound to the *assumed
  brightness position* select — nine segments under a thermometer icon on a fan
  configured with five colour positions — because the translation-key match added in
  this release does not always reach the card, and the last-resort fallback took
  whichever select came first. It now also filters on `EntityCategory.CONFIG`, which
  needs no key exposed and is right by construction: a CONFIG entity declares the
  integration's belief and emits nothing, so it can never be the colour row. And
  every segment carried `disabled` whenever the *light* read off — a state the card
  read off the lamp and decided for itself, while the colour select next to it
  already declares the answer. The row now follows the entity instead of guessing:
  available means fully usable whatever the lamp reads, and unavailable means
  disabled, dimmed, and carrying the reason (`title` and `aria-disabled`) rather
  than rendering as usual and swallowing the press. The select does go unavailable
  with the lamp off, and it is right to — @elmr91 checked his remote and its colour
  keys do nothing then either — but a control that ignores you in silence is what
  makes a user go and check. Neither defect is specific to the new position counts.
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
- **The colour position was bumped on every light power-on, on remotes that have no
  reason to do it** ([#38](https://github.com/dasimon135/ha-rf-fan/issues/38)). The
  bump models a real property of the reference lamp -- a single colour key that
  cycles, on a fixture that walks forward each time it is powered -- but it fired for
  any entry with colour at all, `color_control: relative` included. Nobody has
  measured a two-key lamp behaving that way. It stayed invisible while a relative
  walk still wrapped, because the spurious steps rolled around and looked like
  ordinary drift; clamping the ends made them accumulate instead, so a handful of
  on/off cycles pinned the assumed position at the coldest end while the lamp had not
  moved. The bump is now gated on `color_control: cycle`, which is the shape it
  describes. Should a `relative` lamp ever be measured advancing on power-on, that
  becomes a capability of its own rather than something inferred.
- **A card that never loaded, and a log that would not say why.** The option
  *Disable automatic dashboard card loading* sits on a config entry, but the card is
  registered once for the whole frontend -- so one fan opting out silences the card
  for every fan. @elmr91 lost it on every dashboard because a single entry, set up
  under an earlier release, still had the box ticked
  ([#29](https://github.com/dasimon135/ha-rf-fan/issues/29)); the frontend showed a
  missing card, and the integration mentioned the opt-out at `INFO` without naming
  anybody. It is now a `WARNING` that lists the fans still holding the option, says
  that the effect is global, and the README says the same in its troubleshooting
  section. The behaviour itself is unchanged: one opt-out still disables the
  auto-load everywhere, which is what a single frontend registration can express.
- **`natural_control`, for remotes whose breeze key selects a mode instead of
  toggling one** ([#34](https://github.com/dasimon135/ha-rf-fan/issues/34), measured
  by @elmr91 over three corrections on `v1.8.0b2`). `has_natural_preset` becomes the
  fourth capability to stop being a boolean, and for the same reason as the other
  three: it could only describe one shape of remote.
  - `toggle` -- what every existing entry is migrated to, and unchanged in every
    respect.
  - `dedicated` -- the key **sets** the preset. Pressing it again does nothing on the
    hardware, so Home Assistant leaves the preset the way the remote does: by
    re-sending the current speed. Until now it pressed the breeze key a second time,
    which meant Home Assistant could put such a fan into the preset and never take it
    out. A received breeze frame now sets the preset rather than flipping it, and any
    speed -- commanded or sniffed from the remote -- clears it.
  - A `dedicated` key is deaf while the fan is stopped, so a preset asked for then is
    recorded and pressed on the next start, after the speed code. The same shape as
    the direction a `per_speed` remote records with the fan off.
  - No code changes name and nothing is relearned; `toggle` and `dedicated` learn the
    same `fan_natural` (and `fan_natural_reverse` on a `per_speed` remote).
- **Setting the brightness switched the lamp on and off**
  ([#41](https://github.com/dasimon135/ha-rf-fan/issues/41), reported by @elmr91 on
  `v1.8.0b5`). Home Assistant sets a brightness through `light.turn_on`, and that
  path transmitted the power key before stepping -- unconditionally. On a remote
  whose only light key is `light_toggle`, every move of the slider flipped the lamp,
  and the walk that followed stepped a lamp that had just gone dark. Neither the card
  nor the stepping was at fault: the native more-info slider did the same, and so did
  a scene.

  A power command now goes on the air only when it would help. `light_on` and
  `light_off` are absolute, so they are still sent whatever the assumed state -- on a
  device that never reports back, a free re-assertion is the cheapest way to recover
  from a state that has drifted. `light_toggle` is a flip, so it is held back when
  the lamp is already in the state being asked for. An unknown state still transmits,
  because nothing is established until something is sent. This is the rule
  `switch.py` has always applied to the sound toggle; the light was the exception.

  The same defect existed in `async_turn_off` and had never been reported: turning
  off a lamp already believed off switched it **on**, so a scene asserting "lights
  out" could light one. Fixed by the same change.

  It hid because the brightness tests counted the stepping frames and ignored what
  went out around them. They now assert the complete sequence.

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
