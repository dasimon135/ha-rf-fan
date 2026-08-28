"""Declaring the lamp's on/off state, without touching the lamp (#45).

A single-key lamp has no feedback, so Home Assistant's belief and the lamp can
disagree at any time. Pressing OFF fixes that by *moving the hardware*: it works
when you are in the room and the lamp is lit, and not at all otherwise.

@elmr91 asked for the other kind, and named the precedent himself: the colour and
brightness positions already have a control that declares where the hardware is and
emits nothing. This is the same thing for the one assumed state that lacked it.

A select rather than a button, and `on`/`off` rather than a flip, because it is
absolute: you say which state the lamp is in. Today's other lesson was what flips
cost when the belief is already wrong.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_fan.const import DOMAIN
from tests.ha_helpers import CODES, DEVICE
from tests.ha_helpers import id_by_unique_suffix as _id_by
from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import register_stub as _register_stub
from tests.ha_helpers import setup_full as _setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _declare(hass: HomeAssistant, select_id: str, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": option}, blocking=True
    )
    await hass.async_block_till_done()


async def test_declaring_the_state_moves_the_belief_and_nothing_else(
    hass: HomeAssistant,
) -> None:
    """The whole point: the lamp is not touched, only what Home Assistant thinks."""
    entry, calls = await _setup_full(hass)
    light_id = _one_id(hass, "light")
    select_id = _id_by(hass, entry, "select", "_light_state")

    await _declare(hass, select_id, "on")

    assert calls == [], "declaring a state must not put anything on the air"
    assert hass.states.get(light_id).state == "on"
    assert hass.states.get(select_id).state == "on"


async def test_the_declaration_follows_the_lamp(hass: HomeAssistant) -> None:
    """It reads the same belief it writes, so it never contradicts the light entity."""
    entry, _calls = await _setup_full(hass)
    light_id = _one_id(hass, "light")
    select_id = _id_by(hass, entry, "select", "_light_state")
    assert hass.states.get(select_id).state == "unknown", "nothing is known yet"

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(select_id).state == "on"

    await hass.services.async_call(
        "light", "turn_off", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(select_id).state == "off"


async def test_declaring_off_reaches_the_rest_of_the_integration(
    hass: HomeAssistant,
) -> None:
    """The belief is shared: the colour select gates on it, and must follow.

    Not a detail -- a declaration that only convinced the light entity would leave
    the colour row usable on a lamp the user has just said is dark.
    """
    entry, _calls = await _setup_full(hass)
    light_id = _one_id(hass, "light")
    colour_id = _id_by(hass, entry, "select", "_color_temp")
    select_id = _id_by(hass, entry, "select", "_light_state")
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(colour_id).state != "unavailable"

    await _declare(hass, select_id, "off")

    assert hass.states.get(colour_id).state == "unavailable"


async def test_it_declares_the_integration_s_belief_not_the_fan(
    hass: HomeAssistant,
) -> None:
    """`EntityCategory.CONFIG`, like its two siblings -- and the card relies on it.

    The colour row picks its select by refusing every CONFIG one; a declaration
    entity that forgot to say so would be a candidate for that row again (#29).
    """
    from homeassistant.helpers import entity_registry as er

    entry, _calls = await _setup_full(hass)
    select_id = _id_by(hass, entry, "select", "_light_state")

    registered = er.async_get(hass).async_get(select_id)

    assert registered.entity_category == er.EntityCategory.CONFIG


async def test_a_fan_without_a_light_gets_no_declaration(hass: HomeAssistant) -> None:
    """There is no belief to declare, so there is no entity to declare it with."""
    _register_stub(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bare",
        data={
            "esphome_device": DEVICE,
            "fan_name": "Bare",
            "speed_count": 3,
            "light_control": "none",
            "has_light": False,
            "codes": {key: value for key, value in CODES.items() if not key.startswith("light")},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(AssertionError):
        _id_by(hass, entry, "select", "_light_state")
