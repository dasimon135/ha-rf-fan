"""Shared fixtures/helpers for the tests that need a Home Assistant environment.

Import this module ONLY after `pytest.importorskip("pytest_homeassistant_custom_component")`
in the calling test module: it imports Home Assistant at module level and would
otherwise break the pure (HA-free) suite.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_fan.const import DOMAIN, EVENT_RF_FAN_RECEIVED

DEVICE = "esp32-test"
# The gateway service name mirrors config_flow: dashes become underscores.
TRANSMIT_SERVICE = "esp32_test_transmit_rf_fan"

# Codes for every action. light_on/light_off/fan_on are deliberately left out so
# the light falls back to `light_toggle` and the fan turns on via a speed action —
# this is what lets us assert the toggle vs absolute repeat_count.
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


def full_entry(hass: HomeAssistant, repeat_count: int = 2) -> MockConfigEntry:
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
            "direction_control": "toggle",
            "has_natural_preset": True,
            "color_control": "cycle",
            "light_level": "none",
            "has_timers": True,
            "has_sound": True,
            "has_light": True,
            "repeat_count": repeat_count,
            "codes": dict(CODES),
        },
    )
    entry.add_to_hass(hass)
    return entry


def register_stub(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Register the esphome transmit stub and return the list capturing its calls."""
    calls: list[dict[str, Any]] = []

    def _capture(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("esphome", TRANSMIT_SERVICE, _capture)
    return calls


def last_call(calls: list[dict[str, Any]], action: str) -> dict[str, Any] | None:
    """Return the most recent captured call for `action` (or None)."""
    for data in reversed(calls):
        if data.get("action") == action:
            return data
    return None


async def setup_full(hass: HomeAssistant, repeat_count: int = 2):
    """Register the stub, set up a full entry, and return (entry, calls)."""
    calls = register_stub(hass)
    entry = full_entry(hass, repeat_count=repeat_count)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, calls


def one_id(hass: HomeAssistant, domain: str) -> str:
    """Return the single entity_id for a platform domain (fan/light/select/...)."""
    ids = hass.states.async_entity_ids(domain)
    assert ids, f"no {domain} entity was created"
    return ids[0]


def button_id(hass: HomeAssistant, fragment: str) -> str:
    """Return the single button entity_id whose id contains `fragment`."""
    matches = [e for e in hass.states.async_entity_ids("button") if fragment in e]
    assert len(matches) == 1, f"expected exactly one button matching {fragment!r}: {matches}"
    return matches[0]


async def fire_rf(hass: HomeAssistant, code: str, device: str = DEVICE) -> None:
    """Simulate the gateway reporting a sniffed RF frame, as the ESPHome node does."""
    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": device, "action": "sniff", "code": code}
    )
    await hass.async_block_till_done()


# Codes for a remote whose buttons MOVE a value instead of setting one, plus a
# direction that lives in the speed code set rather than in a key of its own.
# Modelled on the Inspire Aruba Plus of issue #18, scaled down to 3 speeds.
RELATIVE_CODES = {
    "fan_off": "r_off",
    "fan_speed_1": "r_s1",
    "fan_speed_2": "r_s2",
    "fan_speed_3": "r_s3",
    "fan_speed_1_reverse": "r_s1r",
    "fan_speed_2_reverse": "r_s2r",
    "fan_speed_3_reverse": "r_s3r",
    "light_toggle": "r_lt",
    "light_kelvin_up": "r_ku",
    "light_kelvin_down": "r_kd",
    "light_bright_up": "r_bu",
    "light_bright_down": "r_bd",
}

# The natural-airflow key of a `per_speed` remote: one code per direction, the
# same shape as the speeds (issue #28).
NATURAL_CODES = {
    "fan_natural": "r_nat",
    "fan_natural_reverse": "r_natr",
}


def relative_entry(
    hass: HomeAssistant,
    repeat_count: int = 2,
    *,
    color_temp_steps: int | None = None,
    light_level_steps: int | None = None,
    natural_preset: bool = False,
    natural_control: str | None = None,
) -> MockConfigEntry:
    """Create an entry whose remote steps its values (issue #18 shape).

    The step counts are left out of the data unless asked for, so the default entry
    exercises the fallbacks an entry created before they existed relies on.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Relative",
        data={
            "esphome_device": DEVICE,
            "fan_name": "Relative",
            "speed_count": 3,
            "light_control": "toggle",
            "has_fan_on": False,
            "direction_control": "per_speed",
            **(
                {"has_natural_preset": natural_preset}
                if natural_control is None
                else {"natural_control": natural_control}
            ),
            "color_control": "relative",
            "light_level": "relative",
            "has_timers": False,
            "has_sound": False,
            "has_light": True,
            "repeat_count": repeat_count,
            "codes": dict(RELATIVE_CODES)
            | (NATURAL_CODES if (natural_preset or natural_control not in (None, "none")) else {}),
            **({} if color_temp_steps is None else {"color_temp_steps": color_temp_steps}),
            **({} if light_level_steps is None else {"light_level_steps": light_level_steps}),
        },
    )
    entry.add_to_hass(hass)
    return entry


async def setup_relative(
    hass: HomeAssistant,
    repeat_count: int = 2,
    *,
    color_temp_steps: int | None = None,
    light_level_steps: int | None = None,
    natural_preset: bool = False,
    natural_control: str | None = None,
):
    """Register the stub, set up a stepped-control entry, and return (entry, calls)."""
    calls = register_stub(hass)
    entry = relative_entry(
        hass,
        repeat_count=repeat_count,
        color_temp_steps=color_temp_steps,
        light_level_steps=light_level_steps,
        natural_preset=natural_preset,
        natural_control=natural_control,
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, calls


def id_by_unique_suffix(hass: HomeAssistant, entry, domain: str, suffix: str) -> str:
    """Entity id for one of an entry's entities, picked by unique-id suffix.

    `one_id` cannot be used once a platform owns more than one entity for the same
    entry — the colour select and the brightness position select are both `select`.
    """
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.domain == domain and registered.unique_id.endswith(suffix):
            return registered.entity_id
    raise AssertionError(f"no {domain} entity ending in {suffix!r} was created")


def actions_sent(calls: list[dict[str, Any]]) -> list[str]:
    """The action names transmitted so far, in order."""
    return [data.get("action") for data in calls]
