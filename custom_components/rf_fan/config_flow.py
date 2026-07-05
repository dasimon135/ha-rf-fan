"""Config flow pour l'intégration RF Fan."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .actions import split_actions, validate_codes
from .const import (
    CONF_CODES,
    CONF_ESPHOME_DEVICE,
    CONF_FAN_NAME,
    CONF_HAS_LIGHT,
    CONF_REPEAT_COUNT,
    CONF_SPEED_COUNT,
    DEFAULT_HAS_LIGHT,
    DEFAULT_REPEAT_COUNT,
    DEFAULT_SPEED_COUNT,
    DOMAIN,
    EVENT_RF_FAN_RECEIVED,
)

LEARN_TIMEOUT_SEC = 30


class RfFanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow pour ajouter un ventilateur RF générique."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RfFanOptionsFlow:
        """Retourner le flow d'options."""
        return RfFanOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialiser le flow."""
        self._esphome_device: str = ""
        self._fan_name: str = ""
        self._speed_count: int = DEFAULT_SPEED_COUNT
        self._has_light: bool = DEFAULT_HAS_LIGHT
        self._learn_codes: dict[str, str] = {}
        self._learn_action_index: int = 0
        self._learn_task: asyncio.Task[str | None] | None = None
        self._learn_timeout: bool = False

    def _available_esphome_devices(self) -> list[str]:
        """Lister les devices ESPHome exposant un service transmit_rf_fan."""
        esphome_services = self.hass.services.async_services().get("esphome", {})
        devices = []
        suffix = "_transmit_rf_fan"
        for service_name in esphome_services:
            if service_name.endswith(suffix):
                devices.append(service_name[: -len(suffix)].replace("_", "-"))
        return sorted(devices)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Étape 1: infos générales du ventilateur."""
        errors: dict[str, str] = {}
        available_devices = self._available_esphome_devices()
        default_device = available_devices[0] if len(available_devices) == 1 else ""

        if user_input is not None:
            selected_device = user_input.get(CONF_ESPHOME_DEVICE, "").strip()
            if not selected_device and len(available_devices) == 1:
                selected_device = available_devices[0]

            if not selected_device:
                if len(available_devices) > 1:
                    errors[CONF_ESPHOME_DEVICE] = "required_esphome_device"
                else:
                    errors[CONF_ESPHOME_DEVICE] = "unknown_esphome_device"
            elif selected_device not in available_devices:
                errors[CONF_ESPHOME_DEVICE] = "unknown_esphome_device"
            else:
                self._esphome_device = selected_device
                self._fan_name = user_input[CONF_FAN_NAME].strip()
                self._speed_count = int(user_input[CONF_SPEED_COUNT])
                self._has_light = bool(user_input[CONF_HAS_LIGHT])
                return await self.async_step_method()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ESPHOME_DEVICE, default=default_device): str,
                    vol.Required(CONF_FAN_NAME): str,
                    vol.Required(CONF_SPEED_COUNT, default=DEFAULT_SPEED_COUNT): vol.In([3, 4, 5, 6]),
                    vol.Required(CONF_HAS_LIGHT, default=DEFAULT_HAS_LIGHT): bool,
                }
            ),
            description_placeholders={
                "detected": ", ".join(available_devices) if available_devices else "aucun",
            },
            errors=errors,
        )

    async def async_step_method(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choisir entre saisie manuelle et apprentissage."""
        if user_input is not None:
            if user_input["method"] == "learn":
                self._learn_codes = {}
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
    ) -> FlowResult:
        """Étape manuelle: mapping action -> code RF."""
        errors: dict[str, str] = {}
        required_actions, optional_actions = split_actions(
            self._speed_count, self._has_light
        )

        if user_input is not None:
            codes = {
                action: str(user_input.get(action, "")).strip()
                for action in required_actions + optional_actions
                if str(user_input.get(action, "")).strip()
            }
            errors = validate_codes(codes, required_actions, self._has_light)
            if not errors:
                return self._create_entry(codes)

        schema_fields: dict[Any, Any] = {}
        for action in required_actions:
            schema_fields[vol.Required(action)] = str
        for action in optional_actions:
            schema_fields[vol.Optional(action)] = str

        return self.async_show_form(
            step_id="codes",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    def _learn_actions(self) -> list[str]:
        """Lister les actions à apprendre dans l'ordre."""
        required_actions, optional_actions = split_actions(
            self._speed_count, self._has_light
        )
        return required_actions + optional_actions

    async def async_step_learn(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Apprendre les codes d'une action après l'autre."""
        actions = self._learn_actions()

        # Une écoute est en cours ou vient de se terminer : la résoudre d'abord.
        # HA relance automatiquement cette étape quand la tâche se termine ; on ne
        # doit donc jamais piloter le flow à la main (cf. async_show_progress).
        if self._learn_task is not None:
            if not self._learn_task.done():
                return self.async_show_progress(
                    step_id="learn",
                    progress_action="listen_rf_signal",
                    progress_task=self._learn_task,
                    description_placeholders={
                        "action": actions[self._learn_action_index],
                        "timeout": str(LEARN_TIMEOUT_SEC),
                    },
                )

            learned_code = self._learn_task.result()
            self._learn_task = None
            if learned_code is not None:
                self._learn_codes[actions[self._learn_action_index]] = learned_code
                self._learn_action_index += 1
            else:
                self._learn_timeout = True
            # Toujours sortir de l'écran de progression via show_progress_done.
            return self.async_show_progress_done(next_step_id="learn")

        # Soumission d'un formulaire (saisie manuelle, ignorer, ou réessayer).
        if user_input is not None:
            self._learn_timeout = False
            if bool(user_input.get("skip")):
                self._learn_action_index += 1
            else:
                learned_code = str(user_input.get("code", "")).strip()
                if learned_code:
                    self._learn_codes[actions[self._learn_action_index]] = learned_code
                    self._learn_action_index += 1

        # Toutes les actions traitées : créer l'entrée.
        if self._learn_action_index >= len(actions):
            return self._create_entry(self._learn_codes)

        # Timeout sur l'écoute précédente : proposer saisie manuelle / ignorer.
        if self._learn_timeout:
            return self.async_show_form(
                step_id="learn",
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

        # Démarrer l'écoute de l'action courante.
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

    async def _async_wait_for_rf_signal(self) -> str | None:
        """Attendre un événement RF de la passerelle sélectionnée."""
        result: str | None = None
        event_received = asyncio.Event()

        @callback
        def _handle_event(event: Any) -> None:
            nonlocal result
            data = event.data
            device = data.get("device")
            if isinstance(device, str) and device != self._esphome_device:
                return

            code = data.get("code")
            if not isinstance(code, str) or not code.strip():
                return

            result = code.strip()
            event_received.set()

        unsubscribe = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, _handle_event)

        try:
            await asyncio.wait_for(event_received.wait(), timeout=LEARN_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            return None
        finally:
            unsubscribe()

        return result

    def _create_entry(self, codes: dict[str, str]) -> FlowResult:
        """Créer le config entry final."""
        return self.async_create_entry(
            title=self._fan_name,
            data={
                CONF_ESPHOME_DEVICE: self._esphome_device,
                CONF_FAN_NAME: self._fan_name,
                CONF_SPEED_COUNT: self._speed_count,
                CONF_HAS_LIGHT: self._has_light,
                CONF_REPEAT_COUNT: DEFAULT_REPEAT_COUNT,
                CONF_CODES: codes,
            },
        )


class RfFanOptionsFlow(OptionsFlow):
    """Options flow pour RF fan."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialiser les options."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configurer les options d'émission RF."""
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
