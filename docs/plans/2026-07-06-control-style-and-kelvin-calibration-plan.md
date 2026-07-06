# Style de commande + calibration Kelvin — Plan d'implémentation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Déclarer le style de commande (lumière none/toggle/on_off, ventilo `has_fan_on`) pour que le config flow ne demande que les boutons présents (fin des skips), et ajouter la calibration Kelvin (bouton + persistance).

**Architecture:** `split_actions()` (pure) prend `light_control` + `has_fan_on` et ne met en `required` que les actions déclarées ; config flow expose un select + une case. Entités inchangées côté runtime (lisent toujours `has_light`, dérivé). Kelvin : bouton de calibration (reset position, no TX) + `select` en `RestoreEntity`.

**Tech Stack:** Python 3.12, Home Assistant custom component, voluptuous, pytest. Repo FR. Design : [2026-07-06-control-style-and-kelvin-calibration-design.md](2026-07-06-control-style-and-kelvin-calibration-design.md). Branche `feat/action-model`. Vérif locale : `python -m pytest tests/test_actions.py -q` + `python -m py_compile ...`. Tests phcc = CI (skip local).

---

## Task 1 : const + `actions.py` — style de commande (TDD)

**Files:** Modify `const.py`, `actions.py`, `tests/test_actions.py`

**Step 1 : const.py**
```python
CONF_LIGHT_CONTROL: Final = "light_control"
CONF_HAS_FAN_ON: Final = "has_fan_on"
LIGHT_CONTROL_NONE: Final = "none"
LIGHT_CONTROL_TOGGLE: Final = "toggle"
LIGHT_CONTROL_ON_OFF: Final = "on_off"
LIGHT_CONTROL_OPTIONS: Final = [LIGHT_CONTROL_NONE, LIGHT_CONTROL_TOGGLE, LIGHT_CONTROL_ON_OFF]
```

**Step 2 : tests (test_actions.py), les faire échouer**
```python
from actions import split_actions, validate_codes
from const import (
    ACTION_FAN_OFF, ACTION_FAN_ON, ACTION_LIGHT_ON, ACTION_LIGHT_OFF,
    ACTION_LIGHT_TOGGLE, speed_action,
)

def test_split_light_none_has_no_light_action():
    required, optional = split_actions(6, light_control="none")
    for a in (ACTION_LIGHT_ON, ACTION_LIGHT_OFF, ACTION_LIGHT_TOGGLE):
        assert a not in required and a not in optional

def test_split_light_toggle_requires_only_toggle():
    required, _ = split_actions(6, light_control="toggle")
    assert ACTION_LIGHT_TOGGLE in required
    assert ACTION_LIGHT_ON not in required and ACTION_LIGHT_OFF not in required

def test_split_light_on_off_requires_on_and_off():
    required, _ = split_actions(6, light_control="on_off")
    assert ACTION_LIGHT_ON in required and ACTION_LIGHT_OFF in required
    assert ACTION_LIGHT_TOGGLE not in required

def test_split_fan_on_only_when_declared():
    req_no, opt_no = split_actions(6, light_control="none")
    assert ACTION_FAN_ON not in req_no and ACTION_FAN_ON not in opt_no
    req_yes, _ = split_actions(6, light_control="none", has_fan_on=True)
    assert ACTION_FAN_ON in req_yes

def test_validate_codes_no_special_light_rule():
    # toggle déclaré mais code manquant -> erreur "required" classique
    required, _ = split_actions(6, light_control="toggle")
    codes = {ACTION_FAN_OFF: "c", **{speed_action(i): "c" for i in range(1, 7)}}
    errors = validate_codes(codes, required, has_light=True)
    assert errors.get(ACTION_LIGHT_TOGGLE) == "required"
```
Run → FAIL (signature).

**Step 3 : actions.py**
Nouvelle `split_actions` :
```python
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
    required = [ACTION_FAN_OFF]
    required.extend(speed_action(i) for i in range(1, speed_count + 1))
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
        required.extend(timer_action(h) for h in TIMER_HOURS)
    if has_sound:
        required.append(ACTION_SOUND_TOGGLE)
    return required, []
```
Simplifier `validate_codes` : supprimer le bloc `has_light and not any(LIGHT_ACTIONS)` ; garder la boucle générique `required`. Le paramètre `has_light` peut rester (ignoré) pour ne pas casser l'appelant, OU être retiré et l'appelant mis à jour — au choix, mais garder les tests verts. Recommandé : signature `validate_codes(codes, required)` (retirer `has_light`) et mettre à jour l'appel dans config_flow.
Ajouter les imports `LIGHT_CONTROL_TOGGLE/ON_OFF` dans le shim.
Ajouter un helper :
```python
def split_kwargs_from_data(data: dict[str, object]) -> dict[str, object]:
    """kwargs pour split_actions à partir d'un dict d'entrée."""
    return {
        "light_control": data.get(CONF_LIGHT_CONTROL, LIGHT_CONTROL_NONE),
        "has_fan_on": bool(data.get(CONF_HAS_FAN_ON, False)),
        **caps_from_data(data),
    }
```
(importer `CONF_LIGHT_CONTROL`, `CONF_HAS_FAN_ON`, `LIGHT_CONTROL_NONE`.)

**Step 4 :** mettre à jour les tests capacités existants qui appelaient `split_actions(6, has_light=False)` → `split_actions(6, light_control="none")` et `has_light=True` → `light_control="toggle"`. Run → tous PASS.

