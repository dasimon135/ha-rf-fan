# Free-form extra buttons — design

Issue: [#18](https://github.com/dasimon135/ha-rf-fan/issues/18), asked for by @elmr91.
Status: designed, not implemented. Target: 1.9.0.

## The boundary this rests on

Typed capabilities stay typed. Speed, direction, colour, brightness and the airflow
preset are things Home Assistant has a concept of, and a typed entity works in
scenes, in voice assistants, in every native card and in the more-info dialog. Two
buttons labelled "Light +" and "Light −" work in none of them.

The free-form layer is for the remainder: keys that do something neither Home
Assistant nor this integration can describe — @elmr91's "memory" key is the
reported case. For those, a named button is not a lesser entity, it is the only
honest one.

So this adds a second layer; it never replaces the first.

## Entity model

One `button` entity per extra key.

- `unique_id = {entry_id}_extra_N`
- displayed name = the user's label (`_attr_name`)
- `translation_key = "extra"`, kept so the card can recognise them without guessing
- pressing transmits `extra_N` at the configured `repeat_count`, as an **absolute**
  code: nothing is known about whether the key toggles anything, and rounding the
  count down to odd would be one more assumption.

No `switch`, no `number`, no restored state. A key whose effect is unknowable cannot
have an assumed state — a "memory on" checkbox would display a belief nothing can
establish or correct. Rejected for the same reason: a `±` pair, which past the typed
colour and brightness controls would only ever be a press counter with no meaning.

## Storage and config flow

Two keys in the config entry:

```yaml
extra_count: 2
extra_names: {extra_1: "Mémoire", extra_2: "Ionisation"}
codes: {…, extra_1: "0x1A2B3C", extra_2: "0x1A2B40"}
```

`split_actions()` gains `extra_count` and requires `extra_1…extra_N`. **No migration**:
an absent key means zero.

**Capped at 8.** Not only UI prudence: the translations test requires every reachable
action to carry a label in all three files, and an unbounded count would make that
guarantee impossible to keep. Eight rows × (label + `relearn_`) × three files is
finite and checkable.

**Naming step**, shown only when the count is above zero: N text fields, pre-filled
with the existing names on a reconfigure. A blank field falls back to "Extra key N"
rather than failing the flow — a configuration is not blocked over a label.

**A limitation to state plainly.** In the learning screen a field's label comes from
the translation keyed by the field name, so `extra_1` reads "Extra key 1", not
"Mémoire": Home Assistant has no per-field placeholder. The remedy is the step's
`description_placeholders` — the text above the form lists `1 = Mémoire · 2 =
Ionisation`. Less pretty than the name in the field, honest, and invents nothing.

**Reconfigure**: the count is a length, never a renumbering. Going from 3 to 2 makes
`extra_3` "forgotten" — the existing mechanism drops its code and its registry row.
`extra_2`'s code is never reassigned to what used to be `extra_3`.

## The card

**Identified by key, never by elimination.** The chips are the buttons whose registry
entry says `translation_key === "extra"`. That is the #29 lesson: the "the button
that is not a timer" fallback drove the colour row into the brightness resync, and
pressing that walks the lamp down to its end stop. Where the registry exposes no
translation keys at all — exactly @elmr91's install — **no chips are drawn**. Drawing
nothing is recoverable; firing the wrong RF code is not.

**Rendering**: a row at the bottom of the full card, one chip per key, in `extra_1…N`
order — the remote's order, not alphabetical. The label is the entity's
`friendly_name`, so the user's own name, without the integration having to pass it to
the card. Text ellipsised past the available width; the row wraps past three.

A pleasant consequence: **the card gains no translated string**. Its internal
two-language table does not move, where every previous feature added labels to it —
and that is where three omissions have already shipped.

**Click**: `button.press` on the entity, the same path as the timers and the
calibrate button.

**Tile layout excluded**: it fits on one line by construction, and N buttons of
varying width overflow it at two keys.

**No card option** to hide the row: it exists only when there are extra keys, and a
fan without any sees exactly today's card.

## Verification

**Pure tests** — `split_actions(extra_count=N)` requires `extra_1…extra_N` and
nothing else; zero requires none; the count is clamped on read as the step counts
already are, because stored data outlives the form that validated it.
`expected_unique_ids` gains a row per key and loses it when the count shrinks.

**Home Assistant tests** — pressing transmits `extra_N` at the configured repeat
count **without** the toggle rounding; the displayed name is the user's label; a
blank label falls back to the generic name.

**Flow tests** — the naming step appears only above zero; names survive a
reconfigure; and above all: **reducing the count from 3 to 2 forgets `extra_3` and
leaves the codes of 1 and 2 untouched**. That is the guarantee that matters — a
silent renumbering would make a button emit another button's code, and nothing in
the interface would say so.

**Translations** — the existing test derives the action space from `split_actions`
and fails when a reachable action has no label. Adding the count to the product it
walks makes all sixteen entries (`extra_1..8` and their `relearn_` twins) required in
the three files automatically. That guard has already caught three omissions.

**Card tests** — chips drawn from the translation key; **nothing drawn** when the
registry exposes no keys; the click calls `button.press` on the right entity; the
order follows `extra_N`; absent from the tile layout.
