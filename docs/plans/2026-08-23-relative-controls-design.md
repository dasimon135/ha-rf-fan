# Relative controls, power toggle, and generic extra buttons — design

Date: 2026-08-23 · Baseline: `1.7.0`, 80 Python tests + 11 card tests green

Scopes three gaps that came out of the forum thread and the issue tracker, all of
them the same shape: a remote whose buttons **move** a value instead of **setting**
one, or whose power is a single toggle.

| Source | Remote | What does not fit today |
| --- | --- | --- |
| [#18](https://github.com/dasimon135/ha-rf-fan/issues/18) @elmr91 | Inspire Aruba Plus | Colour ± and brightness ± are two dedicated keys, not one cycling key |
| [#18](https://github.com/dasimon135/ha-rf-fan/issues/18) @elmr91 | idem | Winter/summer sends **no code**: the remote stores the mode and emits 6 speed codes per direction |
| [forum #29/#33](https://community.home-assistant.io/t/1017083/33) @Ltek | CHQ7225T, 9 speeds | Power is one toggle; speed is + / − ; and `speed_count` is capped at 6 |

Nothing here requires the integration to understand a protocol. Codes stay opaque
strings, as always.

---

## 1. Decisions taken, and why

**Relative and discrete speed are mutually exclusive**, selected by one field
mirroring the existing `light_control`. `FanEntity` has a single speed feature
(`SET_SPEED`) and a single contract (`percentage` / `async_set_percentage` /
`percentage_step`) — there is no step-only fan feature in Home Assistant, so both
modes produce an identical entity from the outside. `media_player` does expose
`VOLUME_SET` and `VOLUME_STEP` together, but only because Home Assistant renders
both; there is no relative fan UI to render, so a second path would be invisible.
A remote that genuinely has both is served by picking `discrete` and not learning
the ± keys — nothing observable is lost.

**Brightness is its own field, not a fifth value of `light_control`.** Home
Assistant's own light model separates `ColorMode.ONOFF` from
`ColorMode.BRIGHTNESS`: brightness is a capability dimension, not a control style.
The repo already treats colour that way (`has_color_temp` is separate from
`light_control`). Folding them would give `none / toggle / on_off / toggle_dim /
on_off_dim` — enum multiplication, ten values as soon as a third dimension appears.
The fields are not strictly orthogonal (brightness is meaningless without a light),
which is handled by **not asking**: the field only appears in the capabilities step
when a light was declared.

**Typed capabilities where Home Assistant has a concept, generic buttons for the
rest.** @elmr91 proposed replacing typed capabilities with user-labelled generic
ones. Taken all the way that costs too much: a brightness pair modelled as two
labelled buttons is invisible to scenes, to voice, and to every native light card.
But he is right that the tail is long, and every exotic remote should not need a
release. So: typed for brightness / colour / speed / direction, and a free list of
extra buttons for what Home Assistant cannot name — memory, boost, manufacturer
oddities.

---

## 2. Configuration schema

Three fields replace booleans, three are new.

| Field | Values | Replaces |
| --- | --- | --- |
| `power_control` | `off_only` · `on_off` · `toggle` | `has_fan_on` |
| `speed_control` | `discrete` · `relative` | — |
| `direction_control` | `none` · `toggle` · `per_speed` | `has_direction` |
| `color_control` | `none` · `cycle` · `relative` | `has_color_temp` |
| `light_level` | `none` · `relative` | — |
| `speed_count` | **2–12** | `vol.In([3, 4, 5, 6])` |
| `extra_buttons` | list of `{label, kind, codes}` | — |

The speed cap goes because there is no technical reason for it: relative mode needs
two codes whatever N, and discrete mode with 9 speeds is only tedious to learn.

`direction_control: per_speed` is @elmr91's case: the direction is not an action at
all, it is a **dimension of the speed code set**. Learning becomes `fan_speed_N`
forward plus `fan_speed_N_reverse`. Worth the extra learning steps because it makes
direction **absolute** — `async_set_direction` today carries a comment admitting it
cannot guarantee an absolute target from an unknown state. Here it can.

> `per_speed` requires `speed_control: discrete`, and the config flow refuses the
> other combination. A per-direction pair of ± keys is a shape nobody has reported,
> and guessing at it would double the action set for a remote that may not exist.

### New actions

```
fan_power_toggle
fan_speed_up        fan_speed_down
fan_speed_1_reverse … fan_speed_N_reverse
light_bright_up     light_bright_down
light_kelvin_up     light_kelvin_down
extra_<slug>        extra_<slug>_up / extra_<slug>_down
```

`split_actions` loses its only current certainty: `fan_off` is no longer
unconditional. It becomes `off_only` → `fan_off`, `on_off` → `fan_off` + `fan_on`,
`toggle` → `fan_power_toggle` alone.

None of the step actions belong in `TOGGLE_ACTIONS`. A step is absolute, not a flip:
it keeps the full `repeat_count` for reliability, exactly as `light_kelvin` does
today. What makes a receiver count steps separately is `STEP_GAP_SEC`, not the
repeat count.

---

## 3. The walk mechanism

`select.py` already dead-reckons a position and walks to a target. This extracts it
rather than inventing it.

The arithmetic goes into `actions.py`, so it is testable without Home Assistant:

```python
def walk_steps(current, target, size, *, wrap) -> tuple[str, int]
```

`wrap` is what separates a cycle from a range. Colour wraps — shortest path in
either direction. Speed and brightness clamp — the direction follows the sign.
`current is None` (position unknown) still emits: a relative control with an unknown
position is usable, it just says so.

`entity.py` gains the transport half, next to `_async_transmit_times`:

```python
async def _async_walk(self, up, down, current, target, size, *, wrap) -> int
```

It emits one key per step with `STEP_GAP_SEC` between them — today's
`KELVIN_STEP_GAP_SEC`, generalised — and returns the position actually reached.

Assumed positions join `RfFanRuntimeData` beside `kelvin_position`:

```python
speed_position: int | None = None
level_position: int | None = None
```

### Concurrency — the one piece of genuinely new code

An 8-step walk takes several seconds. Move the slider again during it and two walks
interleave, leaving the assumed position wrong. `select.py` has this bug today; with
3 colours it is rare, with 9 speeds it will be routine.

An `asyncio.Lock` per config entry, with *restart* semantics: the running walk is
cancelled, the assumed position is set to **what actually went on the air** (hence
`_async_walk` returning it), then the new walk starts from there.

> **Verify before coding, not after:** whether the Home Assistant slider sends values
> continuously during a drag or only on release. If continuously, every drag becomes
> a cascade of cancelled walks and the lock semantics may need to change to
> "coalesce" rather than "restart".

---

## 4. Entities

**`fan.py`** — `async_set_percentage` branches on `speed_control`. In `relative` the
target index is computed exactly as now, then `_async_walk` moves from
`speed_position`. `percentage_step` is unchanged (`100 / speed_count`), so the Home
Assistant slider behaves identically. `set_percentage(0)` still turns off.

With `power_control: toggle`, `turn_on` / `turn_off` only emit when the assumed state
justifies it — the same caution as the sound switch and `light_toggle` today. A wrong
assumption inverts the command; that is inherent to the hardware.

With `direction_control: per_speed`, the direction is part of the code lookup:
`speed_action(index, direction)`. `current_direction` becomes known rather than
dead-reckoned.

**`light.py`** — `ColorMode.BRIGHTNESS` when `light_level: relative`, `ONOFF`
otherwise. `turn_on(brightness=…)` maps 0–255 onto `level_steps` and walks.

**`select.py`** — `cycle` keeps today's single key; `relative` takes both keys and
the shortest path.

**Four new entities, all `EntityCategory.CONFIG`** (the convention the sound switch
and the colour calibrate button already follow, so they group under *Configuration*
on the device page and stay off dashboards):

| Entity | Behaviour |
| --- | --- |
| `button` Resynchronise speed | `fan_speed_down` × (N−1), then position = 0 |
| `select` Assumed speed position | declares, emits nothing |
| `button` Resynchronise brightness | same on `light_bright_down` |
| `select` Assumed brightness position | declares, emits nothing |

N−1 steps reach the stop from anywhere, and the extra presses do nothing once
there. **Document plainly:** on many remotes, stepping below speed 1 stops the fan.
The resync is audible and visible — that is the price of physical truth over a
declaration. Colour gains its position select for symmetry; its calibrate button
already exists and keeps declaring, since a cycle has no end stop.

**Extra buttons** create one entity each: `kind: button` → `button`, `kind: toggle`
→ `switch` (assumed state, in `TOGGLE_ACTIONS`), `kind: pair` → two `button`s. Named
from the user's label. The bundled card picks them up through the same device walk
it already does for the other siblings.

**Following the physical remote** — `_handle_rf_event` learns the new actions:
`fan_power_toggle` flips, the four `_up` / `_down` move the assumed position by one
(clamping or wrapping). This is where relative mode is *better* than discrete: every
physical press is a known delta, whereas an absolute speed code is only recognised if
it was learned.

`expected_unique_ids` in `actions.py` must list the new ids, or disabling a
capability leaves ghost rows — the bug already fixed in 1.6.0.

---

## 5. Migration

`async_migrate_entry` already exists and is written as cumulative steps
(`if entry.version < 2:`). Version 3 slots in: the `entry.version > 2` guard becomes
`> 3`, and one block translates the booleans.

```
has_fan_on: true       → power_control: on_off
has_fan_on: false      → power_control: off_only
has_direction: true    → direction_control: toggle
has_direction: false   → direction_control: none
has_color_temp: true   → color_control: cycle
has_color_temp: false  → color_control: none
(always)               → speed_control: discrete
                         light_level: none
                         extra_buttons: []
```

**No learned code is invalidated.** Existing action keys (`fan_off`,
`fan_speed_1`…, `light_kelvin`, `fan_reverse`) keep their exact names. After the
v1.7.0 relearn, nobody should have to do it again.

---

## 6. Tests

- **`test_actions.py`** (pure, runs anywhere) — `split_actions` parametrised over the
  selector combinations; `walk_steps` across cycle, range, clamping, unknown
  position; `expected_unique_ids` with the new entities; extra-button slug
  generation and collision handling.
- **`test_entities.py`** — relative speed end to end (counting frames and gaps, like
  today's colour test); brightness; the resync button; and the restart case: start a
  walk, start a second during it, assert the final position is right.
- **`test_migration.py`** — v2 → v3 over the boolean combinations.

Repo rule, unchanged: any behaviour change ships with a test that failed before it.

---

## 7. Delivery

**v1.8.0** — `power_control`, `speed_control: relative`, speed cap to 12, the walk
mechanism, the lock, the CONFIG entities. Unblocks @Ltek entirely; he is the one
waiting.

**v1.9.0** — `light_level`, `color_control: relative`, `direction_control:
per_speed`. Closes #18 for @elmr91.

**v1.10.0** — `extra_buttons` and their card support.

The mechanism lands in 1.8.0; 1.9.0 only rewires it onto the light and the direction.

---

## 8. Open risks

- **@Ltek's ± keys may not send two fixed codes.** If the frame changes as the range
  is walked, the whole relative-speed half collapses into the rolling-code case,
  which is explicitly out of scope. Asked on the forum; unanswered at the time of
  writing. **Do not start v1.8.0 before that answer.**
- **Slider behaviour during a drag** (see §3) — decides the lock semantics.
- **Entity count.** Twelve entities on a fully-loaded fan today, up to sixteen after
  1.9.0. `EntityCategory.CONFIG` keeps them off dashboards, but the device page is
  getting long.
