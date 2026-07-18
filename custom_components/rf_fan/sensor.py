"""Sensor platform for RF Fan (assumed sleep-timer switch-off time)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import CONF_HAS_TIMERS
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sleep-timer sensor if the fan has timers."""
    if not config_entry.data.get(CONF_HAS_TIMERS, False):
        return

    async_add_entities([RfFanTimerSensor(hass, config_entry)])


class RfFanTimerSensor(RfFanBaseEntity, RestoreEntity, SensorEntity):
    """The assumed switch-off time set by the sleep-timer buttons.

    Purely a local estimate (the fan gives no feedback): pressing a timer button
    records now + N hours; turning the fan off clears it.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_assumed_state = False
    # Informational estimate about the device, not a primary reading.
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the sleep-timer sensor."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_sleep_timer"
        self._attr_translation_key = "sleep_timer"
        self._signal_unsub = None

    @property
    def native_value(self):
        """Return the switch-off time, or None once it has passed / been cleared."""
        ends = self._entry_runtime().get("timer_ends_at")
        if ends is None or ends <= dt_util.utcnow():
            return None
        return ends

    async def async_added_to_hass(self) -> None:
        """Restore the switch-off time, then subscribe to timer changes."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable"):
            parsed = dt_util.parse_datetime(last_state.state)
            if parsed is not None and parsed > dt_util.utcnow():
                self._entry_runtime()["timer_ends_at"] = parsed
        self._signal_unsub = async_dispatcher_connect(
            self.hass, self._timer_signal(), self._on_timer_changed
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe the callback."""
        if self._signal_unsub is not None:
            self._signal_unsub()
            self._signal_unsub = None

    @callback
    def _on_timer_changed(self) -> None:
        """Refresh the state when a timer is (re)started or cleared."""
        self.async_write_ha_state()
