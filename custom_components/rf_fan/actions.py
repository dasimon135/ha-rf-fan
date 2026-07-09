"""Logique pure de sélection/validation des actions RF (testable sans Home Assistant)."""

from __future__ import annotations

try:  # runtime Home Assistant : import relatif dans le package
    from .const import (
        ACTION_FAN_NATURAL,
        ACTION_FAN_OFF,
        ACTION_FAN_ON,
        ACTION_FAN_REVERSE,
        ACTION_LIGHT_KELVIN,
        ACTION_LIGHT_OFF,
        ACTION_LIGHT_ON,
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        LIGHT_CONTROL_ON_OFF,
        LIGHT_CONTROL_TOGGLE,
        TIMER_HOURS,
        speed_action,
        timer_action,
    )
except ImportError:  # pragma: no cover - tests : import top-level via conftest
    from const import (
        ACTION_FAN_NATURAL,
        ACTION_FAN_OFF,
        ACTION_FAN_ON,
        ACTION_FAN_REVERSE,
        ACTION_LIGHT_KELVIN,
        ACTION_LIGHT_OFF,
        ACTION_LIGHT_ON,
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        LIGHT_CONTROL_ON_OFF,
        LIGHT_CONTROL_TOGGLE,
        TIMER_HOURS,
        speed_action,
        timer_action,
    )


def split_actions(
    speed_count: int,
    light_control: str = "none",
    *,
    has_fan_on: bool = False,
    has_direction: bool = False,
    has_natural_preset: bool = False,
    has_color_temp: bool = False,
    has_timers: bool = False,
    has_sound: bool = False,
) -> tuple[list[str], list[str]]:
    """Actions requises selon le style de commande et les capacités déclarées.

    Obligatoire : `fan_off` + une action par vitesse, plus les actions des
    capacités déclarées : `fan_on` si `has_fan_on`, la ou les actions lumière
    selon `light_control` (`toggle` -> `light_toggle` ; `on_off` -> `light_on`
    et `light_off` ; `none` -> aucune), puis les actions des capacités activées
    (inversion, flux naturel, couleur kelvin, minuteries, son).
    Aucune action optionnelle : la liste retournée est toujours vide.
    """
    required = [ACTION_FAN_OFF]
    required.extend(speed_action(index) for index in range(1, speed_count + 1))
    if has_fan_on:
        required.append(ACTION_FAN_ON)
    if light_control == LIGHT_CONTROL_TOGGLE:
        required.append(ACTION_LIGHT_TOGGLE)
    elif light_control == LIGHT_CONTROL_ON_OFF:
        required.extend([ACTION_LIGHT_ON, ACTION_LIGHT_OFF])
    if has_direction:
        required.append(ACTION_FAN_REVERSE)
    if has_natural_preset:
        required.append(ACTION_FAN_NATURAL)
    if has_color_temp:
        required.append(ACTION_LIGHT_KELVIN)
    if has_timers:
        required.extend(timer_action(hours) for hours in TIMER_HOURS)
    if has_sound:
        required.append(ACTION_SOUND_TOGGLE)
    return required, []


def validate_codes(codes: dict[str, str], required: list[str]) -> dict[str, str]:
    """Retourner {champ: clé_erreur} ; dict vide si tout est valide."""
    errors: dict[str, str] = {}
    for action in required:
        if not codes.get(action):
            errors[action] = "required"
    return errors


CAPABILITY_FLAGS = (
    "has_direction",
    "has_natural_preset",
    "has_color_temp",
    "has_timers",
    "has_sound",
)


def caps_from_data(data: dict[str, object]) -> dict[str, bool]:
    """Extraire les capacités d'un dict de config entry (défaut False)."""
    return {flag: bool(data.get(flag, False)) for flag in CAPABILITY_FLAGS}


def classify_reconfigure_actions(
    required: list[str], existing_codes: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Répartir les actions pour une reconfiguration.

    - to_learn : requises sans code existant (nouvellement requises).
    - kept : requises disposant déjà d'un code (conservées).
    - forgotten : codées mais plus requises (à retirer).
    Ordre : to_learn/kept suivent `required` ; forgotten suit `existing_codes`.
    """
    to_learn = [a for a in required if not existing_codes.get(a)]
    kept = [a for a in required if existing_codes.get(a)]
    forgotten = [a for a in existing_codes if a not in required]
    return to_learn, kept, forgotten
