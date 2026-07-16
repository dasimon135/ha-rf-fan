"""Generic integration for RF fans."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

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

CARD_VERSION = "1.4.1"
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

    card_path = Path(__file__).parent / "frontend" / "rf-fan-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), True)]
    )
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize an RF fan config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "kelvin_position": 0,
        "light_on": None,
        "timer_ends_at": None,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an RF fan config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
