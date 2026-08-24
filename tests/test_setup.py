"""Component setup: card registration and config-entry migration.

Requires a Home Assistant environment via phcc.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_fan.const import DOMAIN
from tests.ha_helpers import CODES, DEVICE, register_stub, setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def test_setup_does_not_error_when_the_frontend_is_absent(
    hass: HomeAssistant, caplog
) -> None:
    """`after_dependencies` does not guarantee the frontend is loaded.

    It only orders the setup *if* the frontend is set up at all. On an installation
    without it, auto-loading the card is simply not possible — that is expected, not
    an error worth a stack trace in the log.
    """
    assert "frontend" not in hass.config.components

    await setup_full(hass)

    assert "failed to register the bundled Lovelace card" not in caplog.text


async def test_migrate_v1_entry_derives_the_gateway_service(hass: HomeAssistant) -> None:
    """A pre-v2 entry is brought all the way forward, one cumulative step at a time."""
    register_stub(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title="Legacy",
        data={
            "esphome_device": DEVICE,
            "fan_name": "Legacy",
            "speed_count": 3,
            "light_control": "toggle",
            "has_light": True,
            "codes": dict(CODES),
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 3
    assert entry.data["gateway_service"] == "esp32_test"


async def test_entry_from_a_newer_version_is_refused(hass: HomeAssistant) -> None:
    """An entry written by a future release must not be silently downgraded."""
    entry = MockConfigEntry(domain=DOMAIN, version=4, title="Future", data={})
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_migrate_v2_entry_turns_the_booleans_into_selectors(
    hass: HomeAssistant,
) -> None:
    """A v2 entry keeps every learned code and gains the new capability shapes.

    The booleans could only express one shape each. The selectors that replace them
    must land on exactly that shape, and the old keys must not survive alongside:
    two answers to "does this fan reverse?" is how they drift apart.
    """
    register_stub(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Legacy",
        data={
            "esphome_device": DEVICE,
            "gateway_service": "esp32_test",
            "fan_name": "Legacy",
            "speed_count": 3,
            "light_control": "toggle",
            "has_light": True,
            "has_direction": True,
            "has_color_temp": True,
            "codes": dict(CODES),
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 3
    assert entry.data["direction_control"] == "toggle"
    assert entry.data["color_control"] == "cycle"
    assert entry.data["light_level"] == "none"
    assert "has_direction" not in entry.data
    assert "has_color_temp" not in entry.data
    # The whole point of keeping the action names: nobody relearns a button.
    assert entry.data["codes"] == dict(CODES)


async def test_migrate_v2_entry_without_capabilities_lands_on_none(
    hass: HomeAssistant,
) -> None:
    """Absent booleans mean the capability was declined, not unknown."""
    register_stub(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Plain",
        data={
            "esphome_device": DEVICE,
            "gateway_service": "esp32_test",
            "fan_name": "Plain",
            "speed_count": 3,
            "light_control": "toggle",
            "has_light": True,
            "codes": dict(CODES),
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data["direction_control"] == "none"
    assert entry.data["color_control"] == "none"
    assert entry.data["light_level"] == "none"
