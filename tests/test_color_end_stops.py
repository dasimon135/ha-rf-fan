"""Two colour keys stop at the ends; one cycling key comes round (#18).

@elmr91 pressed "warmer" on the top position of a five-position lamp: the lamp did
not move — it was already at the end — and the assumed position rolled back to the
first one. The value looked like a cycle because the only remote shape modelled when
the walk was written was the cycling key. With a ± pair it is a range, exactly like
the brightness, and wrapping it desynchronises rather than shortens.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from tests.ha_helpers import (
    actions_sent,
    fire_rf,
    id_by_unique_suffix,
    one_id,
    setup_full,
    setup_relative,
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


STEPS = 5
"""What @elmr91 counted on his remote once he had measured it properly."""


async def _press_remote(hass: HomeAssistant, entry, code: str) -> None:
    """Press a key, separated from the previous press by more than a burst."""
    seen = entry.runtime_data.receive_seen
    for known in seen:
        seen[known] -= 10.0
    await fire_rf(hass, code)


async def _walk_to(hass: HomeAssistant, color: str, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": color, "option": option}, blocking=True
    )


async def test_the_top_position_does_not_roll_over(hass: HomeAssistant) -> None:
    """The failure he saw: one press too many, and the dropdown jumped to the bottom."""
    entry, _calls = await setup_relative(hass, color_temp_steps=STEPS)
    color = id_by_unique_suffix(hass, entry, "select", "_color_temp")
    await _walk_to(hass, color, str(STEPS))

    await _press_remote(hass, entry, "r_ku")

    assert hass.states.get(color).state == str(STEPS)


async def test_the_bottom_position_does_not_roll_under(hass: HomeAssistant) -> None:
    """The mirror case, which the same modulo produced."""
    entry, _calls = await setup_relative(hass, color_temp_steps=STEPS)
    color = id_by_unique_suffix(hass, entry, "select", "_color_temp")
    await _walk_to(hass, color, "1")

    await _press_remote(hass, entry, "r_kd")

    assert hass.states.get(color).state == "1"


async def test_a_walk_never_plans_through_the_end(hass: HomeAssistant) -> None:
    """Going bottom to top is four presses up, not one press down and a wrap."""
    entry, calls = await setup_relative(hass, color_temp_steps=STEPS)
    color = id_by_unique_suffix(hass, entry, "select", "_color_temp")
    await _walk_to(hass, color, "1")
    calls.clear()

    await _walk_to(hass, color, str(STEPS))

    sent = actions_sent(calls)
    assert sent.count("light_kelvin_up") == STEPS - 1
    assert "light_kelvin_down" not in sent
    assert hass.states.get(color).state == str(STEPS)


async def test_a_cycling_remote_still_comes_round(hass: HomeAssistant) -> None:
    """One key has no other move: for `color_control: cycle` the wrap IS the hardware."""
    entry, _calls = await setup_full(hass)
    color = one_id(hass, "select")

    for expected in ("Neutre", "Froid", "Chaud"):
        await _press_remote(hass, entry, "c_kel")
        assert hass.states.get(color).state == expected
