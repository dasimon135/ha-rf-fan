"""Config flow for the RF Fan integration."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .actions import (
    caps_from_data,
    classify_reconfigure_actions,
    pick_best_code,
    split_actions,
    validate_codes,
)
from .const import (
    CONF_CODES,
    CONF_ESPHOME_DEVICE,
    CONF_FAN_NAME,
    CONF_HAS_COLOR_TEMP,
    CONF_HAS_DIRECTION,
    CONF_HAS_FAN_ON,
    CONF_HAS_LIGHT,
    CONF_HAS_NATURAL_PRESET,
    CONF_HAS_SOUND,
    CONF_HAS_TIMERS,
    CONF_LIGHT_CONTROL,
    CONF_REPEAT_COUNT,
    CONF_SPEED_COUNT,
    DEFAULT_REPEAT_COUNT,
    DEFAULT_SPEED_COUNT,
    DOMAIN,
    EVENT_RF_FAN_RECEIVED,
    LIGHT_CONTROL_NONE,
    LIGHT_CONTROL_OPTIONS,
    LIGHT_CONTROL_TOGGLE,
)

LEARN_TIMEOUT_SEC = 30
# After the first frame, keep listening briefly so a held button's repeats can be
# collected and the noise-resistant modal frame chosen.
LEARN_COLLECT_SEC = 1.2


class RfFanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow to add a generic RF fan."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RfFanOptionsFlow:
        """Return the options flow."""
        return RfFanOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the flow."""
        self._esphome_device: str = ""
        self._fan_name: str = ""
        self._speed_count: int = DEFAULT_SPEED_COUNT
        self._light_control: str = LIGHT_CONTROL_TOGGLE
        self._has_fan_on: bool = False
        self._has_light: bool = True
        self._caps: dict[str, bool] = {}
        self._learn_codes: dict[str, str] = {}
        self._learn_action_index: int = 0
        self._learn_task: asyncio.Task[str | None] | None = None
        self._learn_timeout: bool = False
        self._reconfigure: bool = False
        self._existing_codes: dict[str, str] = {}
        self._pending_actions: list[str] | None = None
        self._repeat_count: int = DEFAULT_REPEAT_COUNT

    def _available_esphome_devices(self) -> list[str]:
        """List ESPHome devices exposing a transmit_rf_fan service."""
        esphome_services = self.hass.services.async_services().get("esphome", {})
        devices = []
        suffix = "_transmit_rf_fan"
        for service_name in esphome_services:
            if service_name.endswith(suffix):
                devices.append(service_name[: -len(suffix)].replace("_", "-"))
        return sorted(devices)

    def _base_schema(self, *, include_device: bool) -> vol.Schema:
        """Build the step 1 schema, reusable for reconfiguration."""
        fields: dict[Any, Any] = {}
        if include_device:
            available = self._available_esphome_devices()
            default_device = available[0] if len(available) == 1 else ""
            if available:
                fields[vol.Required(
                    CONF_ESPHOME_DEVICE, default=default_device or available[0]
                )] = SelectSelector(SelectSelectorConfig(options=available))
            else:
                fields[vol.Optional(CONF_ESPHOME_DEVICE, default=default_device)] = str
        fields[vol.Required(CONF_FAN_NAME, default=self._fan_name)] = str
        fields[vol.Required(CONF_SPEED_COUNT, default=self._speed_count)] = vol.In([3, 4, 5, 6])
        fields[vol.Required(CONF_LIGHT_CONTROL, default=self._light_control)] = SelectSelector(
            SelectSelectorConfig(options=LIGHT_CONTROL_OPTIONS, translation_key="light_control")
        )
        fields[vol.Required(CONF_HAS_FAN_ON, default=self._has_fan_on)] = bool
        fields[vol.Required(CONF_HAS_DIRECTION, default=self._caps.get(CONF_HAS_DIRECTION, False))] = bool
        fields[vol.Required(CONF_HAS_NATURAL_PRESET, default=self._caps.get(CONF_HAS_NATURAL_PRESET, False))] = bool
        fields[vol.Required(CONF_HAS_COLOR_TEMP, default=self._caps.get(CONF_HAS_COLOR_TEMP, False))] = bool
        fields[vol.Required(CONF_HAS_TIMERS, default=self._caps.get(CONF_HAS_TIMERS, False))] = bool
        fields[vol.Required(CONF_HAS_SOUND, default=self._caps.get(CONF_HAS_SOUND, False))] = bool
        return vol.Schema(fields)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: general fan information."""
        errors: dict[str, str] = {}
        available_devices = self._available_esphome_devices()

        if user_input is not None:
            selected_device = user_input.get(CONF_ESPHOME_DEVICE, "").strip()
            if not selected_device and len(available_devices) == 1:
                selected_device = available_devices[0]

            if not selected_device:
                if len(available_devices) > 1:
                    errors[CONF_ESPHOME_DEVICE] = "required_esphome_device"
                else:
                    errors[CONF_ESPHOME_DEVICE] = "unknown_esphome_device"
            elif available_devices and selected_device not in available_devices:
                errors[CONF_ESPHOME_DEVICE] = "unknown_esphome_device"
            else:
                self._esphome_device = selected_device
                self._fan_name = user_input[CONF_FAN_NAME].strip()
                self._speed_count = int(user_input[CONF_SPEED_COUNT])
                self._light_control = user_input[CONF_LIGHT_CONTROL]
                self._has_fan_on = bool(user_input[CONF_HAS_FAN_ON])
                self._has_light = self._light_control != LIGHT_CONTROL_NONE
                self._caps = caps_from_data(user_input)
                return await self.async_step_method()

        return self.async_show_form(
            step_id="user",
            data_schema=self._base_schema(include_device=True),
            description_placeholders={
                "detected": ", ".join(available_devices) if available_devices else "none",
            },
            errors=errors,
        )

    async def async_step_method(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose between manual entry and learning."""
        if user_input is not None:
            if user_input["method"] == "learn":
                if not self._reconfigure:
                    self._learn_codes = {}
                self._learn_task = None
                self._learn_timeout = False
                self._learn_action_index = 0
                return await self.async_step_learn()
            return await self.async_step_codes()

        return self.async_show_form(
            step_id="method",
            data_schema=vol.Schema(
                {
                    vol.Required("method", default="manual"): vol.In(
                        {
                            "manual": "manual",
                            "learn": "learn",
                        }
                    )
                }
            ),
        )

    async def async_step_codes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual step: mapping of action -> RF code."""
        errors: dict[str, str] = {}
        actions = self._actions_to_process()

        if user_input is not None:
            codes = dict(self._learn_codes) if self._reconfigure else {}
            codes.update(
                {
                    action: str(user_input.get(action, "")).strip()
                    for action in actions
                    if str(user_input.get(action, "")).strip()
                }
            )
            errors = validate_codes(codes, actions)
            if not errors:
                return self._finish(codes)

        schema_fields: dict[Any, Any] = {}
        for action in actions:
            schema_fields[vol.Required(action)] = str

        return self.async_show_form(
            step_id="codes",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    def _actions_to_process(self) -> list[str]:
        """List the actions to process, in order."""
        if self._pending_actions is not None:
            return self._pending_actions
        required_actions, optional_actions = split_actions(
            self._speed_count, self._light_control, has_fan_on=self._has_fan_on, **self._caps
        )
        return required_actions + optional_actions

    async def async_step_learn(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Progress screen: listen for the current action.

        This step returns ONLY ``SHOW_PROGRESS`` or ``SHOW_PROGRESS_DONE``:
        from a progress screen, HA does not allow any other transition. Storing
        the code and moving on to the next action happen in
        ``async_step_learn_resolve``, which carries a different ``step_id``. This
        change of ``step_id`` is essential: it is what triggers the
        ``data_entry_flow_progressed`` event that refreshes the frontend
        (see ``FlowManager._async_configure``). Looping on the same ``step_id``
        (``show_progress`` → ``show_progress_done(next_step_id="learn")``) does
        not change the ``step_id`` → no refresh → the spinner stays frozen
        even though the backend has already moved on.
        """
        actions = self._actions_to_process()

        # Listening is done: move on to resolution (changes step_id).
        if self._learn_task is not None and self._learn_task.done():
            return self.async_show_progress_done(next_step_id="learn_resolve")

        # Start listening if needed, then show progress.
        if self._learn_task is None:
            self._learn_task = self.hass.async_create_task(
                self._async_wait_for_rf_signal()
            )
        return self.async_show_progress(
            step_id="learn",
            progress_action="listen_rf_signal",
            progress_task=self._learn_task,
            description_placeholders={
                "action": actions[self._learn_action_index],
                "timeout": str(LEARN_TIMEOUT_SEC),
            },
        )

    async def async_step_learn_resolve(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Resolve a finished listen (or the recovery form), then continue.

        ``step_id`` distinct from ``learn``: the ``learn`` →
        ``learn_resolve`` transition changes the ``step_id``, which triggers the
        frontend refresh. This is also where we handle the cases that cannot
        be returned directly from the progress screen (recovery form
        after a timeout, creation of the entry).
        """
        actions = self._actions_to_process()

        if user_input is not None:
            # Recovery form submission: skip or paste a code.
            self._learn_timeout = False
            if bool(user_input.get("skip")):
                self._learn_action_index += 1
            else:
                manual_code = str(user_input.get("code", "")).strip()
                if manual_code:
                    self._learn_codes[actions[self._learn_action_index]] = manual_code
                    self._learn_action_index += 1
        elif self._learn_task is not None:
            # A listen has just finished: store the code or flag the timeout.
            learned_code = self._learn_task.result()
            self._learn_task = None
            if learned_code is not None:
                self._learn_codes[actions[self._learn_action_index]] = learned_code
                self._learn_action_index += 1
            else:
                self._learn_timeout = True

        # All actions processed: create the entry.
        if self._learn_action_index >= len(actions):
            return self._finish(self._learn_codes)

        # Timeout on the previous listen: offer manual entry / skip.
        if self._learn_timeout:
            return self.async_show_form(
                step_id="learn_resolve",
                data_schema=vol.Schema(
                    {
                        vol.Optional("code", default=""): str,
                        vol.Optional("skip", default=False): bool,
                    }
                ),
                description_placeholders={
                    "action": actions[self._learn_action_index],
                    "timeout": str(LEARN_TIMEOUT_SEC),
                },
                errors={"base": "learn_timeout"},
            )

        # Otherwise: listen for the next action.
        return await self.async_step_learn()

    async def _async_wait_for_rf_signal(self) -> str | None:
        """Wait for RF events from the gateway and return the most repeated code.

        After the first frame, keep collecting briefly: a real (held) button press
        repeats the same frame, so the modal frame wins over random 433 MHz noise.
        """
        frames: list[str] = []
        first_frame = asyncio.Event()

        @callback
        def _handle_event(event: Any) -> None:
            data = event.data
            device = data.get("device")
            if isinstance(device, str) and device != self._esphome_device:
                return

            code = data.get("code")
            if not isinstance(code, str) or not code.strip():
                return

            frames.append(code.strip())
            first_frame.set()

        unsubscribe = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, _handle_event)

        try:
            try:
                await asyncio.wait_for(first_frame.wait(), timeout=LEARN_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                return None
            # Gather a few more frames to catch repeats before choosing.
            await asyncio.sleep(LEARN_COLLECT_SEC)
        finally:
            unsubscribe()

        return pick_best_code(frames)

    def _finish(self, codes: dict[str, str]) -> ConfigFlowResult:
        """Create or update the final config entry."""
        data = {
            CONF_ESPHOME_DEVICE: self._esphome_device,
            CONF_FAN_NAME: self._fan_name,
            CONF_SPEED_COUNT: self._speed_count,
            CONF_LIGHT_CONTROL: self._light_control,
            CONF_HAS_FAN_ON: self._has_fan_on,
            CONF_HAS_LIGHT: self._has_light,
            **self._caps,
            CONF_REPEAT_COUNT: self._repeat_count,
            CONF_CODES: codes,
        }
        if self._reconfigure:
            entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(entry, data=data)
        return self.async_create_entry(title=self._fan_name, data=data)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure an existing entry: re-declare + learn the delta."""
        entry = self._get_reconfigure_entry()
        data = entry.data

        if user_input is None:
            self._reconfigure = True
            self._esphome_device = data[CONF_ESPHOME_DEVICE]
            self._fan_name = data.get(CONF_FAN_NAME, entry.title)
            self._speed_count = int(data.get(CONF_SPEED_COUNT, DEFAULT_SPEED_COUNT))
            self._light_control = data.get(CONF_LIGHT_CONTROL, LIGHT_CONTROL_TOGGLE)
            self._has_fan_on = bool(data.get(CONF_HAS_FAN_ON, False))
            self._caps = caps_from_data(data)
            self._existing_codes = dict(data.get(CONF_CODES, {}))
            self._repeat_count = int(
                entry.options.get(
                    CONF_REPEAT_COUNT, data.get(CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT)
                )
            )
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self._base_schema(include_device=False),
            )

        self._fan_name = user_input[CONF_FAN_NAME].strip()
        self._speed_count = int(user_input[CONF_SPEED_COUNT])
        self._light_control = user_input[CONF_LIGHT_CONTROL]
        self._has_fan_on = bool(user_input[CONF_HAS_FAN_ON])
        self._has_light = self._light_control != LIGHT_CONTROL_NONE
        self._caps = caps_from_data(user_input)
        return await self.async_step_reconfigure_review()

    async def async_step_reconfigure_review(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Recap: to learn / kept (re-learn?) / forgotten, then capture."""
        required_actions, _ = split_actions(
            self._speed_count, self._light_control, has_fan_on=self._has_fan_on, **self._caps
        )
        to_learn, kept, forgotten = classify_reconfigure_actions(
            required_actions, self._existing_codes
        )

        if user_input is not None:
            relearn = [a for a in kept if bool(user_input.get(f"relearn_{a}"))]
            self._learn_codes = {a: self._existing_codes[a] for a in kept}
            self._pending_actions = [
                a for a in required_actions if a in to_learn or a in relearn
            ]
            if not self._pending_actions:
                return self._finish(dict(self._learn_codes))
            self._learn_action_index = 0
            return await self.async_step_method()

        schema_fields: dict[Any, Any] = {
            vol.Optional(f"relearn_{a}", default=False): bool for a in kept
        }
        return self.async_show_form(
            step_id="reconfigure_review",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={
                "to_learn": ", ".join(to_learn) or "—",
                "kept": ", ".join(kept) or "—",
                "forgotten": ", ".join(forgotten) or "—",
            },
        )


class RfFanOptionsFlow(OptionsFlow):
    """Options flow for RF fan."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the RF transmission options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REPEAT_COUNT,
                        default=self._config_entry.options.get(
                            CONF_REPEAT_COUNT,
                            self._config_entry.data.get(CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=8))
                }
            ),
        )
