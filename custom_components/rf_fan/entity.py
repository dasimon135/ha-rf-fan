"""Base entity for RF Fan."""

from __future__ import annotations

import logging
from asyncio import CancelledError, sleep
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import Entity

from .actions import (
    caps_from_data,
    color_temp_options,
    color_temp_steps,
    light_level_steps,
    transmit_repeat_count,
    walk_steps,
)
from .const import (
    COLOR_CONTROL_RELATIVE,
    CONF_CODES,
    CONF_ESPHOME_DEVICE,
    CONF_FAN_NAME,
    CONF_GATEWAY_SERVICE,
    CONF_REPEAT_COUNT,
    DOMAIN,
    ECHO_SUPPRESS_SEC,
    RECEIVE_DEBOUNCE_SEC,
    STEP_GAP_SEC,
    STEP_UP,
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
        # How many positions the stepped controls model on THIS fan. Declared in the
        # config flow because no part of it can be discovered: the hardware never
        # reports a level, so the count is a fact about the remote, not about us.
        self._color_temp_steps: int = color_temp_steps(dict(config_entry.data))
        self._light_level_steps: int = light_level_steps(dict(config_entry.data))
        self._color_temp_options: list[str] = color_temp_options(self._color_temp_steps)
        # Whether the colour ends join up is a property of the REMOTE, not of the
        # value, so every entity that moves the position needs to know the shape.
        self._color_control: str = caps_from_data(dict(config_entry.data))[
            "color_control"
        ]

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

    def _is_repeat(self, event: Any) -> bool:
        """True if this frame is another copy of the press that produced the last one.

        A remote does not send one frame per press: it sends the same frame four to
        six times so that at least one arrives, and the gateway reports every one of
        them. Counting them all turns one press of a toggle key into a flicker and
        one press of a step key into six steps — issue #24, where the colour select
        walked Warm → Cold → Neutral → Warm → Cold → Neutral from a single press.

        The window slides: every frame of a burst pushes it forward, so a burst of
        any length collapses to its first frame while a deliberate second press,
        which takes a human far longer than RECEIVE_DEBOUNCE_SEC, lands outside it.

        Called after `_is_echo`, and only for frames that survive it: a repeat of our
        own transmission is already discarded, and there is no burst to track in it.

        The verdict is computed once per frame and reused, because every platform of
        the entry listens to the same bus event. Recomputing it per listener would
        let the first entity slide the window and leave all the others concluding
        the frame was a repeat — the same "one event, many listeners" constraint that
        `_is_echo` handles by never consuming its window.
        """
        runtime = self._runtime
        judged = runtime.receive_verdict
        if judged is not None and judged[0] is event:
            return judged[1]

        code = event.data.get("code")
        if isinstance(code, str) and code:
            now = self.hass.loop.time()
            seen = runtime.receive_seen
            # Pruning with the same threshold the test uses means "still in the map"
            # and "seen within the window" are the same statement, and keeps the map
            # from growing over the life of the entry.
            for stale in [
                known for known, at in seen.items() if now - at > RECEIVE_DEBOUNCE_SEC
            ]:
                del seen[stale]
            repeat = code in seen
            seen[code] = now
        else:
            # No code reported by the gateway: there is nothing to key a burst on,
            # and swallowing a frame we cannot identify would lose real presses.
            repeat = False

        runtime.receive_verdict = (event, repeat)
        return repeat

    async def _async_walk(
        self,
        axis: str,
        *,
        up_action: str,
        down_action: str | None,
        target: int,
        size: int,
        wrap: bool,
        get_position: Callable[[], int | None],
        set_position: Callable[[int], None],
    ) -> int | None:
        """Step a dead-reckoned position to `target`, one key press at a time.

        The transport half of the walk; the arithmetic lives in
        `actions.walk_steps`. Steps are separated by STEP_GAP_SEC so a debouncing
        receiver counts them individually, and each keeps the full `repeat_count`:
        a step is absolute (one notch in a known direction), not a flip.

        `down_action` is None for a remote whose colour key only cycles forward. There
        is then only one direction available, so the walk always goes up and `wrap`
        must be True — the position comes back round.

        Restart semantics: a walk already running on the same `axis` is cancelled
        first, and this one starts from where that one actually stopped. `set_position`
        is called after every frame that goes on the air, never once at the end, so
        the position a cancellation leaves behind is the truth about the hardware
        rather than an intention. Returns the position actually reached.
        """
        running = self._runtime.walks.pop(axis, None)
        if running is not None and not running.done():
            running.cancel()
            with suppress(CancelledError):
                await running

        task = self.hass.async_create_task(
            self._async_walk_body(
                up_action=up_action,
                down_action=down_action,
                target=target,
                size=size,
                wrap=wrap,
                get_position=get_position,
                set_position=set_position,
            )
        )
        self._runtime.walks[axis] = task
        try:
            await task
        except CancelledError:
            # Superseded by a newer walk on the same axis: expected, not an error.
            # Our own cancellation still propagates — the entry it left in the map
            # is the newer walk's, so `is not task` distinguishes the two cases.
            if self._runtime.walks.get(axis) is task:
                raise
        finally:
            if self._runtime.walks.get(axis) is task:
                del self._runtime.walks[axis]
        return get_position()

    async def _async_walk_body(
        self,
        *,
        up_action: str,
        down_action: str | None,
        target: int,
        size: int,
        wrap: bool,
        get_position: Callable[[], int | None],
        set_position: Callable[[int], None],
    ) -> None:
        """Emit the individual steps of a walk (see `_async_walk`)."""
        position = get_position()
        if down_action is None:
            # Forward-only cycling key: the shortest path may point backwards, but
            # there is nothing to press to go that way.
            direction, steps = STEP_UP, (target - (position or 0)) % size
        else:
            direction, steps = walk_steps(position, target, size, wrap=wrap)

        action = up_action if direction == STEP_UP else down_action
        delta = 1 if direction == STEP_UP else -1
        for index in range(steps):
            if not await self._async_transmit_action(action):
                # Nothing went on the air (unmapped code): the hardware has not
                # moved, so the assumed position may not either.
                return
            current = get_position()
            moved = (0 if current is None else current) + delta
            set_position(moved % size if wrap else max(0, min(size - 1, moved)))
            if index < steps - 1:
                await sleep(STEP_GAP_SEC)

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

    def _level_signal(self) -> str:
        """Dispatcher signal name for the brightness position, specific to the entry."""
        return f"{DOMAIN}_{self._config_entry.entry_id}_level"

    def _advance_kelvin_position(self, delta: int = 1) -> int:
        """Move the color position by `delta` steps and return it.

        Whether the ends join up is a property of the remote, not of the value.

        - `cycle`: one key, and coming round is the only move it has. Wrapping is
          not a convenience here, it is what the hardware does.
        - `relative`: two keys that stop at the ends, exactly like the brightness
          pair. @elmr91 pressed "warmer" on the top position: the lamp did not
          move, and the assumed position rolled back to the first one (#18). A
          wrap there does not shorten a walk, it desynchronises one — the same
          class of damage as counting a repeated frame twice.
        """
        runtime = self._runtime
        moved = runtime.kelvin_position + delta
        if self._color_control == COLOR_CONTROL_RELATIVE:
            runtime.kelvin_position = max(0, min(self._color_temp_steps - 1, moved))
        else:
            runtime.kelvin_position = moved % self._color_temp_steps
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
