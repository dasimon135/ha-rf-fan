"""Entity behaviour tests (require a Home Assistant environment via phcc).

⚠️ Not runnable on the Windows dev machine used for this repo (same reason as
`test_config_flow.py`): the HA test stack has no importable build there. The
module `skip`s cleanly when `pytest_homeassistant_custom_component` is absent, so
it never breaks the pure suite (`test_actions.py`); it runs in CI Linux.

These tests drive the real platform entities (fan/light/select) end-to-end:
they register a stub `esphome.<device>_transmit_rf_fan` service that captures
every transmit call, set up a full-capability config entry, then assert the
observable entity behaviours (toggle repeat_count, restore, colour gating,
direction/preset).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import mock_restore_cache

from tests.ha_helpers import last_call as _last_call
from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import setup_full as _setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


@pytest.mark.parametrize(
    ("configured", "expected_toggle"),
    [
        # Even counts round DOWN to the nearest odd value: a toggle must end up
        # actuated an odd number of times whatever the receiver does with a burst.
        (2, 1),
        (4, 3),
        # An odd count is already correct and passes straight through — this is what
        # lets a receiver that drops a lone frame actually see a light_toggle (#15).
        (5, 5),
        (1, 1),
    ],
)
async def test_toggle_vs_absolute_repeat_count(
    hass: HomeAssistant, configured: int, expected_toggle: int
) -> None:
    """Toggles round the entry repeat_count down to odd; absolute actions keep it."""
    _entry, calls = await _setup_full(hass, repeat_count=configured)

    light_id = _one_id(hass, "light")
    fan_id = _one_id(hass, "fan")

    # Toggle action: light toggle → nearest odd value at or below the configured one.
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    toggle = _last_call(calls, "light_toggle")
    assert toggle is not None, "light_toggle was never transmitted"
    assert toggle["code"] == "c_lt"
    assert toggle["repeat_count"] == expected_toggle

    # Absolute action: fan speed 1 → repeat_count must be the entry value, untouched.
    # percentage 33 maps to speed index 1 (step = 100/3).
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 33}, blocking=True
    )
    await hass.async_block_till_done()
    speed = _last_call(calls, "fan_speed_1")
    assert speed is not None, "fan_speed_1 was never transmitted"
    assert speed["code"] == "c_s1"
    assert speed["repeat_count"] == configured


async def test_fan_restore_state(hass: HomeAssistant) -> None:
    """The fan restores its assumed on/percentage state via RestoreEntity.

    Restore approach used: `mock_restore_cache` (the documented phcc mechanism).
    We first set the entry up to discover the generated entity_id dynamically,
    unload it, seed the restore cache with a known State for that entity_id, then
    set the entry up again and assert the fan comes back `on` at the restored
    percentage. This exercises `RfFanEntity.async_added_to_hass` /
    `async_get_last_state` directly.
    """
    entry, _calls = await _setup_full(hass)
    fan_id = _one_id(hass, "fan")

    # Tear the entry down, then seed the restore cache for the fan entity_id.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    mock_restore_cache(hass, (State(fan_id, "on", {"percentage": 66}),))

    # Bring the entry back up: the fan must restore from the seeded state.
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(fan_id)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["percentage"] == 66


async def test_color_select_gated_by_light(hass: HomeAssistant) -> None:
    """The colour-temp select is unavailable while the light is known to be off."""
    await _setup_full(hass)

    light_id = _one_id(hass, "light")
    select_id = _one_id(hass, "select")

    # Light OFF → the colour cycle needs the lamp powered → select unavailable.
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(select_id).state == STATE_UNAVAILABLE

    # Light ON → select becomes available again (a real colour option).
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(select_id).state != STATE_UNAVAILABLE


async def test_color_cycle_repeats_per_step_and_gaps(hass: HomeAssistant, monkeypatch) -> None:
    """Colour cycling sends each step with repeat_count and separates distinct steps.

    The fan debounces a rapid repeat burst into a single colour step, so every step is
    transmitted `repeat_count` times (reliability); distinct steps are separated by a gap
    (`entity.sleep`) so the receiver registers them as separate presses. A 2-step change
    must therefore emit two presses with exactly one gap between them.
    """
    _entry, calls = await _setup_full(hass, repeat_count=2)
    light_id = _one_id(hass, "light")
    select_id = _one_id(hass, "select")

    # Record gap sleeps without actually waiting on the event loop.
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("custom_components.rf_fan.entity.sleep", _fake_sleep)

    # Turn the light on (the colour cycle needs the lamp powered). The OFF->ON
    # transition bumps the assumed position 0->1 (Chaud -> Neutre).
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    # Neutre(1) -> Chaud(0): steps = (0 - 1) % 3 = 2 → two presses, one gap between.
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "Chaud"}, blocking=True
    )
    await hass.async_block_till_done()

    kelvin = [c for c in calls if c.get("action") == "light_kelvin"]
    assert len(kelvin) == 2, "a 2-step colour change must send two presses"
    assert all(c["repeat_count"] == 2 for c in kelvin), "each step keeps repeat_count"
    assert len(sleeps) == 1, "exactly one gap between the two presses"
    assert hass.states.get(select_id).state == "Chaud"


async def test_fan_direction_and_preset(hass: HomeAssistant) -> None:
    """set_direction / set_preset_mode update the assumed attributes."""
    await _setup_full(hass)
    fan_id = _one_id(hass, "fan")

    await hass.services.async_call(
        "fan", "set_direction", {"entity_id": fan_id, "direction": "reverse"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(fan_id).attributes["direction"] == "reverse"

    await hass.services.async_call(
        "fan",
        "set_preset_mode",
        {"entity_id": fan_id, "preset_mode": "natural"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"


async def test_turn_on_applies_the_requested_preset(hass: HomeAssistant) -> None:
    """`fan.turn_on` with a preset_mode must actually apply the preset.

    The service schema accepts it, so silently dropping it leaves scripts and
    blueprints believing the fan switched to natural airflow when it did not.
    """
    _entry, calls = await _setup_full(hass)
    fan_id = _one_id(hass, "fan")

    await hass.services.async_call(
        "fan", "turn_on", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    await hass.async_block_till_done()

    assert _last_call(calls, "fan_natural") is not None, "fan_natural was never sent"
    state = hass.states.get(fan_id)
    assert state.state == "on"
    assert state.attributes["preset_mode"] == "natural"


async def test_colour_position_is_not_moved_when_nothing_is_transmitted(
    hass: HomeAssistant,
) -> None:
    """With no `light_kelvin` code, selecting a colour must not fake the new position."""
    entry, _calls = await _setup_full(hass)

    codes = dict(entry.data["codes"])
    codes.pop("light_kelvin")
    hass.config_entries.async_update_entry(entry, data={**entry.data, "codes": codes})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    light_id = _one_id(hass, "light")
    select_id = _one_id(hass, "select")

    # Powering the light on bumps the assumed position 0 -> 1 (Chaud -> Neutre).
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(select_id).state == "Neutre"

    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "Froid"}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(select_id).state == "Neutre", "position moved without any RF"