**Step 5 : commit** `feat(actions): declared light control style + optional fan_on`.

---

## Task 2 : `config_flow.py` — select light_control + has_fan_on

**Files:** Modify `config_flow.py`

**Spec :**
- Étape 1 : retirer `vol.Required(CONF_HAS_LIGHT, ...): bool`. Ajouter
  `vol.Required(CONF_LIGHT_CONTROL, default=LIGHT_CONTROL_TOGGLE): SelectSelector(SelectSelectorConfig(options=LIGHT_CONTROL_OPTIONS, translation_key="light_control"))`
  et `vol.Required(CONF_HAS_FAN_ON, default=False): bool`.
- Dans la validation : stocker `self._light_control = user_input[CONF_LIGHT_CONTROL]`, `self._has_fan_on = bool(user_input[CONF_HAS_FAN_ON])`, et **dériver** `self._has_light = self._light_control != LIGHT_CONTROL_NONE`.
- Remplacer les appels `split_actions(self._speed_count, self._has_light, **self._caps)` par `split_actions(self._speed_count, self._light_control, has_fan_on=self._has_fan_on, **self._caps)` (dans `async_step_codes` et `_learn_actions`).
- `_create_entry` : stocker `CONF_LIGHT_CONTROL`, `CONF_HAS_FAN_ON`, et `CONF_HAS_LIGHT` (dérivé) dans `data`.
- Si `validate_codes` a perdu `has_light`, adapter l'appel.
- Imports : `CONF_LIGHT_CONTROL, CONF_HAS_FAN_ON, LIGHT_CONTROL_NONE, LIGHT_CONTROL_TOGGLE, LIGHT_CONTROL_OPTIONS`.

**Verify :** `py_compile config_flow.py` ; `pytest tests/test_actions.py -q` (tous verts).
**Commit :** `feat(config_flow): light control select + dedicated fan-on toggle`.

---

## Task 3 : Calibration Kelvin — button.py + select.py

**Files:** Modify `button.py`, `select.py`

**button.py :**
- `async_setup_entry` : construire une liste. Si `has_timers` → ajouter les 4 `RfFanTimerButton`. Si `data.get(CONF_HAS_COLOR_TEMP, False)` → ajouter un `RfFanKelvinCalibrateButton`. `async_add_entities(entities)` si non vide (sinon `return`).
- `class RfFanKelvinCalibrateButton(RfFanBaseEntity, ButtonEntity)` : unique_id `{entry_id}_kelvin_calibrate`, name "Couleur → Chaud (calibrer)". `async_press` : `runtime = self._entry_runtime(); runtime["kelvin_position"] = 0; async_dispatcher_send(self.hass, self._kelvin_signal())`. (N'émet AUCUN code RF.) Imports : `async_dispatcher_send`, `CONF_HAS_COLOR_TEMP`.

**select.py :**
- Faire hériter `RfFanColorTempSelect` aussi de `RestoreEntity` (`from homeassistant.helpers.restore_state import RestoreEntity`).
- Dans `async_added_to_hass` (avant les abonnements) : `last = await self.async_get_last_state()`; si `last` et `last.state in COLOR_TEMP_OPTIONS` : `self._entry_runtime()["kelvin_position"] = COLOR_TEMP_OPTIONS.index(last.state)`. Puis abonnements existants + `async_write_ha_state()`.

**Verify :** `py_compile button.py select.py` ; `pytest tests/test_actions.py -q`.
**Commit :** `feat(kelvin): calibration button + restore position across restarts`.

---

## Task 4 : i18n + test phcc

**Files:** Modify `strings.json`, `translations/en.json`, `translations/fr.json`, `tests/test_config_flow.py`

**Step 1 : i18n**
- Dans `config.step.user.data` : retirer `has_light` ; ajouter `light_control` et `has_fan_on`.
  - EN : `"light_control": "Light control"`, `"has_fan_on": "Fan has a dedicated on button"`.
  - FR : `"light_control": "Commande de la lumière"`, `"has_fan_on": "Le ventilateur a un bouton marche dédié"`.
- Ajouter la traduction des options du select `light_control` sous `selector` :
  ```json
  "selector": { "light_control": { "options": {
     "none": "Aucune", "toggle": "Bouton toggle unique", "on_off": "Deux boutons (on/off)"
  }}}
  ```
  (FR ci-dessus ; EN : "None", "Single toggle button", "Two buttons (on/off)").
- Valider le JSON.

**Step 2 : test phcc** — mettre à jour `test_all_capabilities_manual_flow` : remplacer `"has_light": True` par `"light_control": "toggle"` et ajouter `"has_fan_on": False` dans le user step. Les codes fournis restent cohérents (light_toggle requis). Ajouter éventuellement un cas `light_control="on_off"` fournissant `light_on`/`light_off`.
- `pytest tests/ -q` → 12+ passed, phcc skipped.

**Commit :** `i18n+test: light control labels; all-caps flow update`.

---

## Vérification finale
- `python -m pytest tests/ -q` (purs verts, phcc skip) + `py_compile` tous modules.
- Revue finale (requesting-code-review) → finishing-a-development-branch.
- Déploiement live + validation (recréer une entrée : learn ne demande plus que les vrais boutons ; tester calibration kelvin).
