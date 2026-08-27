"""The natural-airflow key has a code per direction on a `per_speed` remote (#28).

`direction_control: per_speed` describes a remote with no reverse key at all: it
stores the winter/summer mode itself and emits a different code for the same button
depending on which mode it is in. 1.8.0 modelled that for the speeds. @elmr91
reported that his remote does it for the natural-airflow key too, so sending the
summer code while the fan runs in winter reaches the wrong state, or nothing.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components.fan import ATTR_DIRECTION, ATTR_PRESET_MODE
from homeassistant.core import HomeAssistant

from custom_components.rf_fan.actions import split_actions, transmit_repeat_count
from custom_components.rf_fan.const import (
    ACTION_FAN_NATURAL,
    ACTION_FAN_NATURAL_REVERSE,
)
from tests.ha_helpers import (
    actions_sent,
    fire_rf,
    one_id,
    register_stub,
    relative_entry,
    setup_full,
    setup_relative,
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


def _required(**caps) -> list[str]:
    required, _optional = split_actions(3, "toggle", **caps)
    return required


async def _face(hass: HomeAssistant, fan: str, direction: str) -> None:
    """Put the fan in a known direction, so the preset code has one to resolve."""
    await hass.services.async_call(
        "fan",
        "set_direction",
        {"entity_id": fan, ATTR_DIRECTION: direction},
        blocking=True,
    )


def test_the_winter_code_is_learned_only_where_it_exists() -> None:
    """One extra key, and only for the combination that produces it."""
    both = _required(direction_control="per_speed", has_natural_preset=True)
    no_preset = _required(direction_control="per_speed", has_natural_preset=False)
    keyed_direction = _required(direction_control="toggle", has_natural_preset=True)

    assert ACTION_FAN_NATURAL_REVERSE in both
    assert ACTION_FAN_NATURAL_REVERSE not in no_preset
    # A remote with a reverse key of its own presses the SAME natural button in
    # both modes, so there is no second code to learn.
    assert ACTION_FAN_NATURAL_REVERSE not in keyed_direction
    assert ACTION_FAN_NATURAL in keyed_direction


def test_the_winter_code_keeps_a_burst_odd() -> None:
    """Whether it flips or sets, an odd count is right; an even one may do nothing.

    Not confirmed against hardware, and it does not need to be: rounding an
    absolute code's burst to odd changes nothing, while leaving a real toggle out
    of `TOGGLE_ACTIONS` on an even count nets zero flips.
    """
    assert transmit_repeat_count(ACTION_FAN_NATURAL_REVERSE, 4) == 3
    assert transmit_repeat_count(ACTION_FAN_NATURAL_REVERSE, 5) == 5


async def test_the_preset_uses_the_code_for_the_current_direction(
    hass: HomeAssistant,
) -> None:
    """The bug @elmr91 reported: in winter, the summer code was going out."""
    _entry, calls = await setup_relative(hass, natural_preset=True)
    fan = one_id(hass, "fan")
    await _face(hass, fan, "reverse")

    await hass.services.async_call(
        "fan",
        "set_preset_mode",
        {"entity_id": fan, ATTR_PRESET_MODE: "natural"},
        blocking=True,
    )

    assert ACTION_FAN_NATURAL_REVERSE in actions_sent(calls)
    assert ACTION_FAN_NATURAL not in actions_sent(calls)
    assert hass.states.get(fan).attributes[ATTR_PRESET_MODE] == "natural"


async def test_an_unknown_direction_still_sends_the_summer_code(
    hass: HomeAssistant,
) -> None:
    """Same fallback as the speeds: forward is what goes out when nothing is known."""
    _entry, calls = await setup_relative(hass, natural_preset=True)
    fan = one_id(hass, "fan")

    await hass.services.async_call(
        "fan",
        "set_preset_mode",
        {"entity_id": fan, ATTR_PRESET_MODE: "natural"},
        blocking=True,
    )

    assert ACTION_FAN_NATURAL in actions_sent(calls)
    assert ACTION_FAN_NATURAL_REVERSE not in actions_sent(calls)


async def test_an_entry_predating_the_winter_code_keeps_working(
    hass: HomeAssistant,
) -> None:
    """Upgrading must not make the preset button go dead until it is reconfigured.

    A `per_speed` entry created before this release has the preset and no winter
    code, which is a shape the reverse speeds can never be in. Falling back to the
    summer code leaves it exactly as 1.8.0 left it.
    """
    calls = register_stub(hass)
    entry = relative_entry(hass, natural_preset=True)
    codes = {
        action: code
        for action, code in entry.data["codes"].items()
        if action != ACTION_FAN_NATURAL_REVERSE
    }
    hass.config_entries.async_update_entry(entry, data={**entry.data, "codes": codes})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    fan = one_id(hass, "fan")
    await _face(hass, fan, "reverse")

    await hass.services.async_call(
        "fan",
        "set_preset_mode",
        {"entity_id": fan, ATTR_PRESET_MODE: "natural"},
        blocking=True,
    )

    assert ACTION_FAN_NATURAL in actions_sent(calls)
    assert hass.states.get(fan).attributes[ATTR_PRESET_MODE] == "natural"


async def test_a_winter_natural_frame_reports_the_preset_and_the_direction(
    hass: HomeAssistant,
) -> None:
    """The property that makes `per_speed` track a remote better than a toggle can."""
    _entry, _calls = await setup_relative(hass, natural_preset=True)
    fan = one_id(hass, "fan")

    await fire_rf(hass, "r_natr")

    state = hass.states.get(fan)
    assert state.attributes[ATTR_PRESET_MODE] == "natural"
    assert state.attributes[ATTR_DIRECTION] == "reverse"


async def test_a_summer_natural_frame_says_forward(hass: HomeAssistant) -> None:
    """The mirror case: the code that was pressed names the mode it was pressed in."""
    _entry, _calls = await setup_relative(hass, natural_preset=True)
    fan = one_id(hass, "fan")
    await _face(hass, fan, "reverse")

    await fire_rf(hass, "r_nat")

    state = hass.states.get(fan)
    assert state.attributes[ATTR_PRESET_MODE] == "natural"
    assert state.attributes[ATTR_DIRECTION] == "forward"


async def test_a_keyed_remote_keeps_its_direction_through_a_preset_press(
    hass: HomeAssistant,
) -> None:
    """With a reverse key of its own, the direction is dead-reckoned from that key.

    Its natural code carries no direction at all, so following one must not
    overwrite what the reverse key established.
    """
    _entry, _calls = await setup_full(hass)
    fan = one_id(hass, "fan")
    await _face(hass, fan, "reverse")

    await fire_rf(hass, "c_nat")

    state = hass.states.get(fan)
    assert state.attributes[ATTR_PRESET_MODE] == "natural"
    assert state.attributes[ATTR_DIRECTION] == "reverse"
