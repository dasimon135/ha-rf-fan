"""A toggle-only lamp is not flipped towards the state it is believed to be in.

"Hey Google, turn off the lights" calls `light.turn_off` on every exposed light,
including a lamp Home Assistant already believes off. On a remote whose only light
key is `light_toggle`, pressing it there lit the lamp while the state stayed off.

The lamp here is the Cecotec shape: one toggle key, no brightness steps. The belief
is set through the "Assumed light state" select, which transmits nothing, so every
frame captured afterwards comes from the call under test.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from tests.ha_helpers import actions_sent as _actions_sent
from tests.ha_helpers import id_by_unique_suffix as _id_by
from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import setup_full as _setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _setup_believing(hass: HomeAssistant, belief: str):
    """A toggle-only lamp whose belief was declared `belief`, with no frame sent."""
    entry, calls = await _setup_full(hass)
    light_id = _one_id(hass, "light")
    select_id = _id_by(hass, entry, "select", "_light_state")
    await _declare(hass, select_id, belief)
    assert calls == []
    return light_id, select_id, calls


async def _declare(hass: HomeAssistant, select_id: str, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": option}, blocking=True
    )
    await hass.async_block_till_done()


async def _power(hass: HomeAssistant, light_id: str, service: str) -> None:
    await hass.services.async_call("light", service, {"entity_id": light_id}, blocking=True)
    await hass.async_block_till_done()


async def test_turning_off_a_lamp_believed_off_sends_nothing(hass: HomeAssistant) -> None:
    """The reported case: the voice command lit a lamp that was already dark."""
    light_id, select_id, calls = await _setup_believing(hass, "off")

    await _power(hass, light_id, "turn_off")

    assert _actions_sent(calls) == []
    assert hass.states.get(light_id).state == "off"
    assert hass.states.get(select_id).state == "off"


async def test_turning_on_a_lamp_believed_on_sends_nothing(hass: HomeAssistant) -> None:
    """The mirror case: a second "on" would have switched the lamp off."""
    light_id, select_id, calls = await _setup_believing(hass, "on")

    await _power(hass, light_id, "turn_on")

    assert _actions_sent(calls) == []
    assert hass.states.get(light_id).state == "on"
    assert hass.states.get(select_id).state == "on"


async def test_turning_on_a_lamp_believed_off_presses_once(hass: HomeAssistant) -> None:
    """A real change presses the toggle once, and both entities follow it."""
    light_id, select_id, calls = await _setup_believing(hass, "off")

    await _power(hass, light_id, "turn_on")

    assert _actions_sent(calls) == ["light_toggle"]
    assert hass.states.get(light_id).state == "on"
    assert hass.states.get(select_id).state == "on"


async def test_turning_off_a_lamp_believed_on_presses_once(hass: HomeAssistant) -> None:
    """The other real change."""
    light_id, select_id, calls = await _setup_believing(hass, "on")

    await _power(hass, light_id, "turn_off")

    assert _actions_sent(calls) == ["light_toggle"]
    assert hass.states.get(light_id).state == "off"
    assert hass.states.get(select_id).state == "off"


async def test_declaring_the_state_never_transmits(hass: HomeAssistant) -> None:
    """The nightly resynchronisation: the select corrects the belief, never the lamp."""
    light_id, select_id, calls = await _setup_believing(hass, "off")
    await _power(hass, light_id, "turn_on")
    calls.clear()

    for option in ("off", "on", "on", "off"):
        await _declare(hass, select_id, option)
        assert hass.states.get(light_id).state == option

    assert _actions_sent(calls) == []
