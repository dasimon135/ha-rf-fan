"""Fan platform for RF Fan."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import (
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ACTION_FAN_NATURAL,
    ACTION_FAN_OFF,
    ACTION_FAN_ON,
    ACTION_FAN_REVERSE,
    CONF_HAS_DIRECTION,
    CONF_HAS_NATURAL_PRESET,
    CONF_SPEED_COUNT,
    EVENT_RF_FAN_RECEIVED,
    PRESET_NATURAL,
    PRESET_NORMAL,
    speed_action,
)
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the fan entity."""
    async_add_entities([RfFanEntity(hass, config_entry)])


class RfFanEntity(RfFanBaseEntity, RestoreEntity, FanEntity):
    """Generic RF fan with assumed state."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the fan entity."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_fan"
        # Primary entity of the device: name=None makes it carry the device
        # name (avoids a redundant "…Fan" suffix).
        self._attr_name = None
        self._speed_count: int = int(config_entry.data[CONF_SPEED_COUNT])
        self._is_on: bool | None = None
        self._percentage: int | None = None
        self._event_unsub = None

        # Optional capabilities (config flow)
        self._has_direction: bool = config_entry.data.get(CONF_HAS_DIRECTION, False)
        self._has_preset: bool = config_entry.data.get(CONF_HAS_NATURAL_PRESET, False)

        # Supported features computed per instance based on the capabilities
        features = (
            FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
            | FanEntityFeature.SET_SPEED
        )
        if self._has_direction:
            features |= FanEntityFeature.DIRECTION
        if self._has_preset:
            features |= FanEntityFeature.PRESET_MODE
        self._attr_supported_features = features

        if self._has_preset:
            self._attr_preset_modes = [PRESET_NORMAL, PRESET_NATURAL]

        # Assumed state of the optional capabilities
        self._direction: str | None = None
        self._preset: str | None = None

    @property
    def is_on(self) -> bool | None:
        """Return the assumed on/off state."""
        return self._is_on

    @property
    def percentage(self) -> int | None:
        """Return the speed as a percentage."""
        return self._percentage

    @property
    def current_direction(self) -> str | None:
        """Return the assumed rotation direction."""
        return self._direction

    @property
    def preset_mode(self) -> str | None:
        """Return the assumed preset."""
        return self._preset

    @property
    def percentage_step(self) -> float:
        """Return the supported speed step."""
        return 100 / self._speed_count

    async def async_added_to_hass(self) -> None:
        """Restore the assumed state (on/off, speed, direction, preset), then subscribe to RF events."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._is_on = last_state.state == "on"
            pct = last_state.attributes.get("percentage")
            if isinstance(pct, (int, float)):
                self._percentage = int(pct)
            if self._has_direction:
                direction = last_state.attributes.get("direction")
                if direction in (DIRECTION_FORWARD, DIRECTION_REVERSE):
                    self._direction = direction
            if self._has_preset:
                preset = last_state.attributes.get("preset_mode")
                if preset in (PRESET_NORMAL, PRESET_NATURAL):
                    self._preset = preset
        self._event_unsub = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, self._handle_rf_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe the callbacks."""
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None

    def _clear_timer(self) -> None:
        """Clear the assumed sleep-timer when the fan is switched off."""
        if self._entry_runtime().get("timer_ends_at") is not None:
            self._entry_runtime()["timer_ends_at"] = None
            async_dispatcher_send(self.hass, self._timer_signal())

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan."""
        if percentage is not None:
            await self.async_set_percentage(percentage)
            return

        sent = await self._async_transmit_action(ACTION_FAN_ON)
        if not sent:
            sent = await self._async_transmit_action(speed_action(1))

        if sent:
            self._is_on = True
            if self._percentage is None or self._percentage <= 0:
                self._percentage = round(100 / self._speed_count)
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        sent = await self._async_transmit_action(ACTION_FAN_OFF)
        if sent:
            self._is_on = False
            self._percentage = 0
            self._clear_timer()
            self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed via a fan_speed_X action."""
        if percentage <= 0:
            await self.async_turn_off()
            return

        step = 100 / self._speed_count
        speed_index = max(1, min(self._speed_count, int(round(percentage / step))))
        sent = await self._async_transmit_action(speed_action(speed_index))
        if sent:
            self._is_on = True
            self._percentage = int(round(speed_index * step))
            self.async_write_ha_state()

    async def async_set_direction(self, direction: str) -> None:
        """Toggle the rotation direction (single-toggle remote)."""
        if self._direction == direction:
            return
        # Assumed state: from an unknown direction (None), a single toggle cannot
        # guarantee the absolute target (inherent limitation of assumed_state).
        sent = await self._async_transmit_action(ACTION_FAN_REVERSE)
        if sent:
            self._direction = direction
            self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Toggle the natural airflow preset (single-toggle remote)."""
        if self._preset == preset_mode:
            return
        sent = await self._async_transmit_action(ACTION_FAN_NATURAL)
        if sent:
            self._preset = preset_mode
            self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Update the local state when the physical remote is used."""
        if self._recently_transmitted():
            return

        action = self._event_action(event.data)
        if action is None:
            return

        if action == ACTION_FAN_OFF:
            self._is_on = False
            self._percentage = 0
            self._clear_timer()
            self.async_write_ha_state()
            return

        if action == ACTION_FAN_ON:
            self._is_on = True
            if self._percentage is None or self._percentage <= 0:
                self._percentage = int(round(100 / self._speed_count))
            self.async_write_ha_state()
            return

        if action == ACTION_FAN_REVERSE:
            self._direction = (
                DIRECTION_FORWARD
                if self._direction == DIRECTION_REVERSE
                else DIRECTION_REVERSE
            )
            self.async_write_ha_state()
            return

        if action == ACTION_FAN_NATURAL:
            self._preset = (
                PRESET_NORMAL if self._preset == PRESET_NATURAL else PRESET_NATURAL
            )
            self.async_write_ha_state()
            return

        for idx in range(1, self._speed_count + 1):
            if action == speed_action(idx):
                self._is_on = True
                self._percentage = int(round(idx * (100 / self._speed_count)))
                self.async_write_ha_state()
                return
