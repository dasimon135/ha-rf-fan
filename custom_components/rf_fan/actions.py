"""Logique pure de sélection/validation des actions RF (testable sans Home Assistant)."""

from __future__ import annotations

try:  # runtime Home Assistant : import relatif dans le package
    from .const import (
        ACTION_FAN_OFF,
        ACTION_FAN_ON,
        ACTION_LIGHT_OFF,
        ACTION_LIGHT_ON,
        ACTION_LIGHT_TOGGLE,
        speed_action,
    )
except ImportError:  # pragma: no cover - tests : import top-level via conftest
    from const import (
        ACTION_FAN_OFF,
        ACTION_FAN_ON,
        ACTION_LIGHT_OFF,
        ACTION_LIGHT_ON,
        ACTION_LIGHT_TOGGLE,
        speed_action,
    )

LIGHT_ACTIONS = (ACTION_LIGHT_ON, ACTION_LIGHT_OFF, ACTION_LIGHT_TOGGLE)


def split_actions(speed_count: int, has_light: bool) -> tuple[list[str], list[str]]:
    """Retourner (actions_obligatoires, actions_optionnelles).

    Obligatoire : `fan_off` + une action par vitesse.
    Optionnel : `fan_on` (l'allumage retombe sur speed_1) et, si `has_light`,
    `light_on` / `light_off` / `light_toggle`. Au moins un code lumière est
    exigé — validé séparément par `validate_codes`.
    """
    required = [ACTION_FAN_OFF]
    required.extend(speed_action(index) for index in range(1, speed_count + 1))
    optional = [ACTION_FAN_ON]
    if has_light:
        optional.extend(LIGHT_ACTIONS)
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
