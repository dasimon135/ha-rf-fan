"""Entity behaviour tests (require a Home Assistant environment via phcc).

⚠️ Not runnable on the Windows dev machine used for this repo (same reason as
`test_config_flow.py`): the HA test stack has no importable build there. The
module `skip`s cleanly when `pytest_homeassistant_custom_component` is absent, so
it never breaks the pure suite (`test_actions.py`); it runs in CI Linux.

These tests drive the real platform entities (fan/light/select) end-to-end:
they register a stub `esphome.<device>_transmit_rf_fan` service that captures
every transmit call, set up a full-capability config entry, then assert the
observable entity behaviours (single-shot repeat_count, restore, colour gating,
direction/preset).
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.rf_fan.const import DOMAIN

DEVICE = "esp32-test"
# The gateway service name mirrors config_flow: dashes become underscores.
TRANSMIT_SERVICE = "esp32_test_transmit_rf_fan"

# Codes for every action. light_on/light_off/fan_on are deliberately left out so
# the light falls back to `light_toggle` and the fan turns on via a speed action —
# this is what lets us assert the single-shot vs absolute repeat_count.
CODES = {
    "fan_off": "c_off",
    "fan_speed_1": "c_s1",
    "fan_speed_2": "c_s2",
    "fan_speed_3": "c_s3",
    "light_toggle": "c_lt",
    "light_kelvin": "c_kel",
    "fan_reverse": "c_rev",
    "fan_natural": "c_nat",
    "timer_1h": "c_t1",
    "timer_2h": "c_t2",
    "timer_4h": "c_t4",
    "timer_8h": "c_t8",
    "sound_toggle": "c_snd",
}


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


def _full_entry(hass: HomeAssistant, repeat_count: int = 2) -> MockConfigEntry:
    """Create and register a full-capability entry (all flags + all codes)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Full",
        data={
            "esphome_device": DEVICE,
            "fan_name": "Full",
            "speed_count": 3,
            "light_control": "toggle",
            "has_fan_on": False,
            "has_direction": True,
            "has_natural_preset": True,
            "has_color_temp": True,
            "has_timers": True,
            "has_sound": True,
            "has_light": True,
            "repeat_count": repeat_count,
            "codes": dict(CODES),
        },
    )
    entry.add_to_hass(hass)
    return entry


def _register_stub(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Register the esphome transmit stub and return the list capturing its calls."""
    calls: list[dict[str, Any]] = []

    def _capture(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("esphome", TRANSMIT_SERVICE, _capture)
    return calls


def _last_call(calls: list[dict[str, Any]], action: str) -> dict[str, Any] | None:
    """Return the most recent captured call for `action` (or None)."""
    for data in reversed(calls):
        if data.get("action") == action:
            return data
    return None


async def _setup_full(hass: HomeAssistant, repeat_count: int = 2):
    """Register the stub, set up a full entry, and return (entry, calls)."""
    calls = _register_stub(hass)
    entry = _full_entry(hass, repeat_count=repeat_count)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, calls


def _one_id(hass: HomeAssistant, domain: str) -> str:
    """Return the single entity_id for a platform domain (fan/light/select/...)."""
    ids = hass.states.async_entity_ids(domain)
    assert ids, f"no {domain} entity was created"
    return ids[0]


async def test_single_shot_vs_absolute_repeat_count(hass: HomeAssistant) -> None:
    """Relative actions transmit once; absolute actions use the entry repeat_count.

    Entry repeat_count == 2. Toggling the light is a relative (single-shot) action
    (`light_toggle`) → repeat_count 1. Setting a fan speed is absolute
    (`fan_speed_1`) → repeat_count 2.
    """
    _entry, calls = await _setup_full(hass, repeat_count=2)

    light_id = _one_id(hass, "light")
    fan_id = _one_id(hass, "fan")

    # Relative action: light toggle → repeat_count must be forced to 1.
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    toggle = _last_call(calls, "light_toggle")
    assert toggle is not None, "light_toggle was never transmitted"
    assert toggle["code"] == "c_lt"
    assert toggle["repeat_count"] == 1

    # Absolute action: fan speed 1 → repeat_count must be the entry value (2).
    # percentage 33 maps to speed index 1 (step = 100/3).
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 33}, blocking=True
    )
    await hass.async_block_till_done()
    speed = _last_call(calls, "fan_speed_1")
    assert speed is not None, "fan_speed_1 was never transmitted"
    assert speed["code"] == "c_s1"
    assert speed["repeat_count"] == 2


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
