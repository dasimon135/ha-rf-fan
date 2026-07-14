# RF Fan — Home Assistant integration

A **generic** Home Assistant integration for RF (typically 433 MHz) ceiling and wall
fans that have no manufacturer-specific integration. You pair it with an ESPHome
gateway that can transmit — and ideally receive — the raw RF frames, then teach Home
Assistant your remote button by button.

It is deliberately protocol-agnostic: the integration stores your codes as **opaque
strings** and replays them through the ESPHome gateway. It does not care whether the
frames are `rc_switch`, raw timings, or anything else the gateway understands. A
Cecotec fan is used as the reference example, but any RF fan works.

<p align="center">
  <img src="custom_components/rf_fan/brand/icon@2x.png" width="128" alt="RF Fan icon">
</p>

## Features

- **Config flow** — no YAML to write.
- **Two setup methods**: paste already-sniffed codes manually, or **guided learning**
  from remote button presses (via ESPHome events).
- **Declarative capabilities** — you only get asked for the buttons your fan actually
  has:
  - Discrete fan speeds (3–6).
  - Optional light: none / single toggle / separate on & off buttons.
  - Optional dedicated fan "on" button.
  - Optional **reverse direction**, **natural-airflow preset**, **color temperature
    (Kelvin)**, **sleep timers** (1/2/4/8 h), and **sound** toggle.
- **Reconfigure in place** — add or change capabilities on an existing entry and learn
  only the new buttons, keeping the codes you already captured (see below).
- **Assumed state** (`assumed_state`) with dead-reckoning, plus partial state sync when
  the physical remote is used (if the gateway reports received frames).
- **Configurable RF repeat count**.

## Entities

Depending on the declared capabilities, a device exposes:

| Entity | When | Notes |
| --- | --- | --- |
| `fan` | always | discrete speeds; gains `direction` and a `natural` preset when enabled |
| `light` | light ≠ none | on/off; toggle- or on/off-driven |
| `select` "color temperature" | color temp enabled | cycles Warm → Neutral → Cold |
| `button` calibrate | color temp enabled | resyncs the assumed color position — **emits nothing** |
| `button` timer ×4 | timers enabled | 1 h / 2 h / 4 h / 8 h |
| `switch` sound | sound enabled | beep on/off |

### Color temperature (Kelvin)

The remote's Kelvin button *cycles* the color, so the integration tracks an **assumed
position** (dead-reckoning). To change the color, use the **"color temperature"
dropdown** and pick a value *different* from the one shown — picking the current value
sends nothing. The **calibrate button never emits RF**: it only tells Home Assistant
"the lamp is now on Warm", to re-align the dropdown if it drifts (set the lamp to Warm
physically, then press it). The color only changes visibly when the light is on.

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
| GDO0 | GPIO4 — data (RX **and** TX) |
| GDO2 | unused |

The radio is driven by the
[`esphome-radiolib-cc1101`](https://github.com/juanboro/esphome-radiolib-cc1101)
external component at 433.92 MHz; GDO0 (GPIO4) carries both transmit and receive data.
A 433 MHz antenna is required. A full working config is in
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

## Reconfiguring an existing fan

To add a capability (or fix a captured code) later, open the integration entry and use
**⋮ → Reconfigure** (on the *RF Fan* integration card, not the device page):

1. Re-declare the capabilities (existing values are pre-filled) and enable the new ones.
2. On the review screen you see what will be **learned** (newly required buttons),
   **kept** (existing codes — tick a box to re-learn one), and **removed**.
3. Choose learning or manual entry; only the delta is asked for.
4. The entry reloads in place — your dashboards and automations keep working.

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

## Project structure

```text
custom_components/rf_fan/
  __init__.py        actions.py       config_flow.py   const.py
  entity.py          fan.py           light.py         select.py
  button.py          switch.py        manifest.json
  strings.json       translations/{en,fr}.json
  brand/             icon.png  icon@2x.png  logo.png
  frontend/          rf-fan-card.js   (bundled dashboard card)
esphome/
  rf_fan_example.yaml
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

## Development

Pure logic tests run anywhere:

```bash
python -m pytest tests/test_actions.py -q
```

The config-flow tests require `pytest-homeassistant-custom-component` (a Home Assistant
test environment) and skip cleanly when it is unavailable.

## License

See [LICENSE](LICENSE).
