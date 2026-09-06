"""Natural airflow that comes in LEVELS, as preset modes (#61).

@Ltek's Hampton Bay remote has Breeze 1, 2 and 3 where this integration only ever
modelled one airflow key. The measurement that decides the model was never taken;
his own capture document answered it instead, and the answer is in the frames:

    Speed 5   0101111000000010 0101 010000
    Breeze 2  0101111000000010 1100 010000

A Breeze level and a speed number are values of the SAME four-bit field, carried
with the same six-bit key field. One field holds one value, so from Breeze 2 the
Speed 5 key puts the code already stored as Speed 5 on the air, byte for byte, and
the fan cannot still be in Breeze afterwards.

That is exactly what `natural_control: dedicated` already means (#34, measured by
@elmr91 on a remote with one level): the key SETS, and a speed key is what leaves.
Levels generalise that, and nothing else about it changes.

Everything below is asserted on the frames that went on the air, not only on the
resulting state: the fan never reports back, so an assumed preset is only ever
worth the presses it counted.
"""

from __future__ import annotations

import pytest

from custom_components.rf_fan.actions import natural_level_count, split_actions

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.rf_fan.const import DOMAIN, EVENT_RF_FAN_RECEIVED
from tests.ha_helpers import DEVICE
from tests.ha_helpers import actions_sent as _actions_sent
from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import setup_relative as _setup_relative

# Three levels, forward and reverse, exactly as @Ltek captured them.
LEVEL_CODES = {
    "fan_natural_1": "r_n1",
    "fan_natural_2": "r_n2",
    "fan_natural_3": "r_n3",
    "fan_natural_1_reverse": "r_n1r",
    "fan_natural_2_reverse": "r_n2r",
    "fan_natural_3_reverse": "r_n3r",
}


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _setup_levels(hass: HomeAssistant, levels: int = 3):
    """A remote of @Ltek's shape: per-speed direction, three airflow levels."""
    return await _setup_relative(
        hass,
        natural_control="dedicated",
        extra_data={"natural_levels": levels},
        extra_codes=dict(LEVEL_CODES),
    )


async def _running_at_full_speed(hass: HomeAssistant, calls: list) -> str:
    """Start the fan: a `dedicated` airflow key is deaf while it is stopped."""
    fan_id = _one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 100}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()
    return fan_id


async def _set_preset(hass: HomeAssistant, fan_id: str, preset: str) -> None:
    await hass.services.async_call(
        "fan",
        "set_preset_mode",
        {"entity_id": fan_id, "preset_mode": preset},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _fire(hass: HomeAssistant, code: str) -> None:
    """Simulate one frame from the physical remote."""
    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": code, "action": "sniff"}
    )
    await hass.async_block_till_done()


# --------------------------------------------------------------- which codes


def test_levels_replace_the_single_airflow_key() -> None:
    """A remote that has three Breeze keys does not also have an unnumbered one."""
    required, _ = split_actions(
        3, "none", natural_control="dedicated", natural_levels=3
    )

    assert "fan_natural" not in required
    assert [a for a in required if a.startswith("fan_natural")] == [
        "fan_natural_1",
        "fan_natural_2",
        "fan_natural_3",
    ]


def test_levels_take_a_reverse_set_on_a_per_speed_remote() -> None:
    """The winter half of every level, the same rule the speeds follow."""
    required, _ = split_actions(
        3,
        "none",
        direction_control="per_speed",
        natural_control="dedicated",
        natural_levels=2,
    )

    assert [a for a in required if a.startswith("fan_natural")] == [
        "fan_natural_1",
        "fan_natural_2",
        "fan_natural_1_reverse",
        "fan_natural_2_reverse",
    ]


def test_a_single_level_is_spelled_zero() -> None:
    """One level IS the historical shape, under the name it has always had.

    Offering both would be two ways to declare one remote, differing only in which
    code has to be learned -- so a stray 1 falls back rather than inventing a
    `fan_natural_1` nobody has been asked to teach.
    """
    required, _ = split_actions(
        3, "none", natural_control="dedicated", natural_levels=1
    )

    assert "fan_natural" in required
    assert "fan_natural_1" not in required


def test_a_level_count_is_clamped_on_read() -> None:
    """Stored data outlives the dropdown that validated it."""
    assert natural_level_count({}) == 0
    assert natural_level_count({"natural_levels": "3"}) == 3
    assert natural_level_count({"natural_levels": 1}) == 0
    assert natural_level_count({"natural_levels": -4}) == 0
    assert natural_level_count({"natural_levels": 99}) == 6
    assert natural_level_count({"natural_levels": "brise"}) == 0


# ------------------------------------------------------------- the entity


async def test_the_preset_menu_is_one_entry_per_level(hass: HomeAssistant) -> None:
    """`normal` plus one preset per declared level, and no bare `natural`."""
    await _setup_levels(hass)

    fan_id = _one_id(hass, "fan")
    modes = hass.states.get(fan_id).attributes["preset_modes"]

    assert modes == ["normal", "natural 1", "natural 2", "natural 3"]


