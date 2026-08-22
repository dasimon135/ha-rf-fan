"""Base entity for RF Fan."""

from __future__ import annotations

import logging
from asyncio import sleep
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import Entity

from .actions import transmit_repeat_count
from .const import (
    COLOR_TEMP_OPTIONS,
    CONF_CODES,
    CONF_ESPHOME_DEVICE,
    CONF_FAN_NAME,
    CONF_GATEWAY_SERVICE,
    CONF_REPEAT_COUNT,
    DOMAIN,
    ECHO_SUPPRESS_SEC,
)
from .data import RfFanConfigEntry, RfFanRuntimeData

_LOGGER = logging.getLogger(__name__)


class RfFanBaseEntity(Entity):
    """Base entity for the RF fan."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True

    def __init__(self, hass: HomeAssistant, config_entry: RfFanConfigEntry) -> None:
        """Initialize the base entity."""
        self.hass = hass
        self._config_entry = config_entry
        self._esphome_device: str = config_entry.data[CONF_ESPHOME_DEVICE]
        # Raw service prefix stored at flow time (v2 entries); tolerant fallback
        # derivation for entries that have not been migrated yet.
        self._gateway_service: str = config_entry.data.get(
            CONF_GATEWAY_SERVICE, self._esphome_device.replace("-", "_")
        )
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
        """Transmit an RF action via ESPHome if it is mapped.

        Returns False only when the action has no mapped code (callers rely on
        this to fall back to an alternative action). Hard failures — the gateway
        service is not registered, or the service call itself fails — raise
        HomeAssistantError so the user gets feedback in the UI instead of a
        silently ignored command.
        """
        code = self._codes.get(action)
        if not code:
            _LOGGER.debug("Ignoring unmapped action: %s", action)
            return False

        service_name = f"{self._gateway_service}_transmit_rf_fan"
        if not self.hass.services.has_service("esphome", service_name):
            _LOGGER.warning(
                "ESPHome gateway service esphome.%s is not available; cannot send %s",
                service_name,
                action,
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._gateway_issue_id(),
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="gateway_service_missing",
                translation_placeholders={
                    "fan_name": self._fan_name,
                    "device": self._esphome_device,
                    "service": f"esphome.{service_name}",
                },
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="gateway_service_missing",
                translation_placeholders={
                    "device": self._esphome_device,
                    "service": f"esphome.{service_name}",
                },
            )

        # The service is back: clear the repair issue if one was raised.
        ir.async_delete_issue(self.hass, DOMAIN, self._gateway_issue_id())

        # Toggle actions keep repeat_count but rounded down to an odd value, so the
        # fan ends up flipped exactly once whether or not it debounces the burst;
        # absolute actions use the configured count as-is (see const.TOGGLE_ACTIONS).
        repeat_count = transmit_repeat_count(action, self._repeat_count())
        # Arm the anti-echo window BEFORE the call: the gateway can sniff and report
        # our own frame while we are still awaiting the service call.
        self._note_transmission(code)
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
        except Exception as err:
            _LOGGER.warning("RF send error (%s): %s", action, err)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="transmit_failed",
                translation_placeholders={
                    "action": action,
                    "device": self._esphome_device,
                    "error": str(err),
                },
            ) from err

        # Re-arm from the moment the call actually returned.
        self._note_transmission(code)
        return True

    def _gateway_issue_id(self) -> str:
        """Repair-issue id for a missing gateway service, specific to the entry."""
        return f"gateway_service_missing_{self._config_entry.entry_id}"

    def _note_transmission(self, code: str) -> None:
        """Open the anti-echo window for a code we just put on the air."""
        now = self.hass.loop.time()
        echoes = self._runtime.echo_codes
        # Drop stale entries so the map cannot grow unbounded over time.
        for stale in [known for known, until in echoes.items() if until <= now]:
            del echoes[stale]
        echoes[code] = now + ECHO_SUPPRESS_SEC

    def _is_echo(self, event_data: dict[str, Any]) -> bool:
        """True if the received frame is our own transmission coming back.

        Matching is per code, so a genuine press of a different remote button just
        after a Home Assistant command is not discarded. The window is not consumed
        on the first match: `repeat_count` > 1 produces several echoes, and every
        platform of the entry listens to the same bus event.
        """
        now = self.hass.loop.time()
        code = event_data.get("code")
        if isinstance(code, str) and code:
            return self._runtime.echo_codes.get(code, 0.0) > now
        # No code reported by the gateway: nothing to match on, so fall back to a
        # blanket window over all reception.
        return any(until > now for until in self._runtime.echo_codes.values())

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

    @property
    def _runtime(self) -> RfFanRuntimeData:
        """Typed runtime data for the entry (set in __init__.py async_setup_entry)."""
        return self._config_entry.runtime_data

    def _kelvin_signal(self) -> str:
        """Dispatcher signal name for the color position, specific to the entry."""
        return f"{DOMAIN}_{self._config_entry.entry_id}_kelvin"

    def _timer_signal(self) -> str:
        """Dispatcher signal name for the sleep timer, specific to the entry."""
        return f"{DOMAIN}_{self._config_entry.entry_id}_timer"

    def _advance_kelvin_position(self) -> int:
        """Advance the color position by one step (mod N) and return it."""
        runtime = self._runtime
        runtime.kelvin_position = (runtime.kelvin_position + 1) % len(COLOR_TEMP_OPTIONS)
        return runtime.kelvin_position

    def _is_own_event(self, event_data: dict[str, Any]) -> bool:
        """Check that the RF event comes from the configured gateway."""
        device = event_data.get("device")
        if not isinstance(device, str) or not device:
            return True
        # Normalize the ESPHome dash/underscore ambiguity on both sides.
        return device.replace("-", "_") == self._gateway_service

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

        # Nothing matched. Record it so the diagnostics can show it, and log it
        # once: every platform of the entry listens to the same bus event, so
        # guarding on the stored value keeps this to one line per new code.
        runtime = self._runtime
        if runtime.last_unmatched_code != code:
            runtime.last_unmatched_code = code
            _LOGGER.debug(
                "Received RF code %s matches no learned action for %s. Learned "
                "codes: %s. A code learned through a different gateway "
                "configuration will not match — relearn it",
                code,
                self._fan_name,
                sorted(self._codes.values()),
            )
        return None
