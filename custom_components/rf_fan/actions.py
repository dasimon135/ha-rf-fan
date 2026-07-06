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
        TIMER_HOURS,
        speed_action,
        timer_action,
    )

LIGHT_ACTIONS = (ACTION_LIGHT_ON, ACTION_LIGHT_OFF, ACTION_LIGHT_TOGGLE)


def split_actions(
    speed_count: int,
    has_light: bool,
    *,
    has_direction: bool = False,
    has_natural_preset: bool = False,
    has_color_temp: bool = False,
    has_timers: bool = False,
    has_sound: bool = False,
) -> tuple[list[str], list[str]]:
    """Retourner (actions_obligatoires, actions_optionnelles).

    Obligatoire : `fan_off` + une action par vitesse, plus les actions des
    capacités activées (inversion, flux naturel, couleur kelvin, minuteries,
    son). Chacune est facultative au niveau de la configuration mais devient
    obligatoire dès que la capacité correspondante est activée.
    Optionnel : `fan_on` (l'allumage retombe sur speed_1) et, si `has_light`,
    `light_on` / `light_off` / `light_toggle`. Au moins un code lumière est
    exigé — validé séparément par `validate_codes`.
    """
    required = [ACTION_FAN_OFF]
    required.extend(speed_action(index) for index in range(1, speed_count + 1))
    optional = [ACTION_FAN_ON]
    if has_light:
        optional.extend(LIGHT_ACTIONS)
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
    return required, optional


def validate_codes(
    codes: dict[str, str], required: list[str], has_light: bool
) -> dict[str, str]:
    """Retourner {champ: clé_erreur} ; dict vide si tout est valide."""
    errors: dict[str, str] = {}
    for action in required:
        if not codes.get(action):
            errors[action] = "required"
    if has_light and not any(codes.get(action) for action in LIGHT_ACTIONS):
        errors[ACTION_LIGHT_TOGGLE] = "light_code_required"
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
