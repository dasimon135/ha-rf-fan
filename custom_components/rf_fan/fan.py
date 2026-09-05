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

from .actions import caps_from_data
from .const import (
    ACTION_FAN_NATURAL,
    ACTION_FAN_NATURAL_REVERSE,
    ACTION_FAN_OFF,
    ACTION_FAN_OFF_REVERSE,
    ACTION_FAN_ON,
    ACTION_FAN_REVERSE,
    CONF_SPEED_COUNT,
    DIRECTION_CONTROL_NONE,
    DIRECTION_CONTROL_PER_SPEED,
    EVENT_RF_FAN_RECEIVED,
    NATURAL_CONTROL_DEDICATED,
    NATURAL_CONTROL_NONE,
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
        caps = caps_from_data(dict(config_entry.data))
        self._direction_control: str = caps["direction_control"]
        self._has_direction: bool = self._direction_control != DIRECTION_CONTROL_NONE
        self._per_speed_direction: bool = (
            self._direction_control == DIRECTION_CONTROL_PER_SPEED
        )
        self._natural_control: str = caps["natural_control"]
        self._has_preset: bool = self._natural_control != NATURAL_CONTROL_NONE
        self._dedicated_preset: bool = (
            self._natural_control == NATURAL_CONTROL_DEDICATED
        )

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
        # A `dedicated` airflow key is deaf while the fan is stopped, so a preset
        # asked for then is remembered and pressed once the fan is running.
        self._pending_preset: str | None = None

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
        """Restore the assumed state, then subscribe to RF events."""
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
        if self._runtime.timer_ends_at is not None:
            self._runtime.timer_ends_at = None
            async_dispatcher_send(self.hass, self._timer_signal())

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan, optionally at a given speed and/or preset."""
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            sent = await self._async_transmit_action(ACTION_FAN_ON)
            if not sent:
                sent = await self._async_transmit_action(self._speed_action_for(1))

            if sent:
                self._is_on = True
                if self._percentage is None or self._percentage <= 0:
                    self._percentage = round(100 / self._speed_count)
                self.async_write_ha_state()

        # Applied last: the airflow preset is a separate button on the remote, and
        # the fan has to be running for it to take effect.
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif self._pending_preset is not None:
            # Asked for while the fan was stopped, where the key does nothing. The
            # fan is running now, so this is the first moment it can be heard.
            await self.async_set_preset_mode(self._pending_preset)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan, in the direction it is actually running.

        A `per_speed` remote encodes the direction in every frame it sends, its off
        key included. Stopping a reversed fan with the forward off code does stop
        it, but leaves the receiver storing "forward" while Home Assistant still
        shows reverse -- so the next speed code starts it the wrong way round (#59,
        measured by @Ltek).

        `fan_off_reverse` is optional, and the fallback is the whole point: an entry
        configured before this existed has no such code, gets `fan_off` exactly as
        before, and never sees a failed transmission.
        """
        sent = False
        if self._per_speed_direction and self._direction == DIRECTION_REVERSE:
            sent = await self._async_transmit_action(ACTION_FAN_OFF_REVERSE)
        if not sent:
            sent = await self._async_transmit_action(ACTION_FAN_OFF)
        if sent:
            self._is_on = False
            self._percentage = 0
            self._clear_timer()
            self.async_write_ha_state()

    def _speed_index(self, percentage: int) -> int:
        """Map a percentage onto a 1-based speed index."""
        step = 100 / self._speed_count
        return max(1, min(self._speed_count, round(percentage / step)))

    def _speed_action_for(self, index: int) -> str:
        """Speed action key for an index, in the current direction.

        With `direction_control: per_speed` the direction is not an action but a
        dimension of the speed code set, so it is resolved here. An unknown
        direction sends the forward set, which is also what makes the direction
        known from then on.
        """
        reverse = self._per_speed_direction and self._direction == DIRECTION_REVERSE
        return speed_action(index, reverse=reverse)

    def _natural_action_for(self) -> str:
        """Natural-airflow action key, in the current direction.

        The mirror of `_speed_action_for`, one level down: a `per_speed` remote
        gives this key a code per direction as well, so sending the summer code
        while the fan is running in winter reaches the wrong receiver state — or
        nothing at all. An unknown direction sends the forward code, exactly as
        the speeds do.

        The reverse speeds need no such check because `per_speed` has always
        required them. This key is new, so an entry created before it existed is
        legitimately `per_speed` with a preset and no winter code; falling back
        leaves it behaving exactly as it did, rather than going silently dead
        until it is reconfigured.
        """
        reverse = self._per_speed_direction and self._direction == DIRECTION_REVERSE
        if reverse and self._codes.get(ACTION_FAN_NATURAL_REVERSE):
            return ACTION_FAN_NATURAL_REVERSE
        return ACTION_FAN_NATURAL

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed via a fan_speed_X action."""
        if percentage <= 0:
            await self.async_turn_off()
            return

        speed_index = self._speed_index(percentage)
        sent = await self._async_transmit_action(self._speed_action_for(speed_index))
        if sent:
            self._is_on = True
            self._percentage = round(speed_index * (100 / self._speed_count))
            # A speed key is how a `dedicated` remote leaves the preset -- measured,
            # and the reason this shape exists (#34).
            self._leave_dedicated_preset()
            if self._per_speed_direction and self._direction is None:
                # The forward set is what just went on the air, so the direction is
                # no longer a guess.
                self._direction = DIRECTION_FORWARD
            self.async_write_ha_state()

    async def async_set_direction(self, direction: str) -> None:
        """Set the rotation direction.

        Two remote shapes, and they differ in how much they can promise:

        - `toggle`: one key that flips the direction. From an unknown direction a
          single toggle cannot guarantee the absolute target — inherent to assumed
          state, and the reason the mode below exists.
        - `per_speed`: no direction key at all. The remote stores the mode and emits
          a different speed code per direction, so setting the direction means
          re-sending the current speed from the other code set. The result is
          absolute: the direction is known, not dead-reckoned.
        """
        if self._direction == direction:
            return

        if self._per_speed_direction:
            previous = self._direction
            self._direction = direction
            if self._is_on and self._percentage:
                index = self._speed_index(self._percentage)
                if not await self._async_transmit_action(self._speed_action_for(index)):
                    # Nothing went on the air: the fan has not changed direction,
                    # so neither may the assumed state.
                    self._direction = previous
                    return
            # Fan off: nothing to re-send, and the direction applies to the next
            # speed code sent. Recording it now is what makes that code the right one.
            self.async_write_ha_state()
            return

        sent = await self._async_transmit_action(ACTION_FAN_REVERSE)
        if sent:
            self._direction = direction
            self.async_write_ha_state()

    def _leave_dedicated_preset(self) -> None:
        """Record that a speed took the fan out of the airflow preset.

        Only for a `dedicated` remote: there a speed key genuinely ends the preset.
        A `toggle` remote has never been measured doing that, and inventing it
        would desynchronise the one shape that works today.
        """
        if self._dedicated_preset and self._preset == PRESET_NATURAL:
            self._preset = PRESET_NORMAL

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Enter or leave the natural airflow preset.

        The two shapes leave it by pressing different keys, because they are
        different keys:

        - `toggle`: one key that flips. Entering and leaving are the same press,
          which is why nothing else here has to know the current preset.
        - `dedicated`: the key SETS the preset, so pressing it again changes
          nothing. What leaves the preset is a speed key -- the current speed,
          re-sent, so the fan carries on at the speed Home Assistant already shows
          (#34, measured by @elmr91). Entering while the fan is stopped is deferred
          rather than transmitted: the key is deaf then, and a press that cannot
          land must not be recorded as one.
        """
        # `_pending_preset` is what keeps this from swallowing the deferred press:
        # the preset was recorded when the fan was stopped, so the assumed state
        # already says natural while the key has never been pressed.
        if self._preset == preset_mode and self._pending_preset is None:
            return

        if not self._dedicated_preset:
            sent = await self._async_transmit_action(self._natural_action_for())
            if sent:
                self._preset = preset_mode
                self.async_write_ha_state()
            return

        if preset_mode == PRESET_NATURAL:
            if not (self._is_on and self._percentage):
                # Deferred, and shown: the fan is stopped, so the next start is what
                # carries it. Mirrors how `per_speed` records a direction with the
                # fan off, for the same reason -- the code that acts on it comes later.
                self._preset = preset_mode
                self._pending_preset = preset_mode
                self.async_write_ha_state()
                return
            if await self._async_transmit_action(self._natural_action_for()):
                self._preset = preset_mode
                self._pending_preset = None
                self.async_write_ha_state()
            return

        # Leaving: send the speed the fan is already assumed to be running at. With
        # the fan stopped there is no speed to send, and nothing to leave.
        self._pending_preset = None
        if not (self._is_on and self._percentage):
            self._preset = preset_mode
            self.async_write_ha_state()
            return
        index = self._speed_index(self._percentage)
        if await self._async_transmit_action(self._speed_action_for(index)):
            self._preset = preset_mode
            self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Update the local state when the physical remote is used."""
        # Short-circuit order matters: an echo of our own transmission is not a
        # remote press at all, so it must never be recorded as the start of a burst.
        if self._is_echo(event.data) or self._is_repeat(event):
            return

        action = self._event_action(event.data)
        if action is None:
            return

        if action in (ACTION_FAN_OFF, ACTION_FAN_OFF_REVERSE):
            self._is_on = False
            self._percentage = 0
            # Both off keys name their direction, so hearing one is an ABSOLUTE
            # reading of a state that is otherwise dead-reckoned. Only trust it when
            # the remote actually has the pair: with `fan_off` alone that key is
            # direction-agnostic, and inferring "forward" from it would invent a
            # fact the frame does not carry.
            if self._per_speed_direction and ACTION_FAN_OFF_REVERSE in self._codes:
                self._direction = (
                    DIRECTION_REVERSE
                    if action == ACTION_FAN_OFF_REVERSE
                    else DIRECTION_FORWARD
                )
            self._clear_timer()
            self.async_write_ha_state()
            return

        if action == ACTION_FAN_ON:
            self._is_on = True
            if self._percentage is None or self._percentage <= 0:
                self._percentage = round(100 / self._speed_count)
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

        if action in (ACTION_FAN_NATURAL, ACTION_FAN_NATURAL_REVERSE):
            # A `dedicated` key SETS the preset: following it as a flip drifts by
            # one press every time the fan is already in the preset, which on this
            # shape of remote is exactly when it gets pressed again.
            self._preset = (
                PRESET_NATURAL
                if self._dedicated_preset
                else (PRESET_NORMAL if self._preset == PRESET_NATURAL else PRESET_NATURAL)
            )
            self._pending_preset = None
            # Like a reverse speed code, the winter natural code says which
            # direction the remote is in as well as which preset was pressed. The
            # guard matters: on a `toggle` remote the direction is dead-reckoned
            # from its own key, and a preset press must not overwrite it.
            if self._per_speed_direction:
                self._direction = (
                    DIRECTION_REVERSE
                    if action == ACTION_FAN_NATURAL_REVERSE
                    else DIRECTION_FORWARD
                )
            self.async_write_ha_state()
            return

        # A reverse speed code identifies the speed AND the direction at once, which
        # is why `per_speed` tracks the physical remote better than a toggle can: a
        # toggle press tells you the direction changed, this tells you what it is.
        if self._per_speed_direction:
            for index in range(1, self._speed_count + 1):
                if action == speed_action(index, reverse=True):
                    self._is_on = True
                    self._percentage = round(index * (100 / self._speed_count))
                    self._direction = DIRECTION_REVERSE
                    self._leave_dedicated_preset()
                    self.async_write_ha_state()
                    return

        for idx in range(1, self._speed_count + 1):
            if action == speed_action(idx):
                self._is_on = True
                self._percentage = round(idx * (100 / self._speed_count))
                if self._per_speed_direction:
                    self._direction = DIRECTION_FORWARD
                self._leave_dedicated_preset()
                self.async_write_ha_state()
                return
