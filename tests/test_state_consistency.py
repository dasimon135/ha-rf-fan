"""Second review, 2026-09-23: places where the shown state and the fan part ways.

Each test pins one path found by reading the code. None was reported by a user;
each leaves Home Assistant showing a state the hardware is not in, or presses a
key nobody asked for.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_fan.const import DOMAIN
from tests.ha_helpers import (
    CODES,
    DEVICE,
    actions_sent,
    fire_rf,
    one_id,
    register_stub,
    setup_relative,
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


# --- Entries created before 1.5.0 have no unique id ----------------------------


def _legacy_entry(hass: HomeAssistant, **kwargs) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=6,
        title="Legacy",
        data={
            "esphome_device": DEVICE,
            "fan_name": "Legacy",
            "speed_count": 3,
            "light_control": "toggle",
            "has_light": True,
            "codes": dict(CODES),
        },
        **kwargs,
    )
    entry.add_to_hass(hass)
    return entry


async def test_an_entry_without_a_unique_id_is_given_one(hass: HomeAssistant) -> None:
    """Without one, the same fan could be added a second time on the same gateway."""
    register_stub(hass)
    entry = _legacy_entry(hass)
    assert entry.unique_id is None

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.unique_id == "esp32_test_legacy"


async def test_the_same_fan_cannot_then_be_added_again(hass: HomeAssistant) -> None:
    register_stub(hass)
    entry = _legacy_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "esphome_device": DEVICE,
            "fan_name": "Legacy",
            "speed_count": 3,
            "light_control": "toggle",
            "has_fan_on": False,
            "direction_control": "none",
            "natural_control": "none",
            "color_control": "none",
            "light_level": "none",
            "timer_hours": [],
            "has_timer_off": False,
            "has_sound": False,
            "extra_count": 0,
        },
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_a_unique_id_already_taken_is_left_alone(hass: HomeAssistant) -> None:
    """Two legacy entries for one fan: the second must still load, unchanged."""
    register_stub(hass)
    first = _legacy_entry(hass)
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()

    second = _legacy_entry(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    assert first.unique_id == "esp32_test_legacy"
    assert second.unique_id is None


# --- The `dedicated` airflow preset --------------------------------------------


async def _dedicated(hass: HomeAssistant, **kwargs):
    entry, calls = await setup_relative(hass, natural_control="dedicated", **kwargs)
    return entry, calls, one_id(hass, "fan")


async def test_changing_direction_leaves_a_dedicated_preset(hass: HomeAssistant) -> None:
    """On a `per_speed` remote the direction is changed by re-sending a speed code,
    and on a `dedicated` remote a speed key is what leaves the preset (#34)."""
    _entry, calls, fan_id = await _dedicated(hass)
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 67}, blocking=True
    )
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    calls.clear()

    await hass.services.async_call(
        "fan", "set_direction", {"entity_id": fan_id, "direction": "reverse"}, blocking=True
    )

    assert actions_sent(calls) == ["fan_speed_2_reverse"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"


async def test_the_remote_on_key_drops_a_deferred_preset(hass: HomeAssistant) -> None:
    """Started from the remote's ON key, the fan runs in normal airflow.

    The preset asked for while it was stopped used to stay shown AND armed, and was
    pressed right after the next speed key, the one gesture that leaves it.
    """
    _entry, calls, fan_id = await _dedicated(hass, extra_codes={"fan_on": "r_on"})
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )

    await fire_rf(hass, "r_on")
    state = hass.states.get(fan_id)
    assert state.state == "on"
    assert state.attributes["preset_mode"] == "normal"

    calls.clear()
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 100}, blocking=True
    )
    assert actions_sent(calls) == ["fan_speed_3"]


