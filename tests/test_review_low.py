"""Second review, low-severity findings: the add form, names, walks and reloads.

Each test pins a path found by reading the code on 2026-09-23. None was reported.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant

from custom_components.rf_fan.const import DOMAIN
from tests.ha_helpers import (
    DEVICE,
    actions_sent,
    full_entry,
    one_id,
    register_stub,
    setup_full,
    setup_relative,
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


def _declaration(**overrides):
    answers = {
        "esphome_device": DEVICE,
        "fan_name": "Salon",
        "speed_count": 4,
        "light_control": "on_off",
        "has_fan_on": True,
        "direction_control": "toggle",
        "natural_control": "none",
        "color_control": "none",
        "light_level": "none",
        "timer_hours": [],
        "has_timer_off": False,
        "has_sound": True,
        "extra_count": 0,
    }
    answers.update(overrides)
    return answers


def _defaults(result) -> dict:
    return {
        str(key): key.default()
        for key in result["data_schema"].schema
        if hasattr(key, "default") and callable(key.default)
    }


# --- The add form ---------------------------------------------------------------


async def test_a_name_already_used_is_a_form_error_not_the_end_of_the_flow(
    hass: HomeAssistant,
) -> None:
    """Reconfiguring already answers this with `name_already_used`; adding aborted,
    and every answer on the form was lost with it."""
    await setup_full(hass)
    taken = hass.config_entries.async_entries(DOMAIN)[0]
    assert taken.unique_id == "esp32_test_full"

    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(result["flow_id"], _declaration(fan_name="Full"))

    assert result["type"] == "form"
    assert result["errors"] == {"fan_name": "name_already_used"}
    assert _defaults(result)["speed_count"] == 4


async def test_an_unknown_gateway_keeps_the_rest_of_the_form(hass: HomeAssistant) -> None:
    register_stub(hass)
    await hass.async_block_till_done()
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"], _declaration(esphome_device="not-a-gateway")
    )

    assert result["errors"] == {"esphome_device": "unknown_esphome_device"}
    defaults = _defaults(result)
    assert defaults["speed_count"] == 4
    assert defaults["light_control"] == "on_off"
    assert defaults["has_sound"] is True


# --- Free-form keys left unnamed ------------------------------------------------


async def test_an_unnamed_free_form_key_takes_its_translated_name(hass: HomeAssistant) -> None:
    """Stored as "Extra key 1" it read in English whatever the language; the French
    label has always been in `fr.json`, unused."""
    hass.config.language = "fr"
    register_stub(hass)
    entry = full_entry(
        hass,
        extra_codes={"extra_1": "c_x1"},
        extra_data={"extra_count": 1, "extra_names": {"extra_1": ""}},
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    names = [
        hass.states.get(entity_id).attributes["friendly_name"]
        for entity_id in hass.states.async_entity_ids("button")
    ]
    assert any("Touche supplémentaire 1" in name for name in names), names


# --- Walks ------------------------------------------------------------------------


def _gate(monkeypatch):
    first_step_done = asyncio.Event()
    release = asyncio.Event()

    async def _gated_sleep(delay: float) -> None:
        if not first_step_done.is_set():
            first_step_done.set()
            await release.wait()

    monkeypatch.setattr("custom_components.rf_fan.entity.sleep", _gated_sleep)
    return first_step_done, release


async def test_three_moves_in_a_row_never_run_two_walks_at_once(
    hass: HomeAssistant, monkeypatch
) -> None:
    """The second move cancels the first and waits for it; a third arriving in that
    wait found the axis empty and started beside the second."""
    entry, calls = await setup_relative(hass)
    light_id = one_id(hass, "light")
    await hass.services.async_call("light", "turn_on", {"entity_id": light_id}, blocking=True)
    calls.clear()
    first_step_done, release = _gate(monkeypatch)

    def _move(brightness: int):
        return asyncio.create_task(
            hass.services.async_call(
                "light", "turn_on", {"entity_id": light_id, "brightness": brightness},
                blocking=True,
            )
        )

    first = _move(255)
    await asyncio.wait_for(first_step_done.wait(), timeout=5)
    second, third = _move(153), _move(51)
    release.set()
    await asyncio.gather(first, second, third)
    await hass.async_block_till_done()

    # The last move wins, planned from wherever the lamp really was.
    assert entry.runtime_data.level_position == 1
    sent = actions_sent(calls)
    assert sent.count("light_bright_up") - sent.count("light_bright_down") == 1


async def test_a_reload_stops_a_walk_in_flight(hass: HomeAssistant, monkeypatch) -> None:
    """A walk outlived its entry: after a reconfigure it went on pressing keys
    against runtime data nothing read any more."""
    entry, calls = await setup_relative(hass)
    light_id = one_id(hass, "light")
    await hass.services.async_call("light", "turn_on", {"entity_id": light_id}, blocking=True)
    calls.clear()
    first_step_done, release = _gate(monkeypatch)

    climbing = asyncio.create_task(
        hass.services.async_call(
            "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
        )
    )
    await asyncio.wait_for(first_step_done.wait(), timeout=5)

    assert await hass.config_entries.async_reload(entry.entry_id)
    release.set()
    await asyncio.gather(climbing, return_exceptions=True)
    await hass.async_block_till_done()

    assert actions_sent(calls).count("light_bright_up") == 1
