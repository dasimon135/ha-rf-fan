"""Free-form keys: a button that sends a code, under a name its owner chose (#18).

@elmr91's remote has a "memory" key. Neither Home Assistant nor this integration
knows what the fan does with it, and that is the whole point: what Home Assistant
HAS a concept of stays typed, and what it does not becomes a named button.

So there is nothing to assert about state here — there is none — only that the
right code goes on the air, under the right name, and that a fan without extra keys
grows no entities it never asked for.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_fan.const import DOMAIN
from tests.ha_helpers import CODES, DEVICE, register_stub


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _setup(hass: HomeAssistant, *, count: int, names: dict | None, repeat: int = 2):
    """Set up a fan with `count` free-form keys."""
    calls = register_stub(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Extras",
        data={
            "esphome_device": DEVICE,
            "gateway_service": "esp32_test",
            "fan_name": "Extras",
            "speed_count": 3,
            "light_control": "toggle",
            "has_light": True,
            "direction_control": "none",
            "natural_control": "none",
            "color_control": "none",
            "light_level": "none",
            "extra_count": count,
            **({} if names is None else {"extra_names": names}),
            "repeat_count": repeat,
            "codes": dict(CODES) | {"extra_1": "x_one", "extra_2": "x_two"},
        },
        version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, calls


def _extra_ids(hass: HomeAssistant, entry) -> list[str]:
    """The free-form buttons, in remote order (extra_1 first), not alphabetical."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    found = {
        registered.unique_id.rsplit("_", 1)[-1]: registered.entity_id
        for registered in er.async_entries_for_config_entry(registry, entry.entry_id)
        if registered.unique_id.startswith(f"{entry.entry_id}_extra_")
    }
    return [found[index] for index in sorted(found, key=int)]


async def test_pressing_a_free_form_button_sends_its_code(hass: HomeAssistant) -> None:
    """The entire contract: press, and the learned code goes on the air."""
    entry, calls = await _setup(hass, count=2, names={"extra_1": "Memory"})
    button_id = _extra_ids(hass, entry)[0]

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert [call.get("action") for call in calls] == ["extra_1"]
    assert calls[0]["code"] == "x_one"


async def test_a_free_form_key_is_repeated_as_a_toggle(hass: HomeAssistant) -> None:
    """Its effect is unknowable, and the two mistakes are not symmetric.

    An absolute code sent an odd number of times lands where an even number would.
    A real toggle sent an even number of times nets zero flips, and the button looks
    dead with nothing to see from outside.
    """
    entry, calls = await _setup(hass, count=1, names={"extra_1": "Memory"}, repeat=4)
    button_id = _extra_ids(hass, entry)[0]

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert calls[0]["repeat_count"] == 3


async def test_the_button_carries_the_name_its_owner_gave_it(hass: HomeAssistant) -> None:
    """The label is the whole user interface of a key nothing else can describe."""
    entry, _calls = await _setup(hass, count=1, names={"extra_1": "Mémoire"})
    button_id = _extra_ids(hass, entry)[0]

    assert hass.states.get(button_id).attributes["friendly_name"] == "Extras Mémoire"


async def test_a_blank_name_falls_back_rather_than_failing(hass: HomeAssistant) -> None:
    """A configuration is never blocked over a label, so an empty one is allowed."""
    entry, _calls = await _setup(hass, count=2, names={"extra_1": "Memory", "extra_2": ""})
    names = [
        hass.states.get(button_id).attributes["friendly_name"]
        for button_id in _extra_ids(hass, entry)
    ]

    assert names == ["Extras Memory", "Extras Extra key 2"]


async def test_a_fan_without_extra_keys_grows_no_extra_buttons(
    hass: HomeAssistant,
) -> None:
    """The normal case: nothing declared, nothing created."""
    entry, _calls = await _setup(hass, count=0, names=None)

    assert _extra_ids(hass, entry) == []