async def test_a_deferred_preset_survives_a_restart(hass: HomeAssistant) -> None:
    """The shown preset is restored; the press it is waiting for must be too.

    Otherwise the fan starts in normal airflow while showing `natural`, and picking
    `natural` again does nothing, since that is already the state.
    """
    entry, calls, fan_id = await _dedicated(hass)
    # A known "off" first: only an on/off state is restored, and a fan HA has never
    # driven reads `unknown`.
    await hass.services.async_call("fan", "turn_off", {"entity_id": fan_id}, blocking=True)
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"
    calls.clear()

    await hass.services.async_call("fan", "turn_on", {"entity_id": fan_id}, blocking=True)
    await hass.async_block_till_done()

    assert actions_sent(calls) == ["fan_speed_1", "fan_natural"]


# --- A light switched off mid-walk ---------------------------------------------


async def test_switching_the_light_off_stops_a_brightness_walk(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Nothing reaches a lamp that is off, so no further step may be pressed or counted."""
    entry, calls = await setup_relative(hass)
    light_id = one_id(hass, "light")
    await hass.services.async_call("light", "turn_on", {"entity_id": light_id}, blocking=True)
    calls.clear()

    first_step_done = asyncio.Event()
    release = asyncio.Event()

    async def _gated_sleep(delay: float) -> None:
        if not first_step_done.is_set():
            first_step_done.set()
            await release.wait()

    monkeypatch.setattr("custom_components.rf_fan.entity.sleep", _gated_sleep)

    climbing = asyncio.create_task(
        hass.services.async_call(
            "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
        )
    )
    await asyncio.wait_for(first_step_done.wait(), timeout=5)

    await hass.services.async_call("light", "turn_off", {"entity_id": light_id}, blocking=True)
    release.set()
    await climbing
    await hass.async_block_till_done()

    assert actions_sent(calls).count("light_bright_up") == 1
    assert hass.states.get(light_id).state == "off"
    assert entry.runtime_data.walks == {}


# --- The names given to free-form keys -----------------------------------------


async def test_learning_shows_the_name_given_to_a_free_form_key(hass: HomeAssistant) -> None:
    """The names are asked for one screen before learning; learning has to use them."""
    register_stub(hass)
    await hass.async_block_till_done()
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "esphome_device": DEVICE,
            "fan_name": "Named",
            "speed_count": 2,
            "light_control": "none",
            "has_fan_on": False,
            "direction_control": "none",
            "natural_control": "none",
            "color_control": "none",
            "light_level": "none",
            "timer_hours": [],
            "has_timer_off": False,
            "has_sound": False,
            "extra_count": 1,
        },
    )
    result = await flow.async_configure(result["flow_id"], {"extra_1": "Mémoire"})
    result = await flow.async_configure(result["flow_id"], {"method": "manual"})

    assert result["step_id"] == "codes"
    placeholders = result.get("description_placeholders") or {}
    assert "Mémoire" in placeholders.get("extra_names", "")


async def test_relearning_a_free_form_key_names_it(hass: HomeAssistant) -> None:
    """The listening screen said `extra_1`; the owner called that key "Mémoire"."""
    from unittest.mock import patch

    from homeassistant.config_entries import SOURCE_RECONFIGURE
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.rf_fan.const import EVENT_RF_FAN_RECEIVED

    entry = _legacy_entry(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            "extra_count": 1,
            "extra_names": {"extra_1": "Mémoire"},
            "codes": {**entry.data["codes"], "extra_1": "c_x1"},
        },
    )
    flow = hass.config_entries.flow

    with patch("custom_components.rf_fan.async_setup_entry", return_value=True):
        result = await flow.async_init(
            DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        result = await flow.async_configure(
            result["flow_id"], {"next_step_id": "reconfigure_codes"}
        )
        result = await flow.async_configure(result["flow_id"], {"relearn_extra_1": True})
        result = await flow.async_configure(result["flow_id"], {"method": "learn"})

        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert "Mémoire" in result["description_placeholders"]["action"]

        hass.bus.async_fire(EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "c_x1_v2"})
        await hass.async_block_till_done()
        await flow.async_configure(result["flow_id"])
        await hass.async_block_till_done()
