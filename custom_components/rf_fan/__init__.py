"""Generic integration for RF fans."""

from __future__ import annotations

import logging
from pathlib import Path

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import CONF_ESPHOME_DEVICE, CONF_GATEWAY_SERVICE, DOMAIN
from .data import RfFanConfigEntry, RfFanRuntimeData

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SENSOR,
]

CARD_URL = "/rf_fan_frontend/rf-fan-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the bundled Lovelace card (served and auto-loaded by the frontend)."""
    try:
        await _async_register_card(hass)
    except Exception:  # pragma: no cover - card registration is best-effort
        _LOGGER.warning("RF Fan: could not register the bundled card", exc_info=True)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and add it as a frontend module."""
    from homeassistant.components import frontend
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.loader import async_get_integration

    card_path = Path(__file__).parent / "frontend" / "rf-fan-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), True)]
    )
    # Cache-bust with the integration version from manifest.json: single
    # source of truth, so the browser refetches the card on every release.
    integration = await async_get_integration(hass, DOMAIN)
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries.

    v1 -> v2: store the raw ESPHome service prefix (gateway_service). New
    entries capture it from the live service registry at flow time; for
    migrated entries the historical dash->underscore derivation is used, which
    matches the exact behavior these entries relied on so far.
    """
    if entry.version > 2:
        # Entry created by a newer version of the integration: cannot downgrade.
        return False
    if entry.version < 2:
        data = dict(entry.data)
        data.setdefault(
            CONF_GATEWAY_SERVICE, data[CONF_ESPHOME_DEVICE].replace("-", "_")
        )
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.debug("Migrated config entry %s to version 2", entry.entry_id)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RfFanConfigEntry) -> bool:
    """Initialize an RF fan config entry."""
    entry.runtime_data = RfFanRuntimeData()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RfFanConfigEntry) -> bool:
    """Unload an RF fan config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
