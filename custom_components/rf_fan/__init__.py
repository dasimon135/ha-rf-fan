"""Generic integration for RF fans."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, HomeAssistant, callback
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
    CONF_HAS_NATURAL_PRESET,
    CONF_HAS_TIMER_OFF,
    CONF_HAS_TIMERS,
    CONF_LIGHT_LEVEL,
    CONF_NATURAL_CONTROL,
    CONF_TIMER_HOURS,
    DIRECTION_CONTROL_NONE,
    DIRECTION_CONTROL_TOGGLE,
    DOMAIN,
    LIGHT_LEVEL_NONE,
    NATURAL_CONTROL_NONE,
    NATURAL_CONTROL_TOGGLE,
    TIMER_HOURS,
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
    """Serve the card file, then get the browser to load it.

    Two mechanisms, and they are not equivalent. A Lovelace resource is loaded by
    Lovelace itself, which waits for it before rendering any card; a frontend
    module URL is handed to the shell and nothing waits for it. The second is what
    the integration used to do, and what lost @elmr91 the card on about one hard
    reload in three (#44).
    """
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

    integration = await async_get_integration(hass, DOMAIN)
    # Cache-bust with the integration version from manifest.json: single source of
    # truth, so the browser refetches the card on every release.
    url = f"{CARD_URL}?v={integration.version}"

    if await _async_register_resource(hass, url):
        return

    # Lovelace is not up yet, or is not there at all. Try once more when Home
    # Assistant has finished starting, and only fall back if that fails too --
    # doing both would put two copies of the card in the same page, and the loser
    # of that race cannot be replaced.
    if hass.state is CoreState.running:
        _async_add_module_url(hass, url)
        return

    async def _retry(_event: Any) -> None:
        if not await _async_register_resource(hass, url):
            _async_add_module_url(hass, url)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _retry)


async def _async_register_resource(hass: HomeAssistant, url: str) -> bool:
    """Register the card as a Lovelace resource. True when it is registered.

    This is how HACS delivers every custom card, and the difference is not
    cosmetic: Lovelace loads its own resources and WAITS for them before it renders
    a card, while nothing waits for a frontend module URL. @elmr91 lost the card on
    about one hard reload in three through the module list, and never once through
    a resource he had registered by hand (#44).

    Storage mode only. In YAML mode the resource list is the user's file and this
    integration has no business writing to it, so the caller falls back.
    """
    try:
        from homeassistant.components.lovelace.const import (
            LOVELACE_DATA,
            MODE_STORAGE,
        )
    except ImportError:  # pragma: no cover - lovelace is a core component
        return False

    data = hass.data.get(LOVELACE_DATA)
    if data is None or data.resource_mode != MODE_STORAGE:
        return False

    resources = data.resources
    # `async_items()` does NOT read the store, while `async_create_item()` does. So
    # on a start where Lovelace has not read its resources yet, the collection
    # answers "empty", this decides nothing is registered, and the create -- which
    # loads first -- appends a second copy of what was already there. One more per
    # restart, all identical, and the card then races itself (#44, @elmr91 woke up
    # to two). `async_get_info()` is the public way to make sure it has been read.
    await resources.async_get_info()

    # Matched on the PATH, not the whole URL: the version query changes with every
    # release, and a copy the user registered by hand carries a different one (or
    # none). Adopting that copy is what keeps a hand-registered entry from becoming
    # a second, stale card -- the exact failure of issue #29.
    ours = [
        item
        for item in resources.async_items()
        if str(item.get("url", "")).split("?")[0] == CARD_URL
    ]

    if not ours:
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.debug("Registered the card as a Lovelace resource: %s", url)
        return True

    keep, *extras = ours
    if keep.get("url") != url:
        await resources.async_update_item(keep["id"], {"url": url})
        _LOGGER.debug("Updated the card resource to %s", url)
    # Duplicates left by the defect above, or by anything else. Fixing the cause
    # would otherwise leave them as somebody's manual chore, on an install where
    # two copies of the card race and the loser cannot be replaced.
    for extra in extras:
        await resources.async_delete_item(extra["id"])
        _LOGGER.warning(
            "Removed a duplicate registration of the RF Fan card (%s); "
            "two copies race to define the same element and the older one wins",
            extra.get("url"),
        )
    return True


def _async_add_module_url(hass: HomeAssistant, url: str) -> None:
    """Fall back to the frontend's extra module list.

    `after_dependencies` only ORDERS the setup when the frontend is set up at all;
    it does not guarantee it exists. Without it there is no module list to add the
    card to -- expected on a headless install, not an error.
    """
    from homeassistant.components import frontend

    if "frontend" not in hass.config.components:
        _LOGGER.debug(
            "Frontend not loaded: the card stays served at %s but is not auto-loaded",
            CARD_URL,
        )
        return
    frontend.add_extra_js_url(hass, url)


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

    v3 -> v4: the natural-airflow preset becomes a selector for the same reason
    (const.CONF_NATURAL_CONTROL). Every existing entry was set up against a key
    assumed to toggle, so that is what they migrate to — `dedicated` is a claim
    about the hardware that only its owner can make.

    v4 -> v5: `has_timers` becomes the list of durations the remote actually has
    (const.CONF_TIMER_HOURS), because demanding all of 1/2/4/8 stopped a remote with
    off/2/4/8 declaring timers at all (#59). An entry that had timers migrates to all
    four — that is exactly what the boolean meant — so NO CODE CHANGES NAME and
    nothing is relearned. The new `has_timer_off` is a claim about the hardware
    nobody has been asked yet, so it starts False.
    """
    if entry.version > 5:
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
    if entry.version < 4:
        data = dict(entry.data)
        # Same rule as the selectors above: an explicit answer outranks the boolean
        # it replaced, and the boolean is dropped rather than left to disagree with
        # it later. No code changes name, so nothing is relearned.
        data.setdefault(
            CONF_NATURAL_CONTROL,
            NATURAL_CONTROL_TOGGLE
            if data.get(CONF_HAS_NATURAL_PRESET, False)
            else NATURAL_CONTROL_NONE,
        )
        data.pop(CONF_HAS_NATURAL_PRESET, None)
        hass.config_entries.async_update_entry(entry, data=data, version=4)
        _LOGGER.debug("Migrated config entry %s to version 4", entry.entry_id)
    if entry.version < 5:
        data = dict(entry.data)
        # Same rule as every selector above: an explicit answer outranks the boolean
        # it replaced. Stored as strings because that is what the multi-select
        # submits, and `timer_hours_from_data` normalises either shape on read.
        data.setdefault(
            CONF_TIMER_HOURS,
            [str(hours) for hours in TIMER_HOURS]
            if data.get(CONF_HAS_TIMERS, False)
            else [],
        )
        data.setdefault(CONF_HAS_TIMER_OFF, False)
        data.pop(CONF_HAS_TIMERS, None)
        hass.config_entries.async_update_entry(entry, data=data, version=5)
        _LOGGER.debug("Migrated config entry %s to version 5", entry.entry_id)
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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Take the card's Lovelace resource with the last fan that needed it.

    A resource is persistent and outlives the integration that created it. Left
    behind, it points at a file nothing serves any more, and Home Assistant reports
    that on every dashboard — to a user who has just uninstalled the thing
    responsible and has no way to connect the two.

    Only when the last entry goes: one registration serves every fan.
    """
    if [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ]:
        return

    try:
        from homeassistant.components.lovelace.const import (
            LOVELACE_DATA,
            MODE_STORAGE,
        )
    except ImportError:  # pragma: no cover - lovelace is a core component
        return

    data = hass.data.get(LOVELACE_DATA)
    if data is None or data.resource_mode != MODE_STORAGE:
        return

    for item in list(data.resources.async_items()):
        if str(item.get("url", "")).split("?")[0] == CARD_URL:
            await data.resources.async_delete_item(item["id"])
            _LOGGER.debug("Removed the card resource with the last RF Fan entry")


async def async_unload_entry(hass: HomeAssistant, entry: RfFanConfigEntry) -> bool:
    """Unload an RF fan config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
