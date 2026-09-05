# RF Fan — Home Assistant integration

[![Release](https://img.shields.io/github/v/release/dasimon135/ha-rf-fan)](https://github.com/dasimon135/ha-rf-fan/releases)
[![Validate](https://github.com/dasimon135/ha-rf-fan/actions/workflows/validate.yml/badge.svg)](https://github.com/dasimon135/ha-rf-fan/actions/workflows/validate.yml)
[![Tests](https://github.com/dasimon135/ha-rf-fan/actions/workflows/tests.yml/badge.svg)](https://github.com/dasimon135/ha-rf-fan/actions/workflows/tests.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/dasimon135/ha-rf-fan)](LICENSE)

A **generic** Home Assistant integration for RF (typically 433 MHz) ceiling and wall
fans that have no manufacturer-specific integration. You pair it with an ESPHome
gateway that can transmit — and ideally receive — the raw RF frames, then teach Home
Assistant your remote button by button.

It is deliberately protocol-agnostic: the integration stores your codes as **opaque
strings** and replays them through the ESPHome gateway. It does not care whether the
frames are `rc_switch`, raw timings, or anything else the gateway understands. A
Cecotec fan is used as the reference example, but any RF fan works.

<p align="center">
  <img src="assets/rf-fan-card.gif" width="200" alt="RF Fan animated card">
  &nbsp;&nbsp;
  <img src="custom_components/rf_fan/brand/icon@2x.png" width="120" alt="RF Fan icon">
</p>

## Features

- **Config flow** — no YAML to write.
- **Two setup methods**: paste already-sniffed codes manually, or **guided learning**
  from remote button presses (via ESPHome events).
- **Declarative capabilities** — you only get asked for the buttons your fan actually
  has:
  - Discrete fan speeds (2–12).
  - Optional light: none / single toggle / separate on & off buttons.
  - Optional dedicated fan "on" button.
  - **Rotation direction**: none / one reverse button / *a separate speed code per
    direction* (for remotes that store winter/summer themselves and emit no
    direction code at all).
  - **Color temperature**: none / one cycling button / *two buttons* (warmer and
    cooler).
  - **Light brightness**: none / *two buttons* (brighter and dimmer).
  - Optional **natural-airflow preset** and **sound** toggle.
  - **Sleep timers**: tick only the durations your remote actually has, out of
    1/2/4/8 h — they are independent, so a remote with off/2/4/8 declares three and
    nothing is missing. A separate **timer-cancel key** can be declared alongside
    them if the remote has one.
  - **Direction-aware off**: on a remote with a speed code per direction, an optional
    `fan_off_reverse` code stops the fan from reverse without leaving the receiver's
    stored direction pointing the wrong way. Leave it blank and `fan_off` is used for
    both, exactly as before.
- **Reconfigure in place** — either relearn a single mis-captured button, or add and
  change capabilities and learn only the new ones, keeping the codes you already
  captured (see below).
- **Assumed state** (`assumed_state`) with dead-reckoning, plus partial state sync when
  the physical remote is used (if the gateway reports received frames).
- **Configurable RF repeat count**.

## Entities

Depending on the declared capabilities, a device exposes:

| Entity | When | Notes |
| --- | --- | --- |
| `fan` | always | discrete speeds; gains `direction` and a `natural` preset when enabled |
| `light` | light ≠ none | on/off; gains a dead-reckoned `brightness` when the remote has ± keys |
| `select` "color temperature" | color ≠ none | Warm → Neutral → Cold |
| `button` calibrate | color ≠ none | resyncs the assumed color position — **emits nothing** |
| `select` "assumed brightness position" | brightness = relative | declares where the lamp is — **emits nothing** |
| `button` resync brightness | brightness = relative | walks the lamp down to its lowest step — **does emit** |
| `button` timer | one per declared duration | 1 h / 2 h / 4 h / 8 h, individually optional |
| `button` cancel timer | timer-cancel key declared | **does emit**: calls off the fan's countdown and clears the assumed switch-off time |
| `sensor` sleep timer | at least one timer declared | assumed switch-off time set by the timer buttons (clears itself when it elapses, when the timer is cancelled, or when the fan is turned off) |
| `switch` sound | sound enabled | beep on/off |

### Color temperature (Kelvin)

The integration tracks an **assumed position** (dead-reckoning) whichever shape your
remote has, because the lamp never reports back. To change the color, use the
**"color temperature" dropdown** and pick a value *different* from the one shown —
picking the current value sends nothing. The color only changes visibly when the
light is on.

The two shapes differ in what they can do:

- **One cycling button** — the only direction available is forward, so going from
  Cold back to Warm sends however many presses it takes to come round.
- **Two buttons (warmer / cooler)** — the walk takes whichever way round is shorter,
  and a press on the *physical* remote is followed in both directions.

The **calibrate button never emits RF**: it only tells Home Assistant "the lamp is
now on Warm", to re-align the dropdown if it drifts (set the lamp to Warm physically,
then press it).

### Brightness (remotes with ± keys)

If you declare `light_level: relative`, the light entity gains a real brightness
slider. There is nothing clever behind it: a position is **how many presses up from
the lowest step**, modelled over ten steps, and the integration counts them. Ten is a
starting figure, not a measurement — if the top of your slider never reaches full
brightness, your lamp has more steps than that; if the last presses do nothing, it
has fewer (harmless).

Dead reckoning drifts — someone uses the physical remote out of range of the gateway,
or the lamp was already dimmed before Home Assistant ever saw it. Two ways back, and
they are deliberately different:

| | What it does | Cost |
| --- | --- | --- |
| **"Assumed brightness position"** select | Declares where the lamp is. Emits nothing. | Silent and instant, but only as good as what you tell it. |
| **"Resynchronise brightness"** button | Walks the lamp into its bottom stop (N−1 presses). | Physically true, but audible and slow — and on many remotes stepping below the lowest level switches the lamp off. |

The lamp's own on/off state has the same pair, for the same reason: pressing **off**
on a lamp Home Assistant already believes is off still sends the key, which puts a
lit lamp out and realigns the two — while the **"Assumed light state"** select simply
declares which state it is in, and sends nothing. Use the first when you are in
front of the lamp, the second when you are not.

### Direction without a reverse button

Some remotes have no direction code at all: an internal switch selects winter or
summer and the remote then emits a *different set of speed codes* for each. Declare
`direction_control: per_speed` and you will be asked to learn both sets
(`fan_speed_N` and `fan_speed_N_reverse`) — twice the buttons to teach. The natural
airflow key gets the same treatment where the fan has one (`fan_natural` and
`fan_natural_reverse`): the switch is in front of *every* code the remote sends, not
only the speeds.

What you get for it is a direction that is **absolute** rather than guessed. With a
single reverse button, the integration can only flip and hope, because it has no way
to know which way the fan was turning to begin with. Here the code itself carries the
direction: setting it re-sends the current speed from the other set, and one frame
sniffed from the physical remote reports the speed and the direction together.

### Natural airflow that selects instead of toggling

On most remotes the breeze key is a switch: press it to go in, press it again to
come out. On others it behaves like a speed — it **selects** the mode, a second
press changes nothing, and what takes the fan out of it is pressing a speed key.
Same button, same code, opposite meaning for anyone trying to leave.

Declare which one you have with `natural_control`:

| | What a press means | Leaving the preset |
| --- | --- | --- |
| `toggle` | Flips the preset | The same key again |
| `dedicated` | Sets the preset | The current speed, re-sent |

Nothing extra is learned — both shapes use the one `fan_natural` code (plus
`fan_natural_reverse` on a `per_speed` remote). With `dedicated`, choosing a speed
in Home Assistant or on the remote takes the fan out of the preset, because that is
what the hardware does.

One consequence worth knowing: a `dedicated` breeze key is **deaf while the fan is
off** — the mode only exists while it is running. Asking for the preset with the fan
stopped therefore transmits nothing; it is remembered, and pressed for you on the
next start, right after the speed code that gets the fan going.

### Keys this integration has no concept of

Some remotes carry a button nobody can describe — a memory key, an ioniser, a
"comfort" mode that does something proprietary. There is nothing to model behind
those, and pretending otherwise would be worse than saying so.

Declare how many you have (**Extra buttons**, up to 8) and name them on the step
that follows. Each becomes a Home Assistant button that transmits its code when
pressed, under the name you gave it, and the bundled card shows them as chips at
the bottom.

That is the whole feature. There is no state behind an extra key, assumed or
otherwise: a switch saying "memory on" would display a belief that nothing can
establish and nothing can correct.

**Renaming is free** — the code is stored against a stable index, your label lives
beside it, and nothing is relearned. Reducing the count forgets the *last* key
rather than renumbering the others: a learned code is never reassigned to a
different button.

**A free-form key can still move things this integration tracks.** @elmr91's remote
has a memory key: held for three seconds it *stores* the fan's whole state, pressed
briefly it *recalls* it — speed, light, brightness and colour, all at once. The
integration sends the code and learns nothing back, so after a recall its assumed
state can be wrong in every dimension simultaneously, and nothing about the press
tells it so.

That is not a reason to avoid such a key — two codes, one for store and one for
recall, work perfectly well as two extra buttons. It is a reason to know what
follows: after a recall, either drive the fan once from Home Assistant, or use the
declaration controls ("Assumed light state", "Assumed brightness position", the
colour select) to say where things actually are.

Anything Home Assistant *does* have a concept of stays typed — speed, direction,
colour, brightness, the airflow preset. A typed entity works in scenes, in voice
assistants and in every native card; a labelled button works only for a human
reading the label. This layer is for what is left, not a replacement for the rest.

## Requirements

- Home Assistant **2026.5+**.
- An ESPHome node exposing a `transmit_rf_fan` service (see the ESPHome contract below).
- An RF transmitter supported by ESPHome (e.g. a CC1101 module).
- Ideally an RF receiver too, for guided learning and physical-remote state sync.

## Hardware (reference gateway)

The reference gateway is an **ESP32** DevKit with a **CC1101** 433 MHz transceiver,
flashed with ESPHome. Any ESPHome-supported RF transmitter works — this is just the
setup used to build and test the integration.

> ⚠️ The CC1101 is a **3.3 V** module — do not power it from 5 V.

| CC1101 | ESP32 |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SCK | GPIO18 |
| MOSI (SI) | GPIO23 |
| MISO (SO) | GPIO19 |
| CSN (CS) | GPIO5 |
| GDO0 | GPIO4 — transmit data |
| GDO2 | GPIO13 — receive data |

The radio is driven by ESPHome's built-in
[`cc1101`](https://esphome.io/components/cc1101.html) component at 433.92 MHz, with
**separate RX and TX pins**. Wiring both onto GDO0 also works, but that single pin has
to be re-moded on every RX/TX switch, and on ESP32 that can leave `remote_receiver`
permanently deaf — no decoded frames, not even background noise. If your gateway hears
nothing at all, this is the first thing to rule out; a config for that older single-pin
scheme is kept in
[esphome/rf_fan_radiolib_legacy.yaml](esphome/rf_fan_radiolib_legacy.yaml).
A 433 MHz antenna is required — it connects to the **CC1101 module** (the ESP32 has no
radio): solder a ~17.3 cm wire (quarter-wave for 433.92 MHz) to the **ANT** pad, unless
your module already has a spring antenna or an SMA connector. A full working config is in
[esphome/rf_fan_example.yaml](esphome/rf_fan_example.yaml). RX can be noisy depending on
the local 433 MHz environment; TX is reliable.

## Installation (HACS)

1. Add this repository as a **custom repository** of type `Integration`.
2. Install **RF Fan**.
3. Restart Home Assistant.
4. Add the **RF Fan** integration and follow the config flow.

## Dashboard card (bundled)

The integration ships an **animated Lovelace card** — no separate install or resource
to register. On a dashboard, add a card and pick **RF Fan Card** from the picker, or
use YAML:

```yaml
type: custom:rf-fan-card
entity: fan.your_fan
```

`entity` (a `fan.*`) is the only required field. The card walks up to that fan's
device and auto-discovers the sibling entities (light, colour-temperature select,
sound switch, timer/calibrate buttons), showing only the controls that exist. The fan
blades spin at a speed-proportional rate, and it follows your Home Assistant theme.

Optional fields: `name` (override the title), `layout`, and entity overrides
(`light_entity`, `color_entity`, `sound_entity`) if auto-discovery picks the wrong one.
All fields are editable from the card's visual editor. **Long-press the fan** to open
its more-info dialog. When a sleep timer is running, the card shows the switch-off time.

`layout` takes one of:

| Value | What you get |
| --- | --- |
| `full` (default) | Everything: hero fan, speed, light/sound, colour, direction/preset, timers |
| `compact` | Reduced: fan, speed and light/sound only |
| `tile` | One row aligned with HA's native tiles: power dot, name/state, light toggle, speed − / + |

On the `tile` layout the light toggle only appears when the fan actually has a light,
and tapping the name opens the full card in a popup — set `tile_tap: more-info` to get
Home Assistant's native more-info dialog instead.

An example automation **blueprint** (control the fan by temperature) is in
[`blueprints/automation/rf_fan/`](blueprints/automation/rf_fan/).

### The card looks like it did not update

The console prints a banner — `RF-FAN-CARD v1.8.1b4` — as the card registers itself,
and that is the build you are actually looking at, whatever the integration reports.
It is printed *after* the registration, so a banner also means the file finished
loading rather than merely starting to. If it names an
older version after an upgrade, a stale copy is being served, and it is almost
always a **dashboard resource you registered by hand**: the integration loads the
card on its own, so a leftover manual entry is a second copy under a second URL.

Whichever copy loads first wins. A custom element cannot be replaced once defined,
so the old build keeps rendering and the new one can only say so — which it does,
naming both versions in the console.

Remove the resource under **Settings → Dashboards → ⋮ → Resources**, or bump its
`?v=` suffix, then hard-reload (and clear the app cache on the companion app).

### How the card is loaded

The integration registers the card as a **Lovelace resource** — the same mechanism
HACS uses for every custom card it installs. That matters for one reason: Lovelace
loads its own resources and *waits* for them before rendering a card, so the card
is always defined by the time your dashboard draws it.

You do not need to add a resource by hand, and if you already have one pointing at
`/rf_fan_frontend/rf-fan-card.js` it is adopted rather than duplicated: its URL is
moved to the current version on every upgrade. Removing the last RF Fan takes the
resource with it.

Where a resource cannot be created — a Lovelace configuration in YAML mode, whose
resource list is your file and not the integration's to write — the card falls back
to the frontend's module list, which is how it was loaded before.

### Disabling automatic card loading

The card is auto-loaded for the whole frontend when the integration starts. If you
prefer to manage the dashboard resource yourself (or not load the card at all),
enable **Disable automatic dashboard card loading** in the integration options
(**Settings → Devices & services → RF Fan → Configure**) and restart Home
Assistant. The setting is global: enabling it on any RF fan entry disables the
auto-load for all of them.

**If the card does not load at all**, this is the first thing to check, and with
several fans it is easy to miss: the checkbox lives on each fan but silences the
card for every one of them, so a box ticked on a fan you set up months ago is
enough. The integration says so at startup — search the log for `RF Fan: the
bundled card will NOT load` and it names the fans still holding the option. Clear
it on all of them and restart.

The card file remains served at `/rf_fan_frontend/rf-fan-card.js`, so you can
still register it manually under **Settings → Dashboards → ⋮ → Resources** (type
*JavaScript module*). Add a `?v=<version>` query suffix and bump it after updates:
the file itself is served without long-lived cache headers, but a proxy or a
service worker in front of Home Assistant can still hold a copy. If automatic
registration ever fails, the integration logs an error at startup and this manual
route works as a fallback.

## Reconfiguring an existing fan

To add a capability (or fix a captured code) later, open the integration entry and use
**⋮ → Reconfigure** (on the *RF Fan* integration card, not the device page):

You land on a menu with two paths:

**Relearn RF codes** — for a button that was mis-captured. Goes straight to the review
screen: tick the action(s) to re-capture and learn them again. Nothing else is touched.

**Change the fan declaration** — for adding or removing a capability:

1. Re-declare the capabilities (existing values are pre-filled) and enable the new ones.
2. On the review screen you see what will be **learned** (newly required buttons),
   **kept** (existing codes — tick a box to re-learn one), and **removed**.
3. Choose learning or manual entry; only the delta is asked for.

Either way the entry reloads in place — your dashboards and automations keep working.
Renaming the fan here also renames the entry itself; a name already used by another fan
on the same gateway is refused.

> A full Home Assistant **restart** is required after updating the integration so the
> new config-flow steps load.

## ESPHome contract

The ESPHome node must expose a Home Assistant service named `transmit_rf_fan` with:

- `action` — logical action name (`fan_speed_1`, `light_toggle`, `timer_2h`, …).
- `code` — the RF frame as an opaque string (raw CSV timings such as
  `raw:150,-5839,1144,-370,…`, or a `<protocol>:<bits>` rc_switch code).
- `repeat_count` — number of RF repeats.

For guided learning and physical-remote sync, the node should also fire the
`esphome.rf_fan_received` event with `device` and `code` fields. A complete, working
example is in [esphome/rf_fan_example.yaml](esphome/rf_fan_example.yaml).

### Code shape (rc_switch gateways)

The integration never parses a code — it stores what the gateway reported and hands the
same string back. So the *only* hard requirement is that the two directions agree, and
that whatever the gateway emits is something `transmit_rc_switch_raw` can replay.

That rules out the obvious shortcut. `on_rc_switch` hands the lambda `x.code` as a
64-bit **integer**, so returning it directly yields its decimal representation
(`645080348`); `transmit_rc_switch_raw` reads its input as a *bit string*, one bit per
character, and would send nine bits of nonsense. The example YAML therefore rebuilds the
bit string explicitly and prefixes the protocol number:

```text
1:000100110101000110100011
^ protocol
  ^ bits, most significant first
```

`RCSwitchData` also drops the frame's bit **length**, and it cannot be recovered from the
integer (leading zeros are lost). It has to be declared in the YAML, via the
`rc_code_bits` substitution, and it has to be exact — `transmit_rc_switch_raw` takes the
frame length from the number of characters you give it, so a code padded to 32 bits is
transmitted as a 32-bit frame and the fan ignores it.

Both values are printed by the rc_switch dumper, which the example YAML leaves enabled:

```text
Received RCSwitch Raw: protocol=1 data='000100110101000110100011'
                                ^ rc_protocol   ^ 24 characters = rc_code_bits
```

> Changing the shape a gateway emits **invalidates every code already learned**: matching
> is exact string equality. Relearn them (**⋮ → Reconfigure → Relearn RF codes**) after
> touching `rc_code_bits`, `rc_protocol`, or the `rc_code` lambda.

### Raw-timings gateways (remotes rc_switch cannot decode)

rc_switch only understands fixed-sync PWM protocols. A remote using another
modulation — Manchester/biphase, and several manufacturer schemes — produces no
`on_rc_switch` event at all: the log shows `remote.raw` timing dumps and never a
`Received RCSwitch Raw:` line, so Home Assistant is never told about the frame.

For those, [esphome/rf_fan_raw_gateway.yaml](esphome/rf_fan_raw_gateway.yaml) captures
the frame's raw transitions and replays them verbatim:

```text
raw:150,-5839,1144,-370,1148,-367,…
```

signed microseconds, positive for a mark, negative for a space. The integration is
unaffected — a code is an opaque string either way.

> **Following the physical remote does not work with raw codes, and cannot.** Raw
> frames jitter by a few microseconds between presses, and matching a sniffed frame
> against a learned one is exact string equality. Transmit works; passive state
> tracking does not. If rc_switch decodes your remote, prefer the standard gateway.

The raw gateway also rate-limits what it publishes (`rx_min_interval_ms`) and ignores
bursts shorter than `min_transitions`. A remote repeats its frame for as long as the
button is held, and one API call per repeat is enough to fill the ESPHome queue —
`Action request dropped, TCP buffer full` in the log is that, not a crash.

## Project structure

```text
custom_components/rf_fan/
  __init__.py        actions.py       config_flow.py   const.py
  data.py            diagnostics.py   entity.py        manifest.json
  fan.py             light.py         select.py        sensor.py
  button.py          switch.py
  strings.json       translations/{en,fr}.json
  brand/             icon.png  icon@2x.png  logo.png
  frontend/          rf-fan-card.js   (bundled dashboard card)
blueprints/automation/rf_fan/
  fan_temperature_control.yaml
esphome/
  rf_fan_example.yaml          native cc1101:, separate RX/TX pins (recommended)
  rf_fan_radiolib_legacy.yaml  RadioLib external component, single shared GDO0
scripts/
  Dockerfile.tests   run-tests.ps1    run-tests.sh
tests/
  test_actions.py    (pure logic, runs anywhere — no Home Assistant needed)
  test_*.py          (entities, config flow, diagnostics, blueprint — need phcc)
  ha_helpers.py      (shared fixtures for the phcc tests)
  frontend/          card tests, run by `node --test` against a DOM stub
```

## Brand icon

The integration ships its own icon/logo in
[`custom_components/rf_fan/brand/`](custom_components/rf_fan/brand/). Since Home
Assistant 2026.3, custom integrations serve local brand images directly (they take
priority over the brands CDN), so no submission to `home-assistant/brands` is needed.
Supported files: `icon.png` / `icon@2x.png` / `logo.png` (+ optional
`dark_icon.png` / `dark_logo.png`).

## Known limitations

- No generic rolling-code support.
- No native RF acknowledgement — state is assumed, not confirmed.
- The protocols that actually work depend on what your ESPHome gateway can sniff and
  replay correctly.
- **The reference gateway replays on one fixed rc_switch protocol and bit width.** Both
  are substitutions (`rc_protocol`, `rc_code_bits`) rather than a per-code property, so a
  single gateway cannot serve two remotes of different geometry. Fans whose timings match
  none of the eight built-in rc_switch protocols need an inline `protocol:` block with
  measured `pulse_length` / `sync` / `zero` / `one` values — see
  [Troubleshooting](#troubleshooting). A remote rc_switch cannot decode at all is served
  by the [raw-timings gateway](#raw-timings-gateways-remotes-rc_switch-cannot-decode),
  at the cost of physical-remote tracking. The integration itself is unaffected either
  way: it treats codes as opaque strings.
- **No rolling or incrementing codes.** One action maps to exactly one code, and two
  actions may not share one. A remote whose frame changes on every press (a counter, or
  a rotating suffix) cannot be learned.
- A physical press of the very button Home Assistant just triggered is ignored for
  `ECHO_SUPPRESS_SEC` (see `const.py`) — that window is what discards the gateway's echo
  of our own transmission. Pressing any *other* button is honoured immediately.

## Troubleshooting

The fan never reports anything back, so every state you see is dead-reckoned from the
commands sent. When it drifts, **Settings → Devices & services → RF Fan → ⋮ → Download
diagnostics** dumps what the integration currently believes, under `runtime`:

| Field | Meaning |
| --- | --- |
| `kelvin_position` / `colour` | assumed position in the colour cycle |
| `light_on` | assumed light state (`null` until a command or a sniffed frame settles it) |
| `timer_ends_at` | assumed switch-off time, or `null` |
| `armed_echo_codes` | codes whose echo window is still open — a remote press of one of those is being discarded on purpose |
| `last_unmatched_code` | the last sniffed frame that matched no learned code — see below |

### The physical remote does not update anything

Following the remote is exact string matching between the sniffed code and the learned
ones, so it fails silently and completely when the two are shaped differently. Compare
`last_unmatched_code` in the diagnostics against the `codes` listed above it:

- **`null` while pressing the remote** — nothing is reaching Home Assistant. Confirm the
  `esphome.rf_fan_received` event actually fires (Developer Tools → Events), then that
  its `device` field matches the gateway this entry was set up against.
- **A code that looks nothing like the learned ones** (decimal vs `1:0011…`, or a
  different number of bits) — the gateway YAML changed since those codes were learned.
  Relearn them.
- **A code that differs from a learned one by one bit or a leading zero** — `rc_code_bits`
  is wrong. Read the true width off the `dump: rc_switch` log line and relearn.

Enabling debug logging for `custom_components.rf_fan` prints the same comparison
(unmatched code plus every learned code) on each newly unrecognised frame.

### The fan ignores a code that was learned correctly

The bits are right and the *timings* are wrong. This is the most common failure after a
successful capture, and the reason it is confusing is worth stating plainly:

> **That the gateway decodes your remote does not mean it can replay to your fan.**
> The receiver is configured with `tolerance: 50%`, so it happily reports
> `protocol=6` for a remote whose pulses are 25 % off protocol 6's nominal timings.
> Your fan has no such tolerance. Reception proves the *shape* of the code, never the
> numbers.

So `rc_protocol: "6"` in the YAML means "transmit using protocol 6's **stock** timings",
which may be nothing like what your remote actually emits. Measure, then replace the
protocol number with an inline block.

Capture the original with `rtl_433 -A`, which prints the pulse/gap breakdown, or read the
durations out of a `remote_receiver` raw dump. Then:

```yaml
protocol:
  pulse_length: 400   # the short pulse, in µs (rtl_433's short_width)
  sync: [1, 18]
  zero: [1, 3]
  one: [3, 1]
  inverted: true      # SEE BELOW - omitting this defaults to false
```

**`inverted:` is the half everybody forgets.** It selects whether a bit is
*pulse-then-gap* (`false`) or *gap-then-pulse* (`true`). Get it wrong and every frame goes
out inside out: bit-perfect, correctly timed, and ignored by the fan. Nothing in the
receive log warns you, because receiving never exercises it.

The flag is **a property of the protocol you are replacing, not a free choice.** When you
swap `rc_protocol: "N"` for an inline block you must carry over protocol N's own value.
Read it off the last argument of the matching row in ESPHome's protocol table
([`remote_base/rc_switch_protocol.h`](https://github.com/esphome/esphome/blob/dev/esphome/components/remote_base/rc_switch_protocol.h)) —
for example protocol 6 is declared `RCSwitchBase(10350, 450, 450, 900, 900, 450, true)`,
so an inline replacement for it needs `inverted: true`.

<details>
<summary>Worked example: a 9-speed Hampton Bay remote (issue #59)</summary>

The gateway logged `protocol=6` and every replay was ignored. Two things were wrong at
once, and each alone was enough to break it:

- the remote's real unit is **335 µs**, not protocol 6's nominal 450 — measured over
  1734 durations, which landed on 335 and 666 (ratio 1.99). Only `tolerance: 50%` on the
  receiver made it decode at all;
- the transmit block said `inverted: false`, while protocol 6 is `inverted: true`.

The fix keeps protocol 6's ratios and flag and changes only the unit:

```yaml
protocol:
  pulse_length: 335
  sync: [31, 1]
  zero: [1, 2]
  one: [2, 1]
  inverted: true
```

Confirmed on the reporter's hardware.
</details>

### The fan obeys Developer Tools but ignores the dashboard

**Raise the repeat count** under **⋮ → Reconfigure**. This is the same code, correctly
timed, simply not repeated enough — and it is invisible, because nothing here is ever
confirmed by the fan, so a burst that falls on deaf ears produces no error anywhere.

Some receivers ignore a frame that is bit-perfect but sent fewer times than the original
remote sends it, and the threshold differs **between keys on one remote**: on the first
remote anyone measured, the light obeyed a short burst while the speeds needed three
frames (#59).

The integration sends each frame `repeat_count` times, **default 3**. One subtlety if
you tune it: a *toggle* action (light, sound, reverse, natural, any free-form key) is
rounded **down to the nearest odd number**, so that the fan ends up flipped exactly once
whichever way its receiver counts a burst. A configured `4` therefore sends four frames
for a speed and three for a toggle — and a configured `2` sends a single frame for every
toggle, which is why the default is not 2.

A drifted colour position is resynced with the **calibrate** button (it emits nothing, it
just resets the assumption to Warm). A button that was mis-captured is fixed with
**⋮ → Reconfigure → Relearn RF codes**.

## Development

The pure logic tests (`tests/test_actions.py`) run anywhere:

```bash
python -m pytest tests/test_actions.py -q
```

Everything else needs a Home Assistant test environment
(`pytest-homeassistant-custom-component`). Those modules skip themselves cleanly when it
is unavailable, so the pure suite never breaks — but they are most of the coverage, so
run the full suite before pushing. Home Assistant's runner imports the POSIX-only
`fcntl`, so on Windows it has to go through Docker:

```powershell
.\scripts\run-tests.ps1            # whole suite, same image as CI
.\scripts\run-tests.ps1 tests/test_echo_suppression.py -q
.\scripts\run-tests.ps1 -Rebuild   # after editing requirements-test.txt
```

```bash
sh scripts/run-tests.sh            # same thing from a POSIX shell
```

On Linux/macOS a plain `pip install -r requirements-test.txt && python -m pytest tests/`
works too.

The bundled card has its own tests. They need no dependency and no build step — the card
is rendered against a minimal DOM stub by node's built-in runner:

```bash
node --test "tests/frontend/*.test.mjs"
```

CI runs all three (ruff, pytest, card) on every push and pull request.

## License

See [LICENSE](LICENSE).
