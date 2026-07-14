"""Button platform for RF Fan (sleep timers)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HAS_COLOR_TEMP, CONF_HAS_TIMERS, TIMER_HOURS, timer_action
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the buttons (timers and/or color calibration)."""
    entities: list[ButtonEntity] = []

    if config_entry.data.get(CONF_HAS_TIMERS, False):
        entities.extend(
            RfFanTimerButton(hass, config_entry, hours) for hours in TIMER_HOURS
        )

    if config_entry.data.get(CONF_HAS_COLOR_TEMP, False):
        entities.append(RfFanKelvinCalibrateButton(hass, config_entry))

    if entities:
        async_add_entities(entities)


class RfFanTimerButton(RfFanBaseEntity, ButtonEntity):
    """Button that triggers an N-hour sleep timer."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, hours: int) -> None:
        """Initialize the timer button."""
        super().__init__(hass, config_entry)
        self._hours = hours
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{hours}h"
        self._attr_translation_key = "timer"
        self._attr_translation_placeholders = {"hours": str(hours)}

    async def async_press(self) -> None:
        """Emit the corresponding timer action."""
        await self._async_transmit_action(timer_action(self._hours))


class RfFanKelvinCalibrateButton(RfFanBaseEntity, ButtonEntity):
    """Calibration button: resets the assumed color position to "Warm"."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the color calibration button."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_kelvin_calibrate"
        self._attr_translation_key = "recalibrate_color"

    async def async_press(self) -> None:
        """Reset the color position to zero without emitting an RF code."""
        runtime = self._entry_runtime()
        runtime["kelvin_position"] = 0
        async_dispatcher_send(self.hass, self._kelvin_signal())
