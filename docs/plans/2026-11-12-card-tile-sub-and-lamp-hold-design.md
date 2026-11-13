# Card: a tile that says more, and the lamp belief corrected from it

Date: 2026-11-12. Agreed with the maintainer before any code.

## Why

The tile layout is how the card is used on the maintainer's own dashboard, and it
hides two things the full card shows:

- the secondary line says `Speed 3/6`, `On` or `Off`, never the airflow preset or
  that a timer is running;
- a toggle-only lamp drifts away from what Home Assistant believes, and the only
  way to tell it so is the `light_state` select, buried in the device page. The
  maintainer runs a night automation on an illuminance sensor for that alone.

## 1. Secondary line

- Running: `Speed 3/6`, then ` · Natural` (or `Natural 2`) when the preset is
  not `normal`, then ` · until 22:30` when the timer sensor holds an end time.
- Stopped: `Off`, nothing else. A timer means nothing on a stopped fan, and since
  1.10.5 an elapsed timer stops the fan anyway.
- The end time, not the time left: the card only re-renders on a state change,
  and an end time stays right without a ticking clock. Formatted in Home
  Assistant's language (`hass.locale`).
- Built by a pure `_tileSub()`, so it is tested without a DOM.

## 2. Long press on the tile's lamp button

- A short press is unchanged: it sends the code.
- A press held 500 ms selects the opposite of the lamp's current state on the
  `light_state` select, found by its translation key (it is a CONFIG entity, so
  the colour row's filter correctly leaves it out). Nothing goes on the air.
- The click that ends the hold is swallowed, with the `_held` flag the fan button
  already uses for its long press.
- Feedback: Home Assistant's own toast (`hass-notification`), saying the lamp is
  now marked on or off and that nothing was sent, and a `haptic` event. The icon
  follows by itself, since the light entity follows the select.
- No `light_state` select (a fan without a lamp, or an older version): the long
  press does nothing special.
- The mobile context menu is suppressed on that button.

Rejected: a row in the popup (two gestures, not on the tile), and both at once
(more surface for a gesture the maintainer wants on the tile).

## Tests

Node card tests: the secondary line in each case (running, stopped, preset,
timer, timer unknown), discovery by translation key, a long press calling
`select.select_option` and not `light.toggle`, a short press unchanged.

## Release

A capability a user would look for: 2.1.0. Validated on the maintainer's
instance through a rendered screenshot, and the gesture by hand, since a long
press is not faithfully simulated.