async def test_setting_a_level_sends_that_level_key(hass: HomeAssistant) -> None:
    """The key that SETS level two, and only it."""
    _, calls = await _setup_levels(hass)
    fan_id = await _running_at_full_speed(hass, calls)

    await _set_preset(hass, fan_id, "natural 2")

    assert _actions_sent(calls) == ["fan_natural_2"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural 2"


async def test_a_level_follows_the_direction_the_fan_runs_in(
    hass: HomeAssistant,
) -> None:
    """A `per_speed` remote gives every level a code per direction, like the speeds."""
    _, calls = await _setup_levels(hass)
    fan_id = await _running_at_full_speed(hass, calls)
    await hass.services.async_call(
        "fan",
        "set_direction",
        {"entity_id": fan_id, "direction": "reverse"},
        blocking=True,
    )
    await hass.async_block_till_done()
    calls.clear()

    await _set_preset(hass, fan_id, "natural 3")

    assert _actions_sent(calls) == ["fan_natural_3_reverse"]


async def test_a_level_asked_for_while_stopped_is_deferred(
    hass: HomeAssistant,
) -> None:
    """The key is deaf while the fan is stopped, so the press waits for the start.

    A press that cannot land must not be counted as one -- but the intent is shown,
    the way a direction chosen with the fan off is.
    """
    _, calls = await _setup_levels(hass)
    fan_id = _one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": fan_id}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    await _set_preset(hass, fan_id, "natural 1")

    assert _actions_sent(calls) == []
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural 1"

    await hass.services.async_call("fan", "turn_on", {"entity_id": fan_id}, blocking=True)
    await hass.async_block_till_done()

    assert "fan_natural_1" in _actions_sent(calls)


async def test_a_speed_press_leaves_the_levelled_preset(hass: HomeAssistant) -> None:
    """The whole model, in one assertion: a speed value replaces a level value."""
    _, calls = await _setup_levels(hass)
    fan_id = await _running_at_full_speed(hass, calls)
    await _set_preset(hass, fan_id, "natural 2")
    calls.clear()

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 33}, blocking=True
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == ["fan_speed_1"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"


async def test_leaving_the_preset_resends_the_current_speed(
    hass: HomeAssistant,
) -> None:
    """There is no "leave" key: the way out is the speed the fan already runs at."""
    _, calls = await _setup_levels(hass)
    fan_id = await _running_at_full_speed(hass, calls)
    await _set_preset(hass, fan_id, "natural 3")
    calls.clear()

    await _set_preset(hass, fan_id, "normal")

    assert _actions_sent(calls) == ["fan_speed_3"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"


async def test_hearing_a_level_key_records_it_without_starting_the_fan(
    hass: HomeAssistant,
) -> None:
    """The airflow key cannot start the fan, so hearing one must not claim it did."""
    _, calls = await _setup_levels(hass)
    fan_id = _one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": fan_id}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    await _fire(hass, "r_n3")

    state = hass.states.get(fan_id)
    assert state.attributes["preset_mode"] == "natural 3"
    assert state.state == "off"
    assert _actions_sent(calls) == []


async def test_hearing_a_reverse_level_key_records_the_direction_too(
    hass: HomeAssistant,
) -> None:
    """Like a reverse speed code, a winter level code says which way the fan runs."""
    _, calls = await _setup_levels(hass)
    fan_id = await _running_at_full_speed(hass, calls)

    await _fire(hass, "r_n2r")

    state = hass.states.get(fan_id)
    assert state.attributes["preset_mode"] == "natural 2"
    assert state.attributes["direction"] == "reverse"


async def test_pressing_the_same_level_twice_does_not_flip_it(
    hass: HomeAssistant,
) -> None:
    """A levelled key SETS. Following it as a toggle would drift by one press."""
    _, calls = await _setup_levels(hass)
    fan_id = await _running_at_full_speed(hass, calls)

    await _fire(hass, "r_n1")
    await _fire(hass, "r_n1")

    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural 1"


async def test_a_remote_with_one_airflow_key_is_untouched(
    hass: HomeAssistant,
) -> None:
    """Declaring no levels must leave the shape that shipped exactly as it was."""
    await _setup_relative(hass, natural_control="dedicated")

    fan_id = _one_id(hass, "fan")

    assert hass.states.get(fan_id).attributes["preset_modes"] == ["normal", "natural"]


# ------------------------------------------------------------- the config flow


async def _submit_capabilities(hass: HomeAssistant, **extra):
    """Answer the first screen, with the airflow answers under test."""
    hass.services.async_register(
        "esphome", "esp32_test_transmit_rf_fan", lambda call: None
    )
    await hass.async_block_till_done()

    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "esphome_device": "esp32-test",
            "fan_name": "Breeze",
            "speed_count": 3,
            **extra,
        },
    )
    return flow, result


async def test_levels_without_a_key_that_sets_are_refused(
    hass: HomeAssistant,
) -> None:
    """A level IS a value, and a key that merely flips carries none.

    Refused rather than quietly dropped: accepting it would learn the wrong keys
    for a remote nobody can model, and which half of the answer was meant is not
    guessable from the form.
    """
    _flow, result = await _submit_capabilities(
        hass, natural_control="toggle", natural_levels=3
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"natural_levels": "natural_levels_need_dedicated"}


async def test_levels_with_a_dedicated_key_are_asked_for(hass: HomeAssistant) -> None:
    """Declaring three levels puts three level codes on the form to fill in."""
    flow, result = await _submit_capabilities(
        hass, natural_control="dedicated", natural_levels=3
    )
    assert result["step_id"] == "method"

    result = await flow.async_configure(result["flow_id"], {"method": "manual"})

    asked = [str(key) for key in result["data_schema"].schema]
    assert "fan_natural" not in asked
    assert [a for a in asked if a.startswith("fan_natural")] == [
        "fan_natural_1",
        "fan_natural_2",
        "fan_natural_3",
    ]
