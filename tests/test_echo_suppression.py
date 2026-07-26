"""Anti-echo behaviour (requires a Home Assistant environment via phcc).

The gateway sniffs its own transmissions, so every command Home Assistant sends
comes back as an `esphome.rf_fan_received` event a moment later. That echo must
not be mistaken for a physical remote press — for the toggle actions
(`light_toggle`, `sound_toggle`, `fan_reverse`, `fan_natural`) it would flip the
assumed state straight back.

Suppression is keyed on the transmitted CODE, not on a blanket time window over
all reception, so a genuine remote press of a *different* button right after a
Home Assistant command is still honoured.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from tests.ha_helpers import fire_rf, one_id, setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def test_remote_press_of_a_different_code_is_honoured(hass: HomeAssistant) -> None:
    """A remote press right after a HA command must not be swallowed.

    Home Assistant toggles the light (transmits `c_lt`); immediately afterwards the
    user presses speed 2 on the physical remote (`c_s2`). That is a different code,
    so it cannot be an echo of our own transmission and must update the fan.
    """
    await setup_full(hass)
    light_id = one_id(hass, "light")
    fan_id = one_id(hass, "fan")

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()

    await fire_rf(hass, "c_s2")

    fan = hass.states.get(fan_id)
    assert fan.state == "on"
    # speed 2 of 3 → round(2 * 100/3) == 67
    assert fan.attributes["percentage"] == 67


async def test_echo_of_the_transmitted_code_does_not_flip_the_light(
    hass: HomeAssistant,
) -> None:
    """The echo of our own `light_toggle` must not toggle the light back off."""
    await setup_full(hass)
    light_id = one_id(hass, "light")

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(light_id).state == "on"

    # The gateway sniffs the frame it just sent and reports it back.
    await fire_rf(hass, "c_lt")

    assert hass.states.get(light_id).state == "on"


async def test_repeated_echoes_of_one_transmission_are_all_suppressed(
    hass: HomeAssistant,
) -> None:
    """`repeat_count` > 1 produces several echoes; every one of them must be ignored.

    Suppression must therefore not be consumed by the first entity that sees the
    event: all four platforms listen to the same bus event.
    """
    await setup_full(hass, repeat_count=3)
    fan_id = one_id(hass, "fan")

    await hass.services.async_call(
        "fan", "set_direction", {"entity_id": fan_id, "direction": "reverse"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(fan_id).attributes["direction"] == "reverse"

    for _ in range(3):
        await fire_rf(hass, "c_rev")

    assert hass.states.get(fan_id).attributes["direction"] == "reverse"


async def test_echo_window_expires(hass: HomeAssistant, monkeypatch) -> None:
    """Once the window has elapsed, the same code counts as a real remote press."""
    monkeypatch.setattr("custom_components.rf_fan.entity.ECHO_SUPPRESS_SEC", 0.0)

    await setup_full(hass)
    light_id = one_id(hass, "light")

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(light_id).state == "on"

    # Window already expired → this is a genuine press of the remote's light button.
    await fire_rf(hass, "c_lt")

    assert hass.states.get(light_id).state == "off"


async def test_event_without_a_code_still_falls_back_to_a_time_window(
    hass: HomeAssistant,
) -> None:
    """A gateway that reports only an action keeps the blanket-window behaviour.

    Code-keyed suppression needs the code; without one there is nothing to match,
    so any reception during the window is still treated as a possible echo.
    """
    await setup_full(hass)
    light_id = one_id(hass, "light")

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()

    hass.bus.async_fire(
        "esphome.rf_fan_received", {"device": "esp32-test", "action": "light_toggle"}
    )
    await hass.async_block_till_done()

    assert hass.states.get(light_id).state == "on"
