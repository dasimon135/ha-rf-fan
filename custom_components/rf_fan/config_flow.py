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
from homeassistant.util import slugify

from .actions import (
    caps_from_data,
    classify_reconfigure_actions,
    color_temp_steps,
    extra_button_count,
    extra_names,
    light_level_steps,
    pick_best_code,
    split_actions,
    validate_codes,
)
from .const import (
    COLOR_CONTROL_OPTIONS,
    CONF_CODES,
    CONF_COLOR_CONTROL,
    CONF_COLOR_TEMP_STEPS,
    CONF_DIRECTION_CONTROL,
    CONF_DISABLE_CARD,
    CONF_ESPHOME_DEVICE,
    CONF_EXTRA_COUNT,
    CONF_EXTRA_NAMES,
    CONF_FAN_NAME,
    CONF_GATEWAY_SERVICE,
    CONF_HAS_FAN_ON,
    CONF_HAS_LIGHT,
    CONF_HAS_SOUND,
    CONF_HAS_TIMERS,
    CONF_LIGHT_CONTROL,
    CONF_LIGHT_LEVEL,
    CONF_LIGHT_LEVEL_STEPS,
    CONF_NATURAL_CONTROL,
    CONF_REPEAT_COUNT,
    CONF_SPEED_COUNT,
    DEFAULT_COLOR_TEMP_STEPS,
    DEFAULT_LIGHT_LEVEL_STEPS,
    DEFAULT_REPEAT_COUNT,
    DEFAULT_SPEED_COUNT,
    DIRECTION_CONTROL_OPTIONS,
    DOMAIN,
    EVENT_RF_FAN_RECEIVED,
    LIGHT_CONTROL_NONE,
    LIGHT_CONTROL_OPTIONS,
    LIGHT_CONTROL_TOGGLE,
    LIGHT_LEVEL_OPTIONS,
    MAX_EXTRA_COUNT,
    MAX_SPEED_COUNT,
    MAX_STEP_COUNT,
    MIN_SPEED_COUNT,
    MIN_STEP_COUNT,
    NATURAL_CONTROL_OPTIONS,
    extra_action,
    extra_default_name,
)

LEARN_TIMEOUT_SEC = 30
# After the first frame, keep listening briefly so a held button's repeats can be
# collected and the noise-resistant modal frame chosen.
LEARN_COLLECT_SEC = 1.2


class RfFanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow to add a generic RF fan."""

    VERSION = 4

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RfFanOptionsFlow:
        """Return the options flow."""
        return RfFanOptionsFlow()

    def __init__(self) -> None:
        """Initialize the flow."""
        self._esphome_device: str = ""
        self._gateway_service: str = ""
        self._fan_name: str = ""
        self._speed_count: int = DEFAULT_SPEED_COUNT
        self._light_control: str = LIGHT_CONTROL_TOGGLE
        self._has_fan_on: bool = False
        self._has_light: bool = True
        self._caps: dict[str, object] = {}
        self._extra_count: int = 0
        self._extra_names: dict[str, str] = {}
        # How many positions the stepped controls model. Kept beside the
        # capabilities rather than inside them: `caps_from_data` feeds
        # `split_actions`, which decides which codes to learn, and neither count
        # changes that — an eight-step lamp is learned with the same two keys as
        # a ten-step one.
        self._steps: dict[str, int] = {}
        self._learn_codes: dict[str, str] = {}
        self._learn_action_index: int = 0
        self._learn_task: asyncio.Task[str | None] | None = None
        # Error key for the recovery form ("learn_timeout" / "duplicate_code"),
        # None while the capture loop is running normally.
        self._learn_error: str | None = None
        self._reconfigure: bool = False
        self._existing_codes: dict[str, str] = {}
        self._pending_actions: list[str] | None = None
        self._repeat_count: int = DEFAULT_REPEAT_COUNT

    _SERVICE_SUFFIX = "_transmit_rf_fan"

    @staticmethod
    def _unique_id_for(esphome_device: str, fan_name: str) -> str:
        """Stable id for a fan: gateway + name.

        slugify normalizes the dash/underscore ambiguity of ESPHome device names,
        so the same fan resolves to the same id however the gateway was typed.
        """
        return f"{slugify(esphome_device)}_{slugify(fan_name)}"

    def _gateway_service_prefixes(self) -> list[str]:
        """Raw esphome service prefixes exposing a transmit_rf_fan service."""
        esphome_services = self.hass.services.async_services().get("esphome", {})
        return sorted(
            service_name[: -len(self._SERVICE_SUFFIX)]
            for service_name in esphome_services
            if service_name.endswith(self._SERVICE_SUFFIX)
        )

    def _available_esphome_devices(self) -> list[str]:
        """List ESPHome devices exposing a transmit_rf_fan service (display names)."""
        return [prefix.replace("_", "-") for prefix in self._gateway_service_prefixes()]

    def _resolve_gateway_service(self, display_name: str) -> str:
        """Resolve a display name back to the RAW esphome service prefix.

        The raw prefix is read from the live service registry (no lossy
        dash/underscore guess). Falls back to a best-effort derivation when the
        name was typed manually while the gateway is offline.
        """
        normalized = display_name.replace("_", "-")
        for prefix in self._gateway_service_prefixes():
            if prefix.replace("_", "-") == normalized:
                return prefix
        return display_name.replace("-", "_")

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
        # A dropdown rather than a free number: the count decides how many codes have
        # to be learned, so an accidental 40 is an expensive typo. The old cap of 6
        # had no technical reason behind it and is gone (9-speed remotes exist).
        fields[vol.Required(CONF_SPEED_COUNT, default=self._speed_count)] = vol.In(
            list(range(MIN_SPEED_COUNT, MAX_SPEED_COUNT + 1))
        )
        fields[vol.Required(CONF_LIGHT_CONTROL, default=self._light_control)] = SelectSelector(
            SelectSelectorConfig(options=LIGHT_CONTROL_OPTIONS, translation_key="light_control")
        )
        fields[vol.Required(CONF_HAS_FAN_ON, default=self._has_fan_on)] = bool
        # Selectors, not checkboxes: each of these capabilities exists in more than
        # one remote shape, and the shape decides which codes get learned.
        # Each stepped capability is followed by the number of positions it models.
        # Asked for unconditionally rather than only when the capability is enabled:
        # this is a single form, so a count that appeared and disappeared with the
        # selector above it would need a second step to be filled in at all.
        for capability, options, step_key, step_default in (
            (CONF_DIRECTION_CONTROL, DIRECTION_CONTROL_OPTIONS, None, 0),
            (CONF_NATURAL_CONTROL, NATURAL_CONTROL_OPTIONS, None, 0),
            (
                CONF_COLOR_CONTROL,
                COLOR_CONTROL_OPTIONS,
                CONF_COLOR_TEMP_STEPS,
                DEFAULT_COLOR_TEMP_STEPS,
            ),
            (
                CONF_LIGHT_LEVEL,
                LIGHT_LEVEL_OPTIONS,
                CONF_LIGHT_LEVEL_STEPS,
                DEFAULT_LIGHT_LEVEL_STEPS,
            ),
        ):
            fields[
                vol.Required(capability, default=self._caps.get(capability, options[0]))
            ] = SelectSelector(
                SelectSelectorConfig(options=options, translation_key=capability)
            )
            if step_key is not None:
                fields[
                    vol.Required(step_key, default=self._steps.get(step_key, step_default))
                ] = vol.In(list(range(MIN_STEP_COUNT, MAX_STEP_COUNT + 1)))
        for capability in (
            CONF_HAS_TIMERS,
            CONF_HAS_SOUND,
        ):
            fields[vol.Required(capability, default=bool(self._caps.get(capability, False)))] = bool
        # Free-form keys: a count here, the names on the step that follows. A
        # dropdown for the same reason as the speed count -- every one of these is a
        # button somebody has to teach, so an accidental 40 is an expensive typo.
        fields[vol.Required(CONF_EXTRA_COUNT, default=self._extra_count)] = vol.In(
            list(range(0, MAX_EXTRA_COUNT + 1))
        )
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
                self._gateway_service = self._resolve_gateway_service(selected_device)
                self._fan_name = user_input[CONF_FAN_NAME].strip()
                await self.async_set_unique_id(
                    self._unique_id_for(selected_device, self._fan_name)
                )
                self._abort_if_unique_id_configured()
                self._speed_count = int(user_input[CONF_SPEED_COUNT])
                self._light_control = user_input[CONF_LIGHT_CONTROL]
                self._has_fan_on = bool(user_input[CONF_HAS_FAN_ON])
                self._has_light = self._light_control != LIGHT_CONTROL_NONE
                self._caps = caps_from_data(user_input)
                self._steps = {
                    CONF_COLOR_TEMP_STEPS: color_temp_steps(dict(user_input)),
                    CONF_LIGHT_LEVEL_STEPS: light_level_steps(dict(user_input)),
                }
                self._extra_count = extra_button_count(dict(user_input))
                if self._extra_count:
                    return await self.async_step_extra_names()
                self._extra_names = {}
                return await self.async_step_method()

        return self.async_show_form(
            step_id="user",
            data_schema=self._base_schema(include_device=True),
            description_placeholders={
                "detected": ", ".join(available_devices) if available_devices else "none",
            },
            errors=errors,
        )

    async def async_step_extra_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name the free-form keys, once their number is known.

        A separate step because the count decides how many fields there are, and a
        config-flow schema is built before it can read the answer to a field on its
        own form.

        A blank name is accepted and falls back to a generic one: the label is
        presentation, and no configuration should be blocked over one.
        """
        if user_input is not None:
            self._extra_names = {}
            for index in range(1, self._extra_count + 1):
                action = extra_action(index)
                label = str(user_input.get(action, "")).strip()
                self._extra_names[action] = label or extra_default_name(index)
            # Reconfiguring rejoins its own recap, which is where a kept code is
            # offered for re-learning and a forgotten one is dropped.
            if self._reconfigure:
                return await self.async_step_reconfigure_review()
            return await self.async_step_method()

        fields: dict[Any, Any] = {}
        for index in range(1, self._extra_count + 1):
            action = extra_action(index)
            fields[vol.Optional(action, default=self._extra_names.get(action, ""))] = str

        return self.async_show_form(
            step_id="extra_names", data_schema=vol.Schema(fields)
        )

    def _extra_names_summary(self) -> str:
        """"1 = Memory - 2 = Ionisation", for a step description.

        The learning screen labels each field from the translation keyed by its
        action name, and Home Assistant has no per-field placeholder to slip a
        user's label into. The mapping goes above the form instead.
        """
        return " - ".join(
            f"{index} = {self._extra_names.get(extra_action(index)) or extra_default_name(index)}"
            for index in range(1, self._extra_count + 1)
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
                self._learn_error = None
                self._learn_action_index = 0
                return await self.async_step_learn()
            return await self.async_step_codes()

        return self.async_show_form(
            step_id="method",
            data_schema=vol.Schema(
                {
                    # A selector rather than vol.In: it is the only form that gets
                    # its labels translated (vol.In shows the raw keys).
                    vol.Required("method", default="manual"): SelectSelector(
                        SelectSelectorConfig(
                            options=["manual", "learn"], translation_key="learn_method"
                        )
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

    def _required_actions(self) -> list[str]:
        """Every action the declared fan needs a code for, in learning order.

        One place, deliberately. This used to be spelled out at each call site, and
        a capability added to one of them was simply missing from the other: the
        reconfigure recap never asked for a free-form key's code, so the key could
        be declared and never learned (#18, found by @elmr91 on 1.8.1b1). A second
        caller that forgets an argument is not a mistake anyone can see.
        """
        required_actions, _ = split_actions(
            self._speed_count,
            self._light_control,
            has_fan_on=self._has_fan_on,
            extra_count=self._extra_count,
            **self._caps,
        )
        return required_actions

    def _actions_to_process(self) -> list[str]:
        """List the actions to process, in order."""
        if self._pending_actions is not None:
            return self._pending_actions
        return self._required_actions()

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
            self._learn_error = None
            if bool(user_input.get("skip")):
                self._learn_action_index += 1
            else:
                manual_code = str(user_input.get("code", "")).strip()
                if manual_code:
                    self._learn_error = self._store_learned_code(manual_code)
        elif self._learn_task is not None:
            # A listen has just finished: store the code or flag the failure.
            learned_code = self._learn_task.result()
            self._learn_task = None
            if learned_code is None:
                self._learn_error = "learn_timeout"
            else:
                self._learn_error = self._store_learned_code(learned_code)

        # All actions processed: create the entry.
        if self._learn_action_index >= len(actions):
            return self._finish(self._learn_codes)

        # The previous capture failed: offer manual entry / skip.
        if self._learn_error:
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
                errors={"base": self._learn_error},
            )

        # Otherwise: listen for the next action.
        return await self.async_step_learn()

    def _store_learned_code(self, code: str) -> str | None:
        """Assign a captured code to the current action, or return an error key.

        The repeats of a held button keep arriving after the flow has moved on, so
        the same frame is easily captured twice. Two actions sharing a code make the
        reverse lookup (received frame -> action) ambiguous, so it is refused.
        """
        action = self._actions_to_process()[self._learn_action_index]
        if any(
            other_code == code
            for other_action, other_code in self._learn_codes.items()
            if other_action != action
        ):
            return "duplicate_code"
        self._learn_codes[action] = code
        self._learn_action_index += 1
        return None

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
            if (
                isinstance(device, str)
                and device
                and device.replace("-", "_") != self._gateway_service
            ):
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
            except TimeoutError:
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
            CONF_GATEWAY_SERVICE: self._gateway_service,
            CONF_FAN_NAME: self._fan_name,
            CONF_SPEED_COUNT: self._speed_count,
            CONF_LIGHT_CONTROL: self._light_control,
            CONF_HAS_FAN_ON: self._has_fan_on,
            CONF_HAS_LIGHT: self._has_light,
            **self._caps,
            **self._steps,
            CONF_EXTRA_COUNT: self._extra_count,
            CONF_EXTRA_NAMES: dict(self._extra_names),
            CONF_REPEAT_COUNT: self._repeat_count,
            CONF_CODES: codes,
        }
        if self._reconfigure:
            entry = self._get_reconfigure_entry()
            # Carry a rename through to the entry itself: the title is what the
            # Integrations page shows, the unique id is what prevents a duplicate.
            return self.async_update_reload_and_abort(
                entry,
                data=data,
                title=self._fan_name,
                unique_id=self._unique_id_for(self._esphome_device, self._fan_name),
            )
        return self.async_create_entry(title=self._fan_name, data=data)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure an existing entry: pick what is actually being changed.

        Re-capturing one mis-learned button is the common case and has nothing to
        do with the fan's capabilities, so it gets its own path instead of forcing
        the whole declaration form to be re-submitted first.
        """
        entry = self._get_reconfigure_entry()
        data = entry.data

        self._reconfigure = True
        self._esphome_device = data[CONF_ESPHOME_DEVICE]
        self._gateway_service = data.get(
            CONF_GATEWAY_SERVICE, data[CONF_ESPHOME_DEVICE].replace("-", "_")
        )
        self._fan_name = data.get(CONF_FAN_NAME, entry.title)
        self._speed_count = int(data.get(CONF_SPEED_COUNT, DEFAULT_SPEED_COUNT))
        self._light_control = data.get(CONF_LIGHT_CONTROL, LIGHT_CONTROL_TOGGLE)
        self._has_fan_on = bool(data.get(CONF_HAS_FAN_ON, False))
        self._has_light = self._light_control != LIGHT_CONTROL_NONE
        self._caps = caps_from_data(data)
        self._steps = {
            CONF_COLOR_TEMP_STEPS: color_temp_steps(dict(data)),
            CONF_LIGHT_LEVEL_STEPS: light_level_steps(dict(data)),
        }
        self._extra_count = extra_button_count(dict(data))
        self._extra_names = {
            action: label or extra_default_name(index)
            for index, (action, label) in enumerate(extra_names(dict(data)).items(), start=1)
        }
        self._existing_codes = dict(data.get(CONF_CODES, {}))
        self._repeat_count = int(
            entry.options.get(
                CONF_REPEAT_COUNT, data.get(CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT)
            )
        )
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reconfigure_codes", "reconfigure_capabilities"],
        )

    async def async_step_reconfigure_codes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Keep the declared capabilities and go straight to the per-action recap."""
        return await self.async_step_reconfigure_review()

    async def async_step_reconfigure_capabilities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-declare the fan (name, speeds, capabilities), then learn the delta."""
        entry = self._get_reconfigure_entry()

        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure_capabilities",
                data_schema=self._base_schema(include_device=False),
            )

        fan_name = user_input[CONF_FAN_NAME].strip()
        # A rename changes the entry identity: refuse one that another fan on the
        # same gateway already answers to, rather than ending up with two entries
        # HA cannot tell apart.
        new_unique_id = self._unique_id_for(self._esphome_device, fan_name)
        if any(
            other.unique_id == new_unique_id and other.entry_id != entry.entry_id
            for other in self._async_current_entries()
        ):
            self._fan_name = fan_name
            self._speed_count = int(user_input[CONF_SPEED_COUNT])
            self._light_control = user_input[CONF_LIGHT_CONTROL]
            self._has_fan_on = bool(user_input[CONF_HAS_FAN_ON])
            self._caps = caps_from_data(user_input)
            self._steps = {
                CONF_COLOR_TEMP_STEPS: color_temp_steps(dict(user_input)),
                CONF_LIGHT_LEVEL_STEPS: light_level_steps(dict(user_input)),
            }
            return self.async_show_form(
                step_id="reconfigure_capabilities",
                data_schema=self._base_schema(include_device=False),
                errors={CONF_FAN_NAME: "name_already_used"},
            )

        self._fan_name = fan_name
        self._speed_count = int(user_input[CONF_SPEED_COUNT])
        self._light_control = user_input[CONF_LIGHT_CONTROL]
        self._has_fan_on = bool(user_input[CONF_HAS_FAN_ON])
        self._has_light = self._light_control != LIGHT_CONTROL_NONE
        self._caps = caps_from_data(user_input)
        self._steps = {
            CONF_COLOR_TEMP_STEPS: color_temp_steps(dict(user_input)),
            CONF_LIGHT_LEVEL_STEPS: light_level_steps(dict(user_input)),
        }
        # The same form carries the count on both paths, and only the creation path
        # used to read it: reconfiguring asked for no new code and stored nothing,
        # so the count silently returned to what it had been (#18, on 1.8.1b1).
        self._extra_count = extra_button_count(dict(user_input))
        if self._extra_count:
            return await self.async_step_extra_names()
        self._extra_names = {}
        return await self.async_step_reconfigure_review()

    async def async_step_reconfigure_review(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Recap: to learn / kept (re-learn?) / forgotten, then capture."""
        required_actions = self._required_actions()
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
                        default=self.config_entry.options.get(
                            CONF_REPEAT_COUNT,
                            self.config_entry.data.get(CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
                    vol.Required(
                        CONF_DISABLE_CARD,
                        default=self.config_entry.options.get(CONF_DISABLE_CARD, False),
                    ): bool,
                }
            ),
        )
