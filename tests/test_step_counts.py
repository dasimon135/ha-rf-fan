"""How many positions the stepped controls model is a property of the hardware.

Both counts used to be constants — ten brightness steps and the three named colour
positions. @elmr91 measured his Inspire Aruba Plus at eight of each (issue #18),
which is the whole reason they are declared per fan now: a count that is too low
means the top of the slider never reaches the hardware's maximum, and one that is
too high means the last presses of the range do nothing.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.core import HomeAssistant

from custom_components.rf_fan.const import COLOR_TEMP_NAMED
from tests.ha_helpers import (
    actions_sent,
    button_id,
    fire_rf,
    id_by_unique_suffix,
    one_id,
    setup_relative,
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


MEASURED = 8
"""The count @elmr91 counted on his remote, for both colour and brightness."""


async def _press_remote(hass: HomeAssistant, entry, code: str) -> None:
    """Simulate a press separated from the previous one by more than a burst.

    Ageing what the de-bounce window remembers is the same statement as waiting:
    without it, a second press of the same key inside the window is discarded as a
    repeated frame, which is exactly what issue #24 asks for.
    """
    seen = entry.runtime_data.receive_seen
    for known in seen:
        seen[known] -= 10.0
    await fire_rf(hass, code)


async def test_the_brightness_slider_spans_the_declared_count(
    hass: HomeAssistant,
) -> None:
    """Full brightness is the top declared step, reached in one press per step."""
    _entry, calls = await setup_relative(hass, light_level_steps=MEASURED)
    light = one_id(hass, "light")

    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": light, ATTR_BRIGHTNESS: 255},
        blocking=True,
    )

    assert actions_sent(calls).count("light_bright_up") == MEASURED - 1
    assert hass.states.get(light).attributes[ATTR_BRIGHTNESS] == 255


async def test_the_position_select_lists_the_declared_count(
    hass: HomeAssistant,
) -> None:
    """The dropdown that declares the position offers exactly the real steps."""
    entry, _calls = await setup_relative(hass, light_level_steps=MEASURED)
    position = id_by_unique_suffix(hass, entry, "select", "_brightness_position")

    options = hass.states.get(position).attributes["options"]

    assert options == [str(step) for step in range(1, MEASURED + 1)]


async def test_the_resynchronise_button_walks_the_declared_range(
    hass: HomeAssistant,
) -> None:
    """Reaching the bottom stop from anywhere takes one press fewer than there are steps."""
    entry, calls = await setup_relative(hass, light_level_steps=MEASURED)
    resync = button_id(hass, "resynchronise")

    await hass.services.async_call(
        "button", "press", {"entity_id": resync}, blocking=True
    )

    assert actions_sent(calls).count("light_bright_down") == MEASURED - 1
    position = id_by_unique_suffix(hass, entry, "select", "_brightness_position")
    assert hass.states.get(position).state == "1"


async def test_three_colour_positions_keep_their_names(hass: HomeAssistant) -> None:
    """These strings ARE the entity's state; renaming them would break automations."""
    entry, _calls = await setup_relative(hass)
    color = id_by_unique_suffix(hass, entry, "select", "_color_temp")

    assert hass.states.get(color).attributes["options"] == COLOR_TEMP_NAMED


async def test_more_colour_positions_are_numbered(hass: HomeAssistant) -> None:
    """Warm / Neutral / Cold describes a three-way switch, and eight is not one."""
    entry, _calls = await setup_relative(hass, color_temp_steps=MEASURED)
    color = id_by_unique_suffix(hass, entry, "select", "_color_temp")

    options = hass.states.get(color).attributes["options"]

    assert options == [str(step) for step in range(1, MEASURED + 1)]


async def test_the_colour_walk_reaches_a_position_the_old_count_could_not(
    hass: HomeAssistant,
) -> None:
    """Three modelled positions made two presses the longest move; eight reach further."""
    entry, calls = await setup_relative(hass, color_temp_steps=MEASURED)
    color = id_by_unique_suffix(hass, entry, "select", "_color_temp")

    await hass.services.async_call(
        "select", "select_option", {"entity_id": color, "option": "5"}, blocking=True
    )

    assert actions_sent(calls).count("light_kelvin_up") == 4
    assert hass.states.get(color).state == "5"


async def test_following_the_remote_wraps_at_the_declared_count(
    hass: HomeAssistant,
) -> None:
    """The cycle comes round after the declared number of positions, not after three."""
    entry, _calls = await setup_relative(hass, color_temp_steps=MEASURED)
    color = id_by_unique_suffix(hass, entry, "select", "_color_temp")

    for _ in range(MEASURED):
        await _press_remote(hass, entry, "r_ku")

    assert hass.states.get(color).state == "1"
