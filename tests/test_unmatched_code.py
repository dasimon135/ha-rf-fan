"""A received code that matches no learned action must be visible.

The passive "follow the physical remote" feature compares the sniffed code to
the learned codes by exact string equality. When the gateway's code format
changes (or the remote was learned through a different YAML), nothing matches
and the feature goes silently dead — which reads as "the feature does not
work" rather than "these two codes differ". Recording the last unmatched code
turns that into something the user can actually see in the diagnostics.
"""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from custom_components.rf_fan.diagnostics import async_get_config_entry_diagnostics
from tests.ha_helpers import fire_rf, setup_full

UNKNOWN = "1:001100110011001100110011"


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def test_an_unmatched_code_is_recorded(hass: HomeAssistant) -> None:
    """A sniffed code mapped to no action is kept for diagnostics."""
    entry, _ = await setup_full(hass)

    await fire_rf(hass, UNKNOWN)

    assert entry.runtime_data.last_unmatched_code == UNKNOWN


async def test_a_learned_code_is_not_recorded_as_unmatched(
    hass: HomeAssistant,
) -> None:
    """A code that does map to an action leaves the diagnostic field alone."""
    entry, _ = await setup_full(hass)

    await fire_rf(hass, "c_s2")

    assert entry.runtime_data.last_unmatched_code is None


async def test_a_frame_from_another_gateway_is_not_recorded(
    hass: HomeAssistant,
) -> None:
    """Another gateway's traffic is not this entry's problem."""
    entry, _ = await setup_full(hass)

    await fire_rf(hass, UNKNOWN, device="some-other-gateway")

    assert entry.runtime_data.last_unmatched_code is None


async def test_the_unmatched_code_is_logged_once_not_once_per_platform(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Every platform of the entry sees the event; only one log line comes out."""
    await setup_full(hass)

    with caplog.at_level(logging.DEBUG, logger="custom_components.rf_fan.entity"):
        await fire_rf(hass, UNKNOWN)

    lines = [r for r in caplog.records if UNKNOWN in r.getMessage()]
    assert len(lines) == 1, f"expected exactly one log line, got {len(lines)}"


async def test_diagnostics_expose_the_unmatched_code(hass: HomeAssistant) -> None:
    """The recorded code reaches the downloadable diagnostics."""
    entry, _ = await setup_full(hass)

    await fire_rf(hass, UNKNOWN)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["runtime"]["last_unmatched_code"] == UNKNOWN
