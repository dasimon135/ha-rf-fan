# Post #1 réécrit — prêt à coller (community.home-assistant.io/t/1017083)

Tout ce qui suit la ligne de séparation remplace le corps du post d'origine.
Résumé des changements : `post-community-op-update.md`.

---

## Introduction

Hey everyone!

Following my [Dooya RF433 blinds write-up](https://community.home-assistant.io/t/control-dooya-rf433-blinds-with-esp32-cc1101-via-esphome), here's the same **ESP32 + CC1101** approach applied to a **433 MHz ceiling fan** (mine is a **Cecotec**, but it's fully generic).

This time I went a step further and built a dedicated **Home Assistant custom integration** — **"RF Fan"** — so you don't have to hand-sniff and paste codes. HA **learns each remote button for you** through a guided flow, and you get proper `fan` and `light` entities, plus optional **timers, colour temperature (Kelvin), sound, reverse direction and natural-airflow** — and an animated dashboard card that ships with it.

**Result**: full fan + light control from HA, no cloud, no proprietary hub, for ~$10 of hardware. Works with any RF fan whose remote uses a fixed code, not just Cecotec.

> :bulb: **Updated for v1.7.0 (August 2026).** The wiring, the radio component and the shape of the RF codes all changed since the original write-up — thanks to @elmr91, @Relutzzzu and @Ltek, who found the problems in this thread. If you built this before, see *What changed in v1.7.0* near the end.

---

## Hardware

| Component | Approx. Price | Source |
| --- | --- | --- |
| ESP32 DevKit V1 (or clone) | ~$4 | AliExpress |
| CC1101 433 MHz module (green E07, 8 pins) | ~$3 | AliExpress |
| Dupont jumper wires (female-female) | ~$2 | AliExpress |
| 433 MHz antenna (or a ~17.3 cm wire) | cents | — |
| Micro-USB cable + 5 V charger | already have | — |

**Total: ~$10.** A small plastic enclosure is nice for the final install.

> :warning: The CC1101 is a **3.3 V** module — do **not** power it from 5 V.

The antenna goes on the **CC1101**, not the ESP32 — the ESP32 has no 433 MHz radio. Solder a ~17.3 cm wire (quarter-wave for 433.92 MHz) to the **ANT** pad, unless your module already has a spring antenna or an SMA connector.

---

## Wiring: ESP32 + CC1101

**Use two separate data pins — one for TX, one for RX.**

| CC1101 Pin | Name | ESP32 GPIO |
| --- | --- | --- |
| 1 | GND | GND |
| 2 | VCC | 3V3 |
| 3 | GDO0 | GPIO 4 — **transmit** data |
| 4 | CSN | GPIO 5 |
| 5 | SCK | GPIO 18 |
| 6 | MOSI | GPIO 23 |
| 7 | MISO | GPIO 19 |
| 8 | GDO2 | GPIO 13 — **receive** data |

> :warning: **This is the single most common way to get stuck.** Wiring both directions onto GDO0 also "works" on paper, but that one pin then has to be re-moded on every RX/TX switch, and on ESP32 that can leave `remote_receiver` permanently deaf — no decoded frames, not even background noise. If your gateway transmits fine but hears absolutely nothing, rule this out first. Already built with one shared pin? [`esphome/rf_fan_radiolib_legacy.yaml`](https://github.com/dasimon135/ha-rf-fan/blob/main/esphome/rf_fan_radiolib_legacy.yaml) keeps that scheme working.

There are two common 8-pin CC1101 modules. Check **pin 2**: green **E07** = VCC, blue **Standard** = GND. On the blue module the GPIOs are the same, only the pin *positions* differ — match by **name**, never by number.

On other boards, remap freely: only SCLK/MOSI/MISO are fixed by the chip; CS and the two GDO pins can be any free GPIO. On an ESP32-C3 SuperMini, avoid the strapping pins (GPIO2, GPIO8, GPIO9).

---

## Step 1 — Flash the ESPHome gateway

The gateway does two jobs: it **transmits** the fan's RF frames (via a `transmit_rf_fan` service) and **listens** so Home Assistant can learn your buttons (it fires an `rf_fan_received` event).

The radio is driven by ESPHome's **built-in [`cc1101`](https://esphome.io/components/cc1101.html) component** at 433.92 MHz — no external component to install any more.

A complete, working config is in the repo: **[esphome/rf_fan_example.yaml](https://github.com/dasimon135/ha-rf-fan/blob/main/esphome/rf_fan_example.yaml)**.

If the sniff captures nothing at all, your remote may not be on 433.92 — try 433.42 or 434.42 via the `cc1101_frequency` substitution.

---

## Step 2 — Read your protocol number and bit width

**Don't skip this one.** It is the difference between codes that replay and codes that go out as nonsense.

The example ships with `dump: rc_switch` enabled on purpose. Open the ESPHome log, press any button on the remote, and look for:

```text
Received RCSwitch Raw: protocol=1 data='000100110101000110100011'
```

Two values to copy into the substitutions at the top of the YAML:

```yaml
rc_protocol: "1"     # the protocol=N value
rc_code_bits: "24"   # how many characters are inside data='...'
```

Why it matters: `on_rc_switch` hands the frame over as a 64-bit **integer** and throws the bit **length** away. Returning that integer directly gives you its decimal form (`645080348`), while `transmit_rc_switch_raw` reads its input as a *bit string*, one character per bit — so the frame goes out as a handful of meaningless bits. And the length cannot be recovered afterwards, because a code starting with zeros is indistinguishable from a shorter one. Hence: declare it, exactly.

Reflash after setting these two. Once guided learning works you can set `dump: []` to quieten the log.

[details="rc_switch reports one bit fewer than my remote sends"]
On some remotes the last bit runs straight into the inter-frame gap and the decoder drops it. Set `rc_code_bits` to what **is** decoded, and rebuild the missing trailing bit in the lambda. For a 30-bit frame whose last bit is an even parity over the other 29 (thanks @elmr91 for working this one out):

```yaml
int ones = 0;
for (char c : bits) ones += (c == '1');
bits += (ones & 1) ? '1' : '0';
```
[/details]

---

## Step 3 — Install the RF Fan integration (HACS)

1. HACS → three-dots → **Custom repositories**
2. Add `https://github.com/dasimon135/ha-rf-fan` — category **Integration**
3. Install **RF Fan**, then **restart** Home Assistant
4. Settings → Devices & Services → **Add Integration** → *RF Fan*

Requires Home Assistant **2026.5+**.

---

## Step 4 — Set up & learn your remote

In the config flow:

1. Pick your **ESPHome gateway** (auto-detected).
2. **Declare what your remote can do** — number of speeds, light style (none / single toggle / separate on & off), and tick any of: reverse direction, natural airflow, colour temperature, sleep timers, sound. You're only asked for the buttons you actually have.
3. Choose **Guided learning** and **press each button** on the physical remote when prompted — the gateway captures the frame, HA stores it. **No YAML.** (Manual paste is also available.)

Need to add a capability later? Use **⋮ → Reconfigure** on the integration entry — it learns only the *new* buttons and keeps the codes you already captured, or relearns a single mis-captured one.

> :warning: **Any change to the gateway's `rc_code` lambda, `rc_protocol` or `rc_code_bits` invalidates every code you have already learned.** Matching a received frame against a learned one is exact string equality, so a code stored in the old shape will simply never match again. After touching the YAML: **⋮ → Reconfigure → Relearn RF codes**.

---

## What you get in HA

- a `fan` entity with speed control (+ direction and a natural preset if enabled)
- a `light` entity
- a colour-temperature **select** (+ a small calibrate button)
- a **sound** switch, and **timer** buttons (1/2/4/8 h)

State is **assumed** — the fan sends nothing back — but it is **restored across restarts**, and when you use the physical remote the integration follows along by matching the sniffed frame against the learned codes.

If that following stops working, **Settings → Devices & services → RF Fan → ⋮ → Download diagnostics** now has a `runtime.last_unmatched_code` field: the last frame that matched nothing. Compare it with the learned codes listed just above it and the mismatch is usually obvious — a decimal where you expect `1:0011…`, or the wrong number of bits.

---

## The dashboard card

The integration **ships its own animated card** — nothing to install, no resource to register. On a dashboard, add a card and pick **RF Fan Card** from the picker, or in YAML:

```yaml
type: custom:rf-fan-card
entity: fan.living_room_fan
```

`entity` is the only required field. The card walks up to that fan's device and auto-discovers the siblings (light, colour select, sound, timers), showing only the controls that exist. Blades spin at a speed-proportional rate, it follows your HA theme, and there is a visual editor. Three layouts via `layout:` — `full` (default), `compact`, and `tile` (one row that lines up with HA's native tiles).

[details="Prefer Mushroom? The original card YAML"]
Needs [Mushroom](https://github.com/piitaya/lovelace-mushroom) + [vertical-stack-in-card](https://github.com/ofekashery/vertical-stack-in-card) from HACS. Adjust entity IDs to yours.

```yaml
type: custom:vertical-stack-in-card
cards:
  - type: custom:mushroom-fan-card
    entity: fan.living_room_fan
    name: Living Room Fan
    icon_animation: true
    show_percentage_control: true
    show_oscillate_control: false
    collapsible_controls: false
  - type: grid
    columns: 2
    square: false
    cards:
      - type: custom:mushroom-light-card
        entity: light.living_room_fan_light
        name: Light
        icon_color: amber
        show_brightness_control: false
      - type: custom:mushroom-select-card
        entity: select.living_room_fan_color_temperature
        name: Colour
        icon: mdi:thermometer-lines
  - type: custom:mushroom-chips-card
    alignment: center
    chips:
      - type: template
        entity: fan.living_room_fan
        icon: mdi:fan
        content: Normal
        icon_color: "{{ 'blue' if state_attr('fan.living_room_fan','preset_mode') != 'natural' else 'disabled' }}"
        tap_action:
          action: perform-action
          perform_action: fan.set_preset_mode
          target: { entity_id: fan.living_room_fan }
          data: { preset_mode: normal }
      - type: template
        entity: fan.living_room_fan
        icon: mdi:weather-windy
        content: Natural
        icon_color: "{{ 'blue' if state_attr('fan.living_room_fan','preset_mode') == 'natural' else 'disabled' }}"
        tap_action:
          action: perform-action
          perform_action: fan.set_preset_mode
          target: { entity_id: fan.living_room_fan }
          data: { preset_mode: natural }
      - type: template
        entity: fan.living_room_fan
        icon: mdi:rotate-right
        content: Forward
        icon_color: "{{ 'blue' if state_attr('fan.living_room_fan','direction') != 'reverse' else 'disabled' }}"
        tap_action:
          action: perform-action
          perform_action: fan.set_direction
          target: { entity_id: fan.living_room_fan }
          data: { direction: forward }
      - type: template
        entity: fan.living_room_fan
        icon: mdi:rotate-left
        content: Reverse
        icon_color: "{{ 'blue' if state_attr('fan.living_room_fan','direction') == 'reverse' else 'disabled' }}"
        tap_action:
          action: perform-action
          perform_action: fan.set_direction
          target: { entity_id: fan.living_room_fan }
          data: { direction: reverse }
  - type: custom:mushroom-chips-card
    alignment: center
    chips:
      - type: entity
        entity: switch.living_room_fan_sound
        icon: mdi:volume-high
        content_info: name
        tap_action: { action: toggle }
      - type: entity
        entity: button.living_room_fan_timer_1h
        icon: mdi:timer-outline
        content_info: name
        tap_action:
          action: perform-action
          perform_action: button.press
          target: { entity_id: button.living_room_fan_timer_1h }
      - type: entity
        entity: button.living_room_fan_timer_2h
        icon: mdi:timer-outline
        content_info: name
        tap_action:
          action: perform-action
          perform_action: button.press
          target: { entity_id: button.living_room_fan_timer_2h }
      - type: entity
        entity: button.living_room_fan_timer_4h
        icon: mdi:timer-outline
        content_info: name
        tap_action:
          action: perform-action
          perform_action: button.press
          target: { entity_id: button.living_room_fan_timer_4h }
      - type: entity
        entity: button.living_room_fan_timer_8h
        icon: mdi:timer-outline
        content_info: name
        tap_action:
          action: perform-action
          perform_action: button.press
          target: { entity_id: button.living_room_fan_timer_8h }
      - type: entity
        entity: button.living_room_fan_recalibrate_color
        icon: mdi:target-variant
        content_info: name
        tap_action:
          action: perform-action
          perform_action: button.press
          target: { entity_id: button.living_room_fan_recalibrate_color }
```
[/details]

---

## Honest limitations

- **Assumed state** — no RF acknowledgement from the fan; commands are one-way, HA tracks a best-effort state.
- **Fixed codes only.** A remote whose frame changes on every press — a rolling code, or a counter in a few bits — cannot be learned: one action maps to exactly one code. If four presses of the same button give you four different frames, that is this case.
- **Only what rc_switch can decode.** The gateway hears a frame through `on_rc_switch`, so a remote using a modulation rc_switch has no decoder for — Manchester/biphase, for instance — produces no event at all: the log shows raw timings and nothing else. `rtl_433 -A` on one press tells you what you are dealing with in one line.
- **One protocol and one bit width per gateway.** `rc_protocol` and `rc_code_bits` are substitutions, not per-code properties, so a single gateway cannot serve two remotes of different geometry.
- **RX can be noisy** depending on your local 433 MHz environment; **TX is reliable**.
- **The default rc_switch timings do not fit every fan.** If a code is learned correctly but the fan ignores it, the frame is being replayed with the wrong *timings*, not the wrong bits — capture the original with `rtl_433 -A` and replace the protocol number with the measured values. There is a worked example in the repo's Troubleshooting section.

---

## What changed in v1.7.0

If you built this from the original write-up, three things moved:

1. **Separate RX/TX pins** (GDO2 → GPIO13 for receive). The old shared-GDO0 wiring is why several people in this thread ended up with a completely deaf receiver.
2. **The gateway now emits `<protocol>:<bits>`** instead of the raw integer — see Step 2. **Reflash, then relearn every code.**
3. **Toggle buttons honour `repeat_count`** (rounded down to an odd value) instead of always going out once, so receivers that drop a lone frame now see `light_toggle`.

---

## Conclusion

Same spirit as the Dooya build — ~$10 of hardware, 100% local, no cloud. The difference here is a real **custom integration** doing the heavy lifting (guided learning, proper entities, reconfigure, state restore, bundled card), so it should be approachable even if you have never sniffed an RF code.

Code (integration + ESPHome example): **https://github.com/dasimon135/ha-rf-fan**

Feel free to ask if you have any questions! :slightly_smiling_face: And if you try it on a different RF fan, I'd love to hear whether it works for you.

---

*Tested with: ESPHome 2026.x / ESP-IDF 5.x / ESP32 DevKit v1 / CC1101 E07 green module / Home Assistant 2026.5+ / RF Fan 1.7.0*

*— Built and debugged with Claude* :slight_smile:
