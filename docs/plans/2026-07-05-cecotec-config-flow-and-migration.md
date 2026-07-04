# Finalisation rf_fan + migration Cecotec — Plan d'implémentation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Assouplir le config flow de `rf_fan` pour accepter un ventilateur sans `fan_on` dédié et une lampe pilotée par un seul bouton toggle, puis migrer le ventilateur Cecotec du salon sur l'intégration.

**Architecture:** La logique « quelles actions sont obligatoires / optionnelles » et « les codes fournis sont-ils valides » est extraite de `config_flow.py` vers un module pur `actions.py` (dépend uniquement de `const.py`, aucun import Home Assistant) → testable en pytest simple. `config_flow.py` consomme ces fonctions. Le runtime (`fan.py` / `light.py`) est déjà correct grâce à `assumed_state` + fallback toggle : aucune modification. Le déploiement et la migration HA se font en phase 2, via le MCP Home Assistant.

**Tech Stack:** Python 3.12, Home Assistant custom component, voluptuous, pytest. ESPHome (`transmit_rf_fan`, TX `raw:`). Langue du repo : français.

**Contexte figé par le spike (2026-07-04) :** TX en `raw:` (validé en direct) ; décodage rc_switch RX = ❌ ; lampe on/off simple ; `assumed_state` sans synchro télécommande physique. Voir [2026-07-04-cecotec-migration-design.md](2026-07-04-cecotec-migration-design.md).

---

## Phase 1 — Code de l'intégration (TDD)

### Task 0 : Mise en place du harnais de test minimal

**Files:**
- Create: `requirements-test.txt`
- Create: `tests/__init__.py` (vide)
- Create: `tests/conftest.py`

**Step 1 : Écrire `requirements-test.txt`**

```text
pytest>=8
```

**Step 2 : Créer `tests/__init__.py`** (fichier vide).

**Step 3 : Écrire `tests/conftest.py`**

Rend `const.py` et `actions.py` importables comme modules top-level, sans exécuter `custom_components/rf_fan/__init__.py` (qui importe Home Assistant).

```python
"""Config pytest : expose le module rf_fan sans déclencher l'import Home Assistant."""

import sys
from pathlib import Path

# Le dossier du composant est ajouté au path pour importer `const` / `actions`
# en modules top-level, sans passer par le package (dont __init__ importe HA).
_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "rf_fan"
sys.path.insert(0, str(_COMPONENT_DIR))
```

**Step 4 : Vérifier que pytest tourne (aucun test encore)**

Run: `python -m pytest -q`
Expected: `no tests ran` (exit code 5), pas d'erreur d'import.

**Step 5 : Commit**

```bash
git add requirements-test.txt tests/__init__.py tests/conftest.py
git commit -m "test: minimal pytest harness for pure modules"
```

---

### Task 1 : Module `actions.py` — `split_actions()`

**Files:**
- Create: `custom_components/rf_fan/actions.py`
- Test: `tests/test_actions.py`

**Step 1 : Écrire le test qui échoue**

```python
from actions import split_actions
from const import (
    ACTION_FAN_OFF,
    ACTION_FAN_ON,
    ACTION_LIGHT_OFF,
    ACTION_LIGHT_ON,
    ACTION_LIGHT_TOGGLE,
    speed_action,
)


def test_split_actions_fan_off_and_speeds_required():
    required, optional = split_actions(speed_count=6, has_light=False)
    assert required == [ACTION_FAN_OFF, *(speed_action(i) for i in range(1, 7))]
    # fan_on est optionnel (l'allumage retombe sur speed_1)
    assert ACTION_FAN_ON in optional


def test_split_actions_light_codes_are_optional():
    required, optional = split_actions(speed_count=3, has_light=True)
    for action in (ACTION_LIGHT_ON, ACTION_LIGHT_OFF, ACTION_LIGHT_TOGGLE):
        assert action in optional
        assert action not in required


def test_split_actions_no_light_omits_light_actions():
    required, optional = split_actions(speed_count=3, has_light=False)
    for action in (ACTION_LIGHT_ON, ACTION_LIGHT_OFF, ACTION_LIGHT_TOGGLE):
        assert action not in required
        assert action not in optional
```

**Step 2 : Lancer le test → échec attendu**

Run: `python -m pytest tests/test_actions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'actions'`.

**Step 3 : Implémentation minimale**

```python
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
```

**Step 4 : Lancer le test → succès attendu**

Run: `python -m pytest tests/test_actions.py -q`
Expected: PASS (3 tests).

**Step 5 : Commit**

```bash
git add custom_components/rf_fan/actions.py tests/test_actions.py
git commit -m "feat(config_flow): pure split_actions (fan_on + light codes optional)"
```

---

### Task 2 : Module `actions.py` — `validate_codes()`

**Files:**
- Modify: `custom_components/rf_fan/actions.py`
- Test: `tests/test_actions.py`

**Step 1 : Ajouter les tests qui échouent**

```python
from actions import split_actions, validate_codes


def _speeds(n):
    return {ACTION_FAN_OFF: "c", **{speed_action(i): "c" for i in range(1, n + 1)}}


def test_validate_codes_missing_required_speed():
    required, _ = split_actions(6, has_light=False)
    codes = _speeds(6)
    del codes[speed_action(4)]
    errors = validate_codes(codes, required, has_light=False)
    assert errors == {speed_action(4): "required"}


def test_validate_codes_toggle_only_light_is_valid():
    required, _ = split_actions(6, has_light=True)
    codes = {**_speeds(6), ACTION_LIGHT_TOGGLE: "c"}
    assert validate_codes(codes, required, has_light=True) == {}


def test_validate_codes_light_without_any_code_errors():
    required, _ = split_actions(6, has_light=True)
    errors = validate_codes(_speeds(6), required, has_light=True)
    assert errors == {ACTION_LIGHT_TOGGLE: "light_code_required"}
```

**Step 2 : Lancer → échec attendu**

Run: `python -m pytest tests/test_actions.py -q`
Expected: FAIL — `ImportError: cannot import name 'validate_codes'`.

**Step 3 : Ajouter l'implémentation**

```python
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
```

**Step 4 : Lancer → succès attendu**

Run: `python -m pytest tests/test_actions.py -q`
Expected: PASS (6 tests).

**Step 5 : Commit**

```bash
git add custom_components/rf_fan/actions.py tests/test_actions.py
git commit -m "feat(config_flow): validate_codes tolerates toggle-only light"
```

---

### Task 3 : Câbler `config_flow.py` sur les fonctions pures

**Files:**
- Modify: `custom_components/rf_fan/config_flow.py`

**Step 1 : Remplacer `_split_actions` par un appel au module pur**

Supprimer la méthode `_split_actions` (lignes ~173-181) et importer depuis `actions` :

```python
from .actions import split_actions, validate_codes
```

Remplacer les usages `self._split_actions()` par `split_actions(self._speed_count, self._has_light)`.

**Step 2 : Réécrire la validation de `async_step_codes`**

Dans `async_step_codes`, remplacer la boucle de validation manuelle par :

```python
required_actions, optional_actions = split_actions(self._speed_count, self._has_light)

if user_input is not None:
    codes = {
        action: str(user_input.get(action, "")).strip()
        for action in required_actions + optional_actions
        if str(user_input.get(action, "")).strip()
    }
    errors = validate_codes(codes, required_actions, self._has_light)
    if not errors:
        return self._create_entry(codes)
```

Le schéma reste construit avec `vol.Required` pour `required_actions` et `vol.Optional` pour `optional_actions`.

**Step 3 : Vérifier la compilation du module**

Run: `python -m py_compile custom_components/rf_fan/config_flow.py custom_components/rf_fan/actions.py`
Expected: aucune sortie, exit 0.

**Step 4 : Relancer toute la suite**

Run: `python -m pytest -q`
Expected: PASS (6 tests), aucune régression.

**Step 5 : Commit**

```bash
git add custom_components/rf_fan/config_flow.py
git commit -m "refactor(config_flow): use pure split_actions/validate_codes"
```

---

### Task 4 : Traductions — message d'erreur `light_code_required`

**Files:**
- Modify: `custom_components/rf_fan/strings.json`
- Modify: `custom_components/rf_fan/translations/fr.json`
- Modify: `custom_components/rf_fan/translations/en.json`

**Step 1 : Ajouter la clé d'erreur dans les 3 fichiers**

Dans `config.error`, ajouter :
- `fr.json` : `"light_code_required": "Renseignez au moins un code lumière (ON/OFF ou bascule)."`
- `en.json` / `strings.json` : `"light_code_required": "Provide at least one light code (on/off or toggle)."`

**Step 2 : Valider le JSON**

Run: `python -c "import json,glob; [json.load(open(f,encoding='utf-8')) for f in glob.glob('custom_components/rf_fan/**/*.json', recursive=True)]"`
Expected: aucune sortie, exit 0.

**Step 3 : Commit**

```bash
git add custom_components/rf_fan/strings.json custom_components/rf_fan/translations/
git commit -m "i18n: add light_code_required error string"
```

---

## Phase 2 — Déploiement & migration (opérationnel, via MCP Home Assistant)

> Non-TDD : étapes manuelles/MCP. Faire une **backup HA** avant de commencer.

### Task 5 : Déployer le custom component

- Copier `custom_components/rf_fan/` dans la config HA (`\\homeassistant.local\config\custom_components\rf_fan\`) — ou ajouter le repo comme dépôt HACS perso de type *Integration*, puis installer.
- Redémarrer Home Assistant.
- Vérifier l'absence d'erreur : `ha_get_logs(source="error_log", search="rf_fan")`.

### Task 6 : Créer l'entrée d'intégration (mode manuel, codes pré-remplis)

Codes `raw:` à reprendre depuis `esphome-configs/esp32-ventilateur-cecotec.yaml` :

| Champ config flow | Bouton Cecotec (source) |
|---|---|
| `esphome_device` | `esp32-ventilateur-cecotec` |
| `speed_count` | `6` |
| `has_light` | `true` |
| `fan_off` | Stop |
| `fan_speed_1..6` | Vitesse 1..6 |
| `light_toggle` | Lumière |
| *(laisser vide)* | `fan_on`, `light_on`, `light_off`, `kelvin` |

- Ajouter l'intégration via l'UI (le config flow n'est pas scriptable proprement en MCP → étape UI côté utilisateur ; je fournis le tableau de codes à coller).
- Vérifier la création des entités `fan.*` et `light.*`.

### Task 7 : Test bout-en-bout des entités

- `fan.set_percentage` à plusieurs valeurs → confirmer visuellement les vitesses (via MCP `ha_call_service`).
- `fan.turn_off` → Stop.
- `light.turn_on` / `light.turn_off` → bascule.

### Task 8 : Remapper les interrupteurs muraux

- Rediriger le flow Node-RED (`94ba22cd9798a2a7`) : les appuis muraux appellent désormais `fan.*` / `light.*` au lieu des scripts/helpers.
- Tester chaque interrupteur.

### Task 9 : Nettoyage de l'ancien setup (après validation)

- Retirer les boutons ESPHome Cecotec, les helpers dead-reckoning (`input_number.cecotec_*`, `input_boolean.cecotec_*`) et la branche de décodage RF dans Node-RED.
- Garder une backup avant suppression.

---

## Hors scope (évolutions ultérieures)

- **Kelvin / température de couleur** de la lampe (dead-reckoning).
- **Synchro depuis la télécommande physique** : lambda `on_raw` firmware décodant la trame en bits stables + support d'un code de match distinct du code TX dans l'intégration.
