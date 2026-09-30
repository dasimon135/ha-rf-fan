"""Sensor platform for RF Fan (assumed sleep-timer switch-off time)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .actions import timer_hours_from_data
from .const import ACTION_TIMER_OFF, EVENT_RF_FAN_RECEIVED, timer_action
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sleep-timer sensor if the fan has at least one timer key."""
    if not timer_hours_from_data(dict(config_entry.data)):
        return

    async_add_entities([RfFanTimerSensor(hass, config_entry)])


class RfFanTimerSensor(RfFanBaseEntity, RestoreEntity, SensorEntity):
    """The assumed switch-off time set by the sleep-timer buttons.

    Purely a local estimate (the fan gives no feedback): pressing a timer button
    records now + N hours; turning the fan off clears it.

    The same keys pressed on the physical remote do the same (#86), heard through
    the filters every other platform uses. Only where the remote can be followed at
    all: a raw-timings gateway reports nothing a learned code can be matched to.
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
        self._expiry_unsub = None
        self._event_unsub = None
        self._hours_by_action = {
            timer_action(hours): hours
            for hours in timer_hours_from_data(dict(config_entry.data))
        }

    @property
    def native_value(self):
        """Return the switch-off time, or None once it has passed / been cleared."""
        ends = self._runtime.timer_ends_at
        if ends is None or ends <= dt_util.utcnow():
            return None
        return ends

    async def async_added_to_hass(self) -> None:
        """Restore the switch-off time, then subscribe to timer changes."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable"):
            parsed = dt_util.parse_datetime(last_state.state)
            if parsed is not None and parsed > dt_util.utcnow():
                self._runtime.timer_ends_at = parsed
        self._signal_unsub = async_dispatcher_connect(
            self.hass, self._timer_signal(), self._on_timer_changed
        )
        self._schedule_expiry()
        self._event_unsub = self.hass.bus.async_listen(
            EVENT_RF_FAN_RECEIVED, self._handle_rf_event
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe the callbacks."""
        if self._signal_unsub is not None:
            self._signal_unsub()
            self._signal_unsub = None
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None
        self._cancel_expiry()

    def _cancel_expiry(self) -> None:
        """Drop any pending expiry callback."""
        if self._expiry_unsub is not None:
            self._expiry_unsub()
            self._expiry_unsub = None

    @callback
    def _schedule_expiry(self) -> None:
        """Wake up exactly when the switch-off time is reached.

        Nothing else would refresh the sensor at that moment, so without this the
        entity would keep publishing a switch-off time that is already in the past.
        """
        self._cancel_expiry()
        ends = self._runtime.timer_ends_at
        if ends is None or ends <= dt_util.utcnow():
            return
        self._expiry_unsub = async_track_point_in_utc_time(
            self.hass, self._on_expired, ends
        )

    @callback
    def _on_expired(self, _now) -> None:
        """The assumed switch-off time has been reached: clear it, and tell the fan."""
        self._expiry_unsub = None
        self._runtime.timer_ends_at = None
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, self._timer_elapsed_signal())

    @callback
    def _on_timer_changed(self) -> None:
        """Refresh the state when a timer is (re)started or cleared."""
        self._schedule_expiry()
        self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Follow a timer key pressed on the physical remote.

        Announced on the timer signal like a button press, which reschedules the
        expiry. That matters beyond the display: since #85 the expiry switches the
        fan off, and a timer cancelled from the remote must not take it down.
        """
        action = self._received_action(event)
        if action is None:
            return
        if action == ACTION_TIMER_OFF:
            self._runtime.timer_ends_at = None
        elif action in self._hours_by_action:
            self._runtime.timer_ends_at = dt_util.utcnow() + timedelta(
                hours=self._hours_by_action[action]
            )
        else:
            return
        async_dispatcher_send(self.hass, self._timer_signal())
