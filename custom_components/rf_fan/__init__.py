"""Generic integration for RF fans."""

from __future__ import annotations

import logging
from pathlib import Path

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .actions import expected_unique_ids
from .const import (
    COLOR_CONTROL_CYCLE,
    COLOR_CONTROL_NONE,
    CONF_COLOR_CONTROL,
    CONF_DIRECTION_CONTROL,
    CONF_DISABLE_CARD,
    CONF_ESPHOME_DEVICE,
    CONF_GATEWAY_SERVICE,
    CONF_HAS_COLOR_TEMP,
    CONF_HAS_DIRECTION,
    CONF_LIGHT_LEVEL,
    DIRECTION_CONTROL_NONE,
    DIRECTION_CONTROL_TOGGLE,
    DOMAIN,
    LIGHT_LEVEL_NONE,
)
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
        _LOGGER.error(
            "RF Fan: failed to register the bundled Lovelace card; it will not "
            "load automatically and the dashboard card will show as missing. "
            "You can add it manually as a dashboard resource pointing at %s "
            "(see the README section 'Dashboard card'), then restart Home "
            "Assistant to retry automatic registration",
            CARD_URL,
            exc_info=True,
        )
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and add it as a frontend module."""
    from homeassistant.components import frontend
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.loader import async_get_integration

    card_path = Path(__file__).parent / "frontend" / "rf-fan-card.js"
    # cache_headers=False, deliberately. With it on, Home Assistant serves the file
    # `public, max-age=2678400` — 31 days. The `?v=` below makes our own URL immune,
    # because it changes with every release, but a dashboard resource a user added
    # by hand does not: that URL is frozen for a month, and no reload revalidates
    # it. @elmr91 upgraded twice and his browser kept executing the 1.7.0 card
    # (#29). One conditional request per page load for a 30 KB file is the right
    # price for a card that changes every release.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), False)]
    )

    # Opt-out (integration options): keep serving the file so a manually
    # managed dashboard resource still works, but skip the auto-load.
    #
    # The option sits on a config entry but the card is registered once for the
    # whole frontend, so one fan opting out silences it for every fan. Naming the
    # entries is the whole value of this message: the card disappears from every
    # dashboard at once, the frontend says nothing about why, and the checkbox to
    # clear may be on a fan nobody has opened in months (#29). At INFO and
    # anonymous it was unfindable.
    opted_out = [
        entry.title
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.options.get(CONF_DISABLE_CARD, False)
    ]
    if opted_out:
        _LOGGER.warning(
            "RF Fan: the bundled card will NOT load automatically for any fan, "
            "because 'Disable automatic dashboard card loading' is set on: %s. "
            "The option is per fan but its effect is global — clear it on every "
            "fan listed and restart Home Assistant to get the card back. The card "
            "file stays served at %s for manual resource management",
            ", ".join(opted_out),
            CARD_URL,
        )
        return

    # `after_dependencies` only ORDERS the setup when the frontend is set up at
    # all; it does not guarantee it exists. Without it there is no module list to
    # add the card to — expected on a headless install, not an error.
    if "frontend" not in hass.config.components:
        _LOGGER.debug(
            "Frontend not loaded: the card stays served at %s but is not auto-loaded",
            CARD_URL,
        )
        return

    # Cache-bust with the integration version from manifest.json: single
    # source of truth, so the browser refetches the card on every release.
    integration = await async_get_integration(hass, DOMAIN)
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries.

    Written as cumulative steps, so an entry several versions behind is brought
    forward one step at a time.

    v1 -> v2: store the raw ESPHome service prefix (gateway_service). New
    entries capture it from the live service registry at flow time; for
    migrated entries the historical dash->underscore derivation is used, which
    matches the exact behavior these entries relied on so far.

    v2 -> v3: two capabilities become selectors, because the remote can express
    them in more than one shape (see const.CONF_DIRECTION_CONTROL /
    CONF_COLOR_CONTROL), and brightness appears as a third. NO LEARNED CODE IS
    INVALIDATED: every existing action key keeps its exact name, so nobody has to
    relearn a button they already taught.
    """
    if entry.version > 3:
        # Entry created by a newer version of the integration: cannot downgrade.
        return False
    if entry.version < 2:
        data = dict(entry.data)
        data.setdefault(
            CONF_GATEWAY_SERVICE, data[CONF_ESPHOME_DEVICE].replace("-", "_")
        )
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.debug("Migrated config entry %s to version 2", entry.entry_id)
    if entry.version < 3:
        data = dict(entry.data)
        # `setdefault`, not assignment: a selector that is already present was set
        # deliberately and outranks the boolean it replaced. Deriving over the top
        # of it would silently undo the user's answer.
        data.setdefault(
            CONF_DIRECTION_CONTROL,
            DIRECTION_CONTROL_TOGGLE
            if data.get(CONF_HAS_DIRECTION, False)
            else DIRECTION_CONTROL_NONE,
        )
        data.setdefault(
            CONF_COLOR_CONTROL,
            COLOR_CONTROL_CYCLE
            if data.get(CONF_HAS_COLOR_TEMP, False)
            else COLOR_CONTROL_NONE,
        )
        # New capability, so nothing to carry over: an existing entry has never
        # been asked whether its remote has brightness keys.
        data.setdefault(CONF_LIGHT_LEVEL, LIGHT_LEVEL_NONE)
        # The booleans they replace are dropped rather than left behind, so there
        # is only one answer to "does this fan reverse?" in the stored data.
        data.pop(CONF_HAS_DIRECTION, None)
        data.pop(CONF_HAS_COLOR_TEMP, None)
        hass.config_entries.async_update_entry(entry, data=data, version=3)
        _LOGGER.debug("Migrated config entry %s to version 3", entry.entry_id)
    return True


@callback
def _async_remove_stale_entities(hass: HomeAssistant, entry: RfFanConfigEntry) -> None:
    """Drop registry rows for capabilities that are no longer enabled.

    A reconfiguration that turns a capability off just stops its platform from
    creating the entity; the registry row would survive as a permanently
    unavailable entity that the user cannot delete.
    """
    registry = er.async_get(hass)
    expected = expected_unique_ids(entry.entry_id, entry.data)
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.unique_id not in expected:
            _LOGGER.debug(
                "Removing %s: its capability is no longer enabled", registered.entity_id
            )
            registry.async_remove(registered.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: RfFanConfigEntry) -> bool:
    """Initialize an RF fan config entry."""
    entry.runtime_data = RfFanRuntimeData()
    _async_remove_stale_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RfFanConfigEntry) -> bool:
    """Unload an RF fan config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
