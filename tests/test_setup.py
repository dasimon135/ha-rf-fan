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
    """A pre-v2 entry gains `gateway_service` from the historical dash->underscore rule."""
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

    assert entry.version == 2
    assert entry.data["gateway_service"] == "esp32_test"


async def test_entry_from_a_newer_version_is_refused(hass: HomeAssistant) -> None:
    """An entry written by a future release must not be silently downgraded."""
    entry = MockConfigEntry(domain=DOMAIN, version=3, title="Future", data={})
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
