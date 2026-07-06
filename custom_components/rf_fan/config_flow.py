"""Config flow pour l'intégration RF Fan."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .actions import CAPABILITY_FLAGS, split_actions, validate_codes
from .const import (
    CONF_CODES,
    CONF_ESPHOME_DEVICE,
    CONF_FAN_NAME,
    CONF_HAS_COLOR_TEMP,
    CONF_HAS_DIRECTION,
    CONF_HAS_LIGHT,
    CONF_HAS_NATURAL_PRESET,
    CONF_HAS_SOUND,
    CONF_HAS_TIMERS,
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
        self._caps: dict[str, bool] = {}
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
                self._caps = {
                    flag: bool(user_input.get(flag, False)) for flag in CAPABILITY_FLAGS
                }
                return await self.async_step_method()

        if available_devices:
            device_key = vol.Required(
                CONF_ESPHOME_DEVICE, default=default_device or available_devices[0]
            )
            device_field: Any = SelectSelector(
                SelectSelectorConfig(options=available_devices)
            )
        else:
            device_key = vol.Optional(CONF_ESPHOME_DEVICE, default=default_device)
            device_field = str

        data_schema = vol.Schema(
            {
                device_key: device_field,
                vol.Required(CONF_FAN_NAME): str,
                vol.Required(CONF_SPEED_COUNT, default=DEFAULT_SPEED_COUNT): vol.In([3, 4, 5, 6]),
                vol.Required(CONF_HAS_LIGHT, default=DEFAULT_HAS_LIGHT): bool,
                vol.Required(CONF_HAS_DIRECTION, default=False): bool,
                vol.Required(CONF_HAS_NATURAL_PRESET, default=False): bool,
                vol.Required(CONF_HAS_COLOR_TEMP, default=False): bool,
                vol.Required(CONF_HAS_TIMERS, default=False): bool,
                vol.Required(CONF_HAS_SOUND, default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
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
            self._speed_count, self._has_light, **self._caps
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
            self._speed_count, self._has_light, **self._caps
        )
        return required_actions + optional_actions

    async def async_step_learn(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Écran de progression : écouter l'action courante.

        Cette étape ne renvoie QUE ``SHOW_PROGRESS`` ou ``SHOW_PROGRESS_DONE`` :
        depuis un écran de progression, HA n'autorise aucune autre transition. Le
        stockage du code et le passage à l'action suivante se font dans
        ``async_step_learn_resolve``, qui porte un ``step_id`` différent. Ce
        changement de ``step_id`` est indispensable : c'est lui qui déclenche
        l'événement ``data_entry_flow_progressed`` rafraîchissant le frontend
        (cf. ``FlowManager._async_configure``). Boucler sur le même ``step_id``
        (``show_progress`` → ``show_progress_done(next_step_id="learn")``) ne
        change pas le ``step_id`` → aucun rafraîchissement → le spinner reste figé
        alors même que le backend a avancé.
        """
        actions = self._learn_actions()

        # L'écoute est terminée : passer à la résolution (change de step_id).
        if self._learn_task is not None and self._learn_task.done():
            return self.async_show_progress_done(next_step_id="learn_resolve")

        # Démarrer l'écoute si nécessaire, puis afficher la progression.
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
    ) -> FlowResult:
        """Résoudre une écoute terminée (ou le formulaire de reprise), puis continuer.

        ``step_id`` distinct de ``learn`` : la transition ``learn`` →
        ``learn_resolve`` fait changer le ``step_id``, ce qui déclenche le
        rafraîchissement du frontend. On y traite aussi les cas qui ne peuvent
        pas être renvoyés directement depuis l'écran de progression (formulaire de
        reprise après timeout, création de l'entrée).
        """
        actions = self._learn_actions()

        if user_input is not None:
            # Soumission du formulaire de reprise : ignorer ou coller un code.
            self._learn_timeout = False
            if bool(user_input.get("skip")):
                self._learn_action_index += 1
            else:
                manual_code = str(user_input.get("code", "")).strip()
                if manual_code:
                    self._learn_codes[actions[self._learn_action_index]] = manual_code
                    self._learn_action_index += 1
        elif self._learn_task is not None:
            # Une écoute vient de se terminer : stocker le code ou marquer le timeout.
            learned_code = self._learn_task.result()
            self._learn_task = None
            if learned_code is not None:
                self._learn_codes[actions[self._learn_action_index]] = learned_code
                self._learn_action_index += 1
            else:
                self._learn_timeout = True

        # Toutes les actions traitées : créer l'entrée.
        if self._learn_action_index >= len(actions):
            return self._create_entry(self._learn_codes)

        # Timeout sur l'écoute précédente : proposer saisie manuelle / ignorer.
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

        # Sinon : écouter l'action suivante.
        return await self.async_step_learn()

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
                **self._caps,
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
