"""A control whose code was never learned answers the press (#87).

Learning lets a key be skipped after a timeout, which is how someone gets past a
key their remote does not have. The entry is then created with whatever was
captured, so a control can exist with no code behind it. Pressing it used to send
nothing and say nothing, at any log level a user would see.

It now raises a translated error naming the key and the fan, which Home Assistant
shows where the press was made. The keys that are optional by design keep falling
back silently: `fan_on` (a speed key starts the fan) and `fan_off_reverse`
(`fan_off` stops it), because there the press still does what was asked.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.rf_fan.const import DOMAIN
from tests.ha_helpers import (
    actions_sent,
    button_id,
    id_by_unique_suffix,
    on_off_entry,
    one_id,
    register_stub,
    relative_entry,
    setup_full,
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _forget(hass: HomeAssistant, entry, action: str) -> None:
    """Drop one learned code and reload, as a skipped key during learning leaves it."""
    codes = {key: value for key, value in entry.data["codes"].items() if key != action}
    hass.config_entries.async_update_entry(entry, data={**entry.data, "codes": codes})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


def _assert_not_learned(err: pytest.ExceptionInfo, action: str, fan_name: str) -> None:
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "action_not_learned"
    assert err.value.translation_placeholders == {"action": action, "fan_name": fan_name}


async def test_a_timer_button_without_a_code_says_so(hass: HomeAssistant) -> None:
    """The press is answered, and no switch-off time is claimed."""
    entry, calls = await setup_full(hass)
    await _forget(hass, entry, "timer_4h")
    sensor = one_id(hass, "sensor")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "button", "press", {"entity_id": button_id(hass, "4h")}, blocking=True
        )

    _assert_not_learned(err, "timer_4h", "Full")
    assert actions_sent(calls) == []
    assert hass.states.get(sensor).state == "unknown"


async def test_a_speed_without_a_code_says_so(hass: HomeAssistant) -> None:
    """The fan state is left where it was: nothing reached the fan."""
    entry, calls = await setup_full(hass)
    await _forget(hass, entry, "fan_speed_2")
    fan = one_id(hass, "fan")
    before = hass.states.get(fan)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "fan", "set_percentage", {"entity_id": fan, "percentage": 66}, blocking=True
        )

    _assert_not_learned(err, "fan_speed_2", "Full")
    assert actions_sent(calls) == []
    after = hass.states.get(fan)
    assert (after.state, after.attributes.get("percentage")) == (
        before.state,
        before.attributes.get("percentage"),
    )


async def test_a_two_key_light_names_the_key_it_is_missing(hass: HomeAssistant) -> None:
    """With neither `light_off` nor a toggle key, the error names `light_off`.

    That is the key the reconfigure recap lists as "to learn" for this remote;
    naming `light_toggle`, which it never had, would send the user looking for it.
    """
    calls = register_stub(hass)
    entry = on_off_entry(hass)
    codes = {key: value for key, value in entry.data["codes"].items() if key != "light_off"}
    hass.config_entries.async_update_entry(entry, data={**entry.data, "codes": codes})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    light = one_id(hass, "light")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "light", "turn_off", {"entity_id": light}, blocking=True
        )

    _assert_not_learned(err, "light_off", "OnOff")
    assert actions_sent(calls) == []


async def test_a_stepping_walk_without_its_key_says_so(hass: HomeAssistant) -> None:
    """A walk is a run of presses; the first one that cannot be made ends it, loudly."""
    calls = register_stub(hass)
    entry = relative_entry(hass, light_level_steps=4)
    codes = {
        key: value for key, value in entry.data["codes"].items() if key != "light_bright_down"
    }
    hass.config_entries.async_update_entry(entry, data={**entry.data, "codes": codes})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    resync = id_by_unique_suffix(hass, entry, "button", "brightness_calibrate")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "button", "press", {"entity_id": resync}, blocking=True
        )

    _assert_not_learned(err, "light_bright_down", "Relative")
    assert actions_sent(calls) == []


async def test_a_fan_on_key_that_was_skipped_still_falls_back(hass: HomeAssistant) -> None:
    """`fan_on` is optional by design: a speed key starts the fan, so no error."""
    _entry, calls = await setup_full(hass, extra_data={"has_fan_on": True})
    fan = one_id(hass, "fan")

    await hass.services.async_call("fan", "turn_on", {"entity_id": fan}, blocking=True)
    await hass.async_block_till_done()

    assert actions_sent(calls) == ["fan_speed_1"]
    assert hass.states.get(fan).state == "on"
