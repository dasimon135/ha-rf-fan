"""`natural_control: dedicated` — an airflow key that SETS a mode (#34).

Measured by @elmr91 on his Inspire Aruba Plus, over three corrections:

> Natural mode (called "mode brise" in French) is not a toggle: it behaves as a
> dedicated speed. Pressing twice the key has no effect: fan remains in natural mode.

> natural key only works when fan is already on […] in order to start natural mode:
> select any speed key to start fan, then press natural key.

> when fan is in natural mode, pressing a speed key changes the speed of the fan
> (so leaving natural mode).

So the key resembles a speed key in the two ways that matter here — it *sets*
instead of flipping, and a speed key is what takes the fan back out — but it is not
a member of the speed set, because it cannot start the fan.

Everything below is asserted on the frames that went on the air, not only on the
resulting state: the fan never reports back, so the assumed preset is only ever
worth the presses it counted.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from custom_components.rf_fan.const import EVENT_RF_FAN_RECEIVED
from tests.ha_helpers import DEVICE
from tests.ha_helpers import actions_sent as _actions_sent
from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import setup_relative as _setup_relative


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _setup_dedicated(hass: HomeAssistant):
    """A remote of @elmr91's shape: per-speed direction, and a dedicated airflow key."""
    return await _setup_relative(hass, natural_control="dedicated")


async def _running_at_full_speed(hass: HomeAssistant, calls: list) -> str:
    """Start the fan, since the airflow key does nothing while it is stopped."""
    fan_id = _one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 100}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()
    return fan_id


async def _fire(hass: HomeAssistant, code: str) -> None:
    """Simulate one frame from the physical remote."""
    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": code, "action": "sniff"}
    )
    await hass.async_block_till_done()


async def _press_again(hass: HomeAssistant, entry, code: str) -> None:
    """Fire the SAME code as a second deliberate press rather than a repeat.

    A press puts its frame on the air several times and the receiver de-bounces
    them per code, over a window measured on `hass.loop.time()` that no test clock
    moves. Ageing the record is the same statement as waiting (see
    `test_receive_debounce`).
    """
    seen = entry.runtime_data.receive_seen
    for known in seen:
        seen[known] -= 10.0
    await _fire(hass, code)


async def test_entering_natural_presses_the_airflow_key(hass: HomeAssistant) -> None:
    """Entering is the one part a set key and a toggle key agree on."""
    _entry, calls = await _setup_dedicated(hass)
    fan_id = await _running_at_full_speed(hass, calls)

    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == ["fan_natural"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"


async def test_leaving_natural_sends_a_speed_rather_than_the_airflow_key(
    hass: HomeAssistant,
) -> None:
    """Pressing the airflow key again does nothing on the hardware; a speed key is the way out.

    This is the whole defect: on a `toggle` remote Home Assistant leaves the preset
    by pressing the same key twice, and on a remote of this shape that press is
    swallowed — the fan stays in breeze and Home Assistant believes it left.
    """
    _entry, calls = await _setup_dedicated(hass)
    fan_id = await _running_at_full_speed(hass, calls)
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "normal"}, blocking=True
    )
    await hass.async_block_till_done()

    # Speed 3 of 3: the speed the fan was already running at, re-sent.
    assert _actions_sent(calls) == ["fan_speed_3"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"


async def test_a_second_airflow_frame_leaves_the_preset_where_it_is(
    hass: HomeAssistant,
) -> None:
    """A set key pressed twice sets twice. Following it as a flip drifts one press at a time."""
    entry, calls = await _setup_dedicated(hass)
    fan_id = await _running_at_full_speed(hass, calls)

    await _fire(hass, "r_nat")
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"

    await _press_again(hass, entry, "r_nat")
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"


async def test_choosing_a_speed_leaves_the_preset(hass: HomeAssistant) -> None:
    """A speed key takes the fan out of breeze, so the assumed preset has to follow."""
    _entry, calls = await _setup_dedicated(hass)
    fan_id = await _running_at_full_speed(hass, calls)
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 33}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"
    assert hass.states.get(fan_id).attributes["percentage"] == 33


async def test_a_speed_pressed_on_the_remote_leaves_the_preset(hass: HomeAssistant) -> None:
    """The same, tracked passively: the remote is the other way the fan gets its orders."""
    _entry, calls = await _setup_dedicated(hass)
    fan_id = await _running_at_full_speed(hass, calls)
    await _fire(hass, "r_nat")
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"

    await _fire(hass, "r_s2")

    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"
    assert hass.states.get(fan_id).attributes["percentage"] == 67


async def test_a_preset_asked_for_while_the_fan_is_off_is_carried_by_the_next_start(
    hass: HomeAssistant,
) -> None:
    """The key does nothing while the fan is stopped, so the intent waits for the start.

    Mirrors what `direction_control: per_speed` already does: record now, act on the
    code that goes on the air next. Transmitting into a fan that cannot hear it would
    leave the integration believing in a preset the fan never entered.
    """
    _entry, calls = await _setup_dedicated(hass)
    fan_id = _one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": fan_id}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == [], "the airflow key is deaf while the fan is off"

    await hass.services.async_call(
        "fan", "turn_on", {"entity_id": fan_id}, blocking=True
    )
    await hass.async_block_till_done()

    # The speed starts the fan; the airflow key can only be heard afterwards.
    assert _actions_sent(calls)[-1] == "fan_natural"
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"


async def test_a_toggle_remote_still_toggles(hass: HomeAssistant) -> None:
    """The shape that exists today is untouched: both directions press the same key."""
    _entry, calls = await _setup_relative(hass, natural_control="toggle")
    fan_id = await _running_at_full_speed(hass, calls)

    for preset in ("natural", "normal"):
        await hass.services.async_call(
            "fan",
            "set_preset_mode",
            {"entity_id": fan_id, "preset_mode": preset},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert _actions_sent(calls) == ["fan_natural", "fan_natural"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"
