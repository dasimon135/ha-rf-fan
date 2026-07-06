"""Tests du config flow — mode apprentissage (nécessitent un environnement HA).

⚠️ Non exécutable sur la machine de dev Windows utilisée pour ce repo :
Home Assistant 2026.3+ exige Python >= 3.14.2, or `lru-dict` n'a pas de wheel
pour cet interpréteur et le poste n'a pas de compilateur MSVC ; les combinaisons
HA/phcc installables sous Python 3.13 retombent aussi sur un build natif.
À lancer en CI Linux (ou toute machine avec l'environnement de test HA) via
`pytest-homeassistant-custom-component`. Le module se `skip` proprement si phcc
est absent, pour ne pas casser la suite de tests purs (`test_actions.py`).

Test de régression principal : `test_learn_progress_event_fires_on_rf_signal`.
Il vérifie que HA émet bien l'événement `data_entry_flow_progressed` quand un
signal RF est reçu pendant l'apprentissage. C'est cet événement qui fait
rafraîchir le frontend ; le bug d'origine venait de la boucle d'apprentissage qui
gardait le même `step_id` ("learn") entre `async_show_progress` et
`async_show_progress_done(next_step_id="learn")` — HA ne notifiant le frontend que
sur changement de `step_id` (ou de `progress_action`/`description_placeholders`
d'un `SHOW_PROGRESS`), l'événement n'était jamais émis et le spinner restait figé.
Un simple re-`async_configure` manuel masquerait le bug (la boucle publique
compense l'absence de notification) : d'où l'assertion sur l'événement lui-même.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_USER  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402

from custom_components.rf_fan.const import DOMAIN, EVENT_RF_FAN_RECEIVED  # noqa: E402

DEVICE = "esp32-test"
EVENT_PROGRESSED = "data_entry_flow_progressed"


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Activer le chargement du custom component pour tous les tests du module."""
    yield


async def _start_learn(hass: HomeAssistant):
    """Amener le flow jusqu'à l'écran d'apprentissage de la 1re action (fan_off)."""
    # Le config flow liste les passerelles via les services esphome *_transmit_rf_fan.
    hass.services.async_register(
        "esphome", "esp32_test_transmit_rf_fan", lambda call: None
    )
    await hass.async_block_till_done()

    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "esphome_device": DEVICE,
            "fan_name": "Test",
            "speed_count": 3,
            "has_light": False,
        },
    )
    result = await flow.async_configure(result["flow_id"], {"method": "learn"})
    return flow, result


async def test_learn_progress_event_fires_on_rf_signal(hass: HomeAssistant) -> None:
    """Régression : un `data_entry_flow_progressed` doit être émis à réception RF."""
    flow, result = await _start_learn(hass)
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["description_placeholders"]["action"] == "fan_off"

    progressed: list = []
    hass.bus.async_listen(EVENT_PROGRESSED, lambda event: progressed.append(event))

    hass.bus.async_fire(EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "C_off"})
    await hass.async_block_till_done()

    assert progressed, "aucun data_entry_flow_progressed émis -> frontend figé"


async def test_learn_flow_advances_and_creates_entry(hass: HomeAssistant) -> None:
    """Happy-path complet : chaque signal RF fait avancer jusqu'à la création."""
    flow, result = await _start_learn(hass)
    flow_id = result["flow_id"]

    seen: list[str] = []
    for _ in range(10):
        if result["type"] != FlowResultType.SHOW_PROGRESS:
            break
        action = result["description_placeholders"]["action"]
        seen.append(action)
        hass.bus.async_fire(
            EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": f"C_{action}"}
        )
        await hass.async_block_till_done()
        # Simule le re-fetch du frontend après l'événement de progression.
        result = await flow.async_configure(flow_id)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert seen[:4] == ["fan_off", "fan_speed_1", "fan_speed_2", "fan_speed_3"]
    codes = result["data"]["codes"]
    assert codes["fan_off"] == "C_fan_off"
    assert codes["fan_speed_1"] == "C_fan_speed_1"
    assert codes["fan_speed_3"] == "C_fan_speed_3"


async def test_all_capabilities_manual_flow(hass: HomeAssistant) -> None:
    """Manuel avec toutes les capacités : la liste d'actions et l'entrée sont complètes."""
    hass.services.async_register(
        "esphome", "esp32_test_transmit_rf_fan", lambda call: None
    )
    await hass.async_block_till_done()
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "esphome_device": DEVICE,
            "fan_name": "Full",
            "speed_count": 3,
            "light_control": "toggle",
            "has_fan_on": False,
            "has_direction": True,
            "has_natural_preset": True,
            "has_color_temp": True,
            "has_timers": True,
            "has_sound": True,
        },
    )
    result = await flow.async_configure(result["flow_id"], {"method": "manual"})
    assert result["step_id"] == "codes"

    # Fournir un code par action requise. required = fan_off + speed_1..3 +
    # light_toggle (via at-least-one) + fan_reverse + fan_natural + light_kelvin
    # + timer_1h/2h/4h/8h + sound_toggle. Fournir aussi light_toggle pour la
    # règle "au moins un code lumière".
    codes_input = {
        "fan_off": "C_off",
        "fan_speed_1": "C_s1", "fan_speed_2": "C_s2", "fan_speed_3": "C_s3",
        "light_toggle": "C_lt",
        "fan_reverse": "C_rev", "fan_natural": "C_nat", "light_kelvin": "C_kel",
        "timer_1h": "C_t1", "timer_2h": "C_t2", "timer_4h": "C_t4", "timer_8h": "C_t8",
        "sound_toggle": "C_snd",
    }
    result = await flow.async_configure(result["flow_id"], codes_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["has_direction"] and data["has_color_temp"] and data["has_sound"]
    codes = data["codes"]
    assert codes["fan_reverse"] == "C_rev"
    assert codes["light_kelvin"] == "C_kel"
    assert codes["timer_8h"] == "C_t8"
    assert codes["sound_toggle"] == "C_snd"
