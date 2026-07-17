"""Base entity for RF Fan."""

from __future__ import annotations

import logging
from asyncio import sleep
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .const import (
    COLOR_TEMP_OPTIONS,
    CONF_CODES,
    CONF_ESPHOME_DEVICE,
    CONF_FAN_NAME,
    CONF_REPEAT_COUNT,
    DOMAIN,
    ECHO_SUPPRESS_SEC,
    SINGLE_SHOT_ACTIONS,
)

_LOGGER = logging.getLogger(__name__)


class RfFanBaseEntity(Entity):
    """Base entity for the RF fan."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the base entity."""
        self.hass = hass
        self._config_entry = config_entry
        self._esphome_device: str = config_entry.data[CONF_ESPHOME_DEVICE]
        self._fan_name: str = config_entry.data[CONF_FAN_NAME]
        self._codes: dict[str, str] = config_entry.data[CONF_CODES]

        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": self._fan_name,
            "manufacturer": "Generic RF",
            "model": "RF Fan",
        }

    def _repeat_count(self) -> int:
        """Return the RF repeat count."""
        return int(
            self._config_entry.options.get(
                CONF_REPEAT_COUNT,
                self._config_entry.data.get(CONF_REPEAT_COUNT, 2),
            )
        )

    async def _async_transmit_action(self, action: str) -> bool:
        """Transmit an RF action via ESPHome if it is mapped."""
        code = self._codes.get(action)
        if not code:
            _LOGGER.debug("Ignoring unmapped action: %s", action)
            return False

        service_name = f"{self._esphome_device.replace('-', '_')}_transmit_rf_fan"
        # Relative/toggle actions must fire exactly once (the captured code already
        # holds the remote's repeat burst); only absolute actions use repeat_count.
        repeat_count = 1 if action in SINGLE_SHOT_ACTIONS else self._repeat_count()
        try:
            await self.hass.services.async_call(
                "esphome",
                service_name,
                {
                    "action": action,
                    "code": code,
                    "repeat_count": repeat_count,
                },
                blocking=True,
            )
        except Exception as err:  # pragma: no cover
            _LOGGER.warning("RF send error (%s): %s", action, err)
            return False

        self._entry_runtime()["last_tx"] = self.hass.loop.time()
        return True

    def _recently_transmitted(self) -> bool:
        """True if a transmission occurred very recently (anti-echo window)."""
        last_tx = self._entry_runtime().get("last_tx", 0.0)
        return (self.hass.loop.time() - last_tx) < ECHO_SUPPRESS_SEC

    async def _async_transmit_times(self, action: str, times: int, gap: float = 0.0) -> bool:
        """Transmit an action's code `times` times (cycle).

        `gap` seconds are awaited between successive presses so a debouncing receiver
        registers each as a distinct press; without a gap a rapid burst merges into a
        single step. Returns True if at least one transmission succeeded.
        """
        sent_any = False
        count = max(0, times)
        for index in range(count):
            if await self._async_transmit_action(action):
                sent_any = True
            if gap and index < count - 1:
                await sleep(gap)
        return sent_any

    def _entry_runtime(self) -> dict[str, Any]:
        """Shared state dict for the entry (created in __init__.py async_setup_entry)."""
        return self.hass.data[DOMAIN][self._config_entry.entry_id]

    def _kelvin_signal(self) -> str:
        """Dispatcher signal name for the color position, specific to the entry."""
        return f"{DOMAIN}_{self._config_entry.entry_id}_kelvin"

    def _timer_signal(self) -> str:
        """Dispatcher signal name for the sleep timer, specific to the entry."""
        return f"{DOMAIN}_{self._config_entry.entry_id}_timer"

    def _advance_kelvin_position(self) -> int:
        """Advance the color position by one step (mod N) and return it."""
        runtime = self._entry_runtime()
        runtime["kelvin_position"] = (runtime.get("kelvin_position", 0) + 1) % len(COLOR_TEMP_OPTIONS)
        return runtime["kelvin_position"]

    def _is_own_event(self, event_data: dict[str, Any]) -> bool:
        """Check that the RF event comes from the configured gateway."""
        device = event_data.get("device")
        if not isinstance(device, str) or not device:
            return True
        return device == self._esphome_device

    def _event_action(self, event_data: dict[str, Any]) -> str | None:
        """Extract the received RF action from the ESPHome event."""
        if not self._is_own_event(event_data):
            return None

        action = event_data.get("action")
        if isinstance(action, str) and action and action != "sniff":
            return action

        code = event_data.get("code")
        if not isinstance(code, str) or not code:
            return None

        for mapped_action, mapped_code in self._codes.items():
            if mapped_code == code:
                return mapped_action
        return None
