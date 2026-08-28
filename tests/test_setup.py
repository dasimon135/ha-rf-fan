"""Component setup: card registration and config-entry migration.

Requires a Home Assistant environment via phcc.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_fan.const import CONF_DISABLE_CARD, DOMAIN
from tests.ha_helpers import CODES, DEVICE, full_entry, register_stub, setup_full


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


async def test_the_card_opt_out_says_which_fan_switched_it_off(
    hass: HomeAssistant, caplog
) -> None:
    """The checkbox is per fan; its effect is global. The log has to name whose.

    @elmr91 lost the card on every dashboard because one of several fans still had
    the option set from an earlier install ([#29](https://github.com/dasimon135/ha-rf-fan/issues/29)).
    Nothing in the frontend says why a card is missing, and the entry to look at may
    be one nobody has opened in months -- so the one place that can answer is the
    log, and it was whispering it at INFO without naming anybody.
    """
    register_stub(hass)
    living = full_entry(hass)
    hass.config_entries.async_update_entry(living, title="Living room")
    bedroom = full_entry(hass)
    hass.config_entries.async_update_entry(
        bedroom, title="Bedroom", options={CONF_DISABLE_CARD: True}
    )

    assert await hass.config_entries.async_setup(living.entry_id)
    await hass.async_block_till_done()

    named = [
        record
        for record in caplog.records
        if record.levelname == "WARNING" and "Bedroom" in record.getMessage()
    ]
    assert named, "the fan holding the option open must be named, loudly enough to be seen"

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

    assert entry.version == 4
    assert entry.data["gateway_service"] == "esp32_test"


async def test_entry_from_a_newer_version_is_refused(hass: HomeAssistant) -> None:
    """An entry written by a future release must not be silently downgraded."""
    entry = MockConfigEntry(domain=DOMAIN, version=5, title="Future", data={})
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

    assert entry.version == 4
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
async def test_migrate_v3_entry_turns_the_natural_boolean_into_a_selector(
    hass: HomeAssistant,
) -> None:
    """A boolean can only describe one shape of airflow key, and it described `toggle`.

    Every existing entry was configured against a key assumed to flip the preset, so
    that is what they land on. `dedicated` is a claim about the hardware that only
    its owner can make, and it is never inferred here.
    """
    register_stub(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="Breeze",
        data={
            "esphome_device": DEVICE,
            "gateway_service": "esp32_test",
            "fan_name": "Breeze",
            "speed_count": 3,
            "light_control": "toggle",
            "has_light": True,
            "direction_control": "none",
            "color_control": "none",
            "light_level": "none",
            "has_natural_preset": True,
            "codes": dict(CODES),
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 4
    assert entry.data["natural_control"] == "toggle"
    # Dropped rather than left behind: two answers to "does this fan have a breeze
    # key?" is how they drift apart.
    assert "has_natural_preset" not in entry.data
    assert entry.data["codes"] == dict(CODES)


async def test_migrate_v3_entry_without_the_boolean_lands_on_none(
    hass: HomeAssistant,
) -> None:
    """An absent boolean means the capability was declined, not unknown."""
    register_stub(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="Plain",
        data={
            "esphome_device": DEVICE,
            "gateway_service": "esp32_test",
            "fan_name": "Plain",
            "speed_count": 3,
            "light_control": "toggle",
            "has_light": True,
            "direction_control": "none",
            "color_control": "none",
            "light_level": "none",
            "codes": dict(CODES),
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data["natural_control"] == "none"
