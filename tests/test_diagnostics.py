"""Diagnostics payload (requires a Home Assistant environment via phcc).

Diagnostics is what a user attaches to a bug report, so it has to carry the
assumed state — the dead-reckoned colour position, the anti-echo window, the
sleep timer. Those are exactly the things that go wrong and none of them can be
read back from the hardware.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from custom_components.rf_fan.diagnostics import async_get_config_entry_diagnostics
from tests.ha_helpers import one_id, setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def test_diagnostics_report_the_assumed_runtime_state(hass: HomeAssistant) -> None:
    """A fresh entry reports its starting assumed state."""
    entry, _calls = await setup_full(hass)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    runtime = diag["runtime"]
    assert runtime["kelvin_position"] == 0
    assert runtime["colour"] == "Chaud"
    assert runtime["light_on"] is None
    assert runtime["timer_ends_at"] is None
    assert runtime["armed_echo_codes"] == 0


async def test_diagnostics_follow_the_state_as_it_changes(hass: HomeAssistant) -> None:
    """Turning the light on bumps the colour and arms the anti-echo window."""
    entry, _calls = await setup_full(hass)
    light_id = one_id(hass, "light")

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()

    runtime = (await async_get_config_entry_diagnostics(hass, entry))["runtime"]
    assert runtime["light_on"] is True
    # The hardware advances the colour on a real OFF->ON transition.
    assert runtime["kelvin_position"] == 1
    assert runtime["colour"] == "Neutre"
    assert runtime["armed_echo_codes"] == 1


async def test_diagnostics_still_redact_the_gateway(hass: HomeAssistant) -> None:
    """The gateway names stay redacted; the codes stay visible (they are the point)."""
    entry, _calls = await setup_full(hass)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["config"]["esphome_device"] == "**REDACTED**"
    assert diag["summary"]["action_count"] == len(entry.data["codes"])
