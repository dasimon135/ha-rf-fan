# Modèle d'actions étendu (capacités optionnelles) — Plan d'implémentation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ajouter à `rf_fan` des capacités optionnelles (sens inverse, flux naturel, kelvin, minuteries, son) déclarées au config flow, et remplacer le champ device texte par un menu déroulant.

**Architecture:** Config flow piloté par capacités : des booléens à l'étape 1 gèrent (1) les actions RF demandées via les fonctions pures de `actions.py`, (2) les entités/features créées par chaque plateforme (qui `return` si sa capacité est absente). Tout en dead-reckoning. Rétrocompat par `data.get(flag, False)`. La position kelvin est partagée entre `light` et `select` via `hass.data[DOMAIN][entry_id]` + un signal dispatcher.

**Tech Stack:** Python 3.12, Home Assistant custom component, voluptuous, pytest. Repo en français. Design : [2026-07-06-action-model-design.md](2026-07-06-action-model-design.md).

**Contrainte de test connue :** les tests entités/config-flow nécessitent `pytest-homeassistant-custom-component`, non installable sur le poste Windows (HA 2026.3+ exige Python 3.14.2 ; lru-dict sans wheel + pas de MSVC). → tests purs (`test_actions.py`) exécutables localement ; tests phcc écrits pour CI Linux et `skip` si phcc absent. Vérif locale des plateformes : `python -m py_compile` + JSON + `python -m pytest tests/test_actions.py`.

---

## Task 1 : Constantes + `actions.py` (capacités) — TDD

**Files:**
- Modify: `custom_components/rf_fan/const.py`
- Modify: `custom_components/rf_fan/actions.py`
- Test: `tests/test_actions.py`

**Step 1 : Ajouter les constantes dans `const.py`**

```python
# Capacités (config flow)
CONF_HAS_DIRECTION: Final = "has_direction"
CONF_HAS_NATURAL_PRESET: Final = "has_natural_preset"
CONF_HAS_COLOR_TEMP: Final = "has_color_temp"
CONF_HAS_TIMERS: Final = "has_timers"
CONF_HAS_SOUND: Final = "has_sound"

# Nouvelles actions
ACTION_FAN_REVERSE: Final = "fan_reverse"
ACTION_FAN_NATURAL: Final = "fan_natural"
ACTION_LIGHT_KELVIN: Final = "light_kelvin"
ACTION_SOUND_TOGGLE: Final = "sound_toggle"
TIMER_HOURS: Final = (1, 2, 4, 8)

# Preset flux naturel
PRESET_NORMAL: Final = "normal"
PRESET_NATURAL: Final = "natural"

# Positions couleur (select kelvin) : ordre du cycle matériel
COLOR_TEMP_OPTIONS: Final = ["Chaud", "Neutre", "Froid"]


def timer_action(hours: int) -> str:
    """Clé d'action pour la minuterie de N heures."""
    return f"timer_{hours}h"
```

**Step 2 : Écrire les tests (dans `tests/test_actions.py`), les faire échouer**

```python
from actions import split_actions
from const import (
    ACTION_FAN_NATURAL,
    ACTION_FAN_REVERSE,
    ACTION_LIGHT_KELVIN,
    ACTION_SOUND_TOGGLE,
    timer_action,
)


def test_split_actions_capabilities_off_by_default():
    required, optional = split_actions(6, has_light=False)
    for action in (ACTION_FAN_REVERSE, ACTION_FAN_NATURAL, ACTION_LIGHT_KELVIN,
                   ACTION_SOUND_TOGGLE, timer_action(1)):
        assert action not in required
        assert action not in optional


def test_split_actions_direction_and_preset_required_when_enabled():
    required, _ = split_actions(6, has_light=False, has_direction=True,
                                has_natural_preset=True)
    assert ACTION_FAN_REVERSE in required
    assert ACTION_FAN_NATURAL in required


def test_split_actions_color_temp_and_sound_required_when_enabled():
    required, _ = split_actions(6, has_light=True, has_color_temp=True,
                                has_sound=True)
    assert ACTION_LIGHT_KELVIN in required
    assert ACTION_SOUND_TOGGLE in required


def test_split_actions_timers_add_four_actions():
    required, _ = split_actions(6, has_light=False, has_timers=True)
    for hours in (1, 2, 4, 8):
        assert timer_action(hours) in required
```

Run: `python -m pytest tests/test_actions.py -q` → FAIL (`split_actions()` got an unexpected keyword argument).

**Step 3 : Étendre `split_actions` dans `actions.py`**

Nouvelle signature (kwargs à défaut `False`, rétrocompatible : `has_light` reste positionnel/kw) :

```python
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
        required.extend(timer_action(h) for h in TIMER_HOURS)
    if has_sound:
        required.append(ACTION_SOUND_TOGGLE)
    return required, optional
```

Ajouter les imports nécessaires (`ACTION_FAN_REVERSE`, `ACTION_FAN_NATURAL`, `ACTION_LIGHT_KELVIN`, `ACTION_SOUND_TOGGLE`, `timer_action`, `TIMER_HOURS`) dans le shim try/except relatif+absolu, comme les autres. `validate_codes` est inchangée : les nouvelles actions étant dans `required`, la boucle générique les valide déjà.

Run: `python -m pytest tests/test_actions.py -q` → PASS (tous).

**Step 4 : Helper de construction des capacités**

Ajouter dans `actions.py` une fonction pure qui extrait les capacités d'un dict de données (utilisée par config_flow et les plateformes, DRY) :

```python
CAPABILITY_FLAGS = (
    "has_direction",
    "has_natural_preset",
    "has_color_temp",
    "has_timers",
    "has_sound",
)


def caps_from_data(data: dict) -> dict[str, bool]:
    """Extraire les capacités d'un dict de config entry (défaut False)."""
    return {flag: bool(data.get(flag, False)) for flag in CAPABILITY_FLAGS}
```

Test :
```python
from actions import caps_from_data

def test_caps_from_data_defaults_false():
    assert caps_from_data({}) == {
        "has_direction": False, "has_natural_preset": False,
        "has_color_temp": False, "has_timers": False, "has_sound": False,
    }

def test_caps_from_data_reads_true():
    assert caps_from_data({"has_direction": True})["has_direction"] is True
```

Run: `python -m pytest tests/test_actions.py -q` → PASS.

**Step 5 : Commit**

```bash
git add custom_components/rf_fan/const.py custom_components/rf_fan/actions.py tests/test_actions.py
git commit -m "feat(actions): capability-gated actions (direction/preset/kelvin/timers/sound)"
```

---

## Task 2 : `config_flow.py` — dropdown device + capacités

**Files:** Modify `custom_components/rf_fan/config_flow.py`

**Step 1 : Étape 1 — champ device en menu déroulant + booléens de capacités**

Importer le selector :
```python
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
```

Dans `async_step_user`, remplacer le schéma. Le device devient un `SelectSelector` (options = passerelles détectées) quand il y en a ; ajouter les 5 booléens :

```python
device_field = (
    SelectSelector(SelectSelectorConfig(options=available_devices))
    if available_devices
    else str
)
data_schema = vol.Schema({
    vol.Required(CONF_ESPHOME_DEVICE, default=default_device): device_field
    if available_devices else vol.Optional(CONF_ESPHOME_DEVICE, default=default_device),
    vol.Required(CONF_FAN_NAME): str,
    vol.Required(CONF_SPEED_COUNT, default=DEFAULT_SPEED_COUNT): vol.In([3, 4, 5, 6]),
    vol.Required(CONF_HAS_LIGHT, default=DEFAULT_HAS_LIGHT): bool,
    vol.Required(CONF_HAS_DIRECTION, default=False): bool,
    vol.Required(CONF_HAS_NATURAL_PRESET, default=False): bool,
    vol.Required(CONF_HAS_COLOR_TEMP, default=False): bool,
    vol.Required(CONF_HAS_TIMERS, default=False): bool,
    vol.Required(CONF_HAS_SOUND, default=False): bool,
})
```
> Note : garder le fallback `str` si aucune passerelle détectée (pour ne pas bloquer). Simplifier si besoin, mais conserver la validation `selected_device not in available_devices` existante.

**Step 2 : Mémoriser les capacités + passer à `split_actions`**

- Dans `__init__`, ajouter `self._caps: dict[str, bool] = {}`.
- Dans le bloc `else` de validation de `async_step_user` : `self._caps = {flag: bool(user_input.get(flag, False)) for flag in CAPABILITY_FLAGS}`.
- Remplacer les appels `split_actions(self._speed_count, self._has_light)` (dans `async_step_codes` et `_learn_actions`) par `split_actions(self._speed_count, self._has_light, **self._caps)`.
- Dans `_create_entry`, ajouter les flags à `data` : `**self._caps` (ou champ par champ).

**Step 3 : Vérifier**

Run: `python -m py_compile custom_components/rf_fan/config_flow.py` → exit 0.
Run: `python -m pytest tests/test_actions.py -q` → 6+ PASS (pas de régression).

**Step 4 : Commit**
```bash
git add custom_components/rf_fan/config_flow.py
git commit -m "feat(config_flow): device dropdown + capability toggles"
```

---

## Task 3 : `entity.py` — helper d'envoi multiple + accès état partagé

**Files:** Modify `custom_components/rf_fan/entity.py`

**Step 1 : Ajouter un helper pour envoyer N fois une action (cycle kelvin)**

```python
async def _async_transmit_times(self, action: str, times: int) -> bool:
    """Émettre `times` fois le code d'une action (cycle). True si au moins une émission."""
    sent_any = False
    for _ in range(max(0, times)):
        if await self._async_transmit_action(action):
            sent_any = True
    return sent_any
```

**Step 2 : Accès à l'état partagé de l'entrée** (position kelvin)

```python
def _entry_runtime(self) -> dict:
    """Dict d'état partagé de l'entrée (créé dans __init__.py)."""
    return self.hass.data[DOMAIN][self._config_entry.entry_id]
```
(Importer `DOMAIN` déjà présent.)

**Step 3 : Vérifier + commit**
```bash
python -m py_compile custom_components/rf_fan/entity.py
git add custom_components/rf_fan/entity.py
git commit -m "feat(entity): multi-transmit helper + shared runtime accessor"
```

---

## Task 4 : `fan.py` — features DIRECTION + PRESET_MODE

**Files:** Modify `custom_components/rf_fan/fan.py`

**Spec :**
- Lire les capacités : `has_direction = config_entry.data.get(CONF_HAS_DIRECTION, False)`, idem preset.
- `_attr_supported_features` : ajouter `FanEntityFeature.DIRECTION` si `has_direction`, `FanEntityFeature.PRESET_MODE` si `has_natural_preset`.
- Si preset : `_attr_preset_modes = [PRESET_NORMAL, PRESET_NATURAL]`.
- État supposé : `self._direction: str | None = None` (`"forward"`/`"reverse"`), `self._preset: str | None = None`.
- `current_direction` / `preset_mode` properties.
- `async_set_direction(direction)` : si `self._direction != direction`, envoyer `ACTION_FAN_REVERSE` (toggle) ; MAJ `self._direction`, `async_write_ha_state()`.
- `async_set_preset_mode(preset_mode)` : si `self._preset != preset_mode`, envoyer `ACTION_FAN_NATURAL` ; MAJ, write state.
- `_handle_rf_event` : sur réception `ACTION_FAN_REVERSE` → basculer `self._direction` ; sur `ACTION_FAN_NATURAL` → basculer `self._preset` (dead-reckoning RX).

**Steps :**
1. Implémenter (voir spec ; suivre le style existant de `fan.py`).
2. `python -m py_compile custom_components/rf_fan/fan.py` → exit 0.
3. Commit : `feat(fan): optional reverse direction and natural preset`.

**Note test :** couvert par le test phcc (Task 10) ; pas de test pur possible (dépend de HA).

---

## Task 5 : `select.py` (nouveau) + couplage kelvin dans `light.py`

**Files:** Create `custom_components/rf_fan/select.py` ; Modify `custom_components/rf_fan/light.py`

**Spec select :**
- `async_setup_entry` : `return` si `not data.get(CONF_HAS_COLOR_TEMP, False)`.
- Entité `SelectEntity` (hérite `RfFanBaseEntity`), `_attr_options = COLOR_TEMP_OPTIONS`, `_attr_name = "Température couleur"`, unique_id `{entry_id}_color_temp`.
- `current_option` : `COLOR_TEMP_OPTIONS[self._entry_runtime()["kelvin_position"]]`.
- `async_select_option(option)` : `target = COLOR_TEMP_OPTIONS.index(option)` ; `steps = (target - pos) % 3` ; `await self._async_transmit_times(ACTION_LIGHT_KELVIN, steps)` ; `runtime["kelvin_position"] = target` ; `async_write_ha_state()`.
- `async_added_to_hass` : `async_dispatcher_connect(hass, f"{DOMAIN}_{entry_id}_kelvin", self._on_kelvin_changed)` (self._on_kelvin_changed = write_ha_state).
- RX : écouter aussi `ACTION_LIGHT_KELVIN` reçu → `runtime["kelvin_position"] = (pos + 1) % 3` + write state.

**Spec couplage light :**
- Si `has_color_temp` : dans `async_turn_on`, après émission réussie, `runtime["kelvin_position"] = (pos + 1) % 3` et `async_dispatcher_send(hass, f"{DOMAIN}_{entry_id}_kelvin")` (l'allumage matériel avance la couleur). Idem sur RX light-on.

**Steps :**
1. Créer `select.py`, modifier `light.py`.
2. `python -m py_compile custom_components/rf_fan/select.py custom_components/rf_fan/light.py`.
3. Commit : `feat(select): kelvin color-temp select with light coupling`.

---

## Task 6 : `button.py` (nouveau) — minuteries

**Files:** Create `custom_components/rf_fan/button.py`

**Spec :**
- `async_setup_entry` : `return` si `not data.get(CONF_HAS_TIMERS, False)`.
- Créer 4 `ButtonEntity` (une par `h in TIMER_HOURS`), `_attr_name = f"Minuterie {h}h"`, unique_id `{entry_id}_timer_{h}h`.
- `async_press` : `await self._async_transmit_action(timer_action(h))`.

**Steps :** implémenter → `py_compile` → commit `feat(button): sleep-timer buttons`.

---

## Task 7 : `switch.py` (nouveau) — son

**Files:** Create `custom_components/rf_fan/switch.py`

**Spec :**
- `async_setup_entry` : `return` si `not data.get(CONF_HAS_SOUND, False)`.
- `SwitchEntity`, `_attr_name = "Son"`, unique_id `{entry_id}_sound`, `_is_on: bool | None = None`.
- `async_turn_on/off` : si `_is_on != cible`, envoyer `ACTION_SOUND_TOGGLE` ; MAJ, write state.
- RX : sur `ACTION_SOUND_TOGGLE` reçu → basculer `_is_on`.

**Steps :** implémenter → `py_compile` → commit `feat(switch): sound toggle`.

---

## Task 8 : `__init__.py` — plateformes + état partagé

**Files:** Modify `custom_components/rf_fan/__init__.py`

**Step 1 :**
```python
from homeassistant.const import Platform

PLATFORMS = [Platform.FAN, Platform.LIGHT, Platform.SELECT, Platform.BUTTON, Platform.SWITCH]

async def async_setup_entry(hass, entry):
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"kelvin_position": 0}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
```
(Importer `DOMAIN` depuis `.const`.) Les plateformes non concernées `return` immédiatement dans leur `async_setup_entry` → aucune entité créée.

**Step 2 :** `python -m py_compile custom_components/rf_fan/__init__.py` → commit `feat: forward select/button/switch platforms + shared runtime state`.

---

## Task 9 : Traductions

**Files:** Modify `strings.json`, `translations/en.json`, `translations/fr.json`

**Step 1 :** Dans `config.step.user.data`, ajouter les labels des 5 capacités (`has_direction`, `has_natural_preset`, `has_color_temp`, `has_timers`, `has_sound`). Dans `config.step.codes.data` et `config.step.learn_resolve` (le cas échéant), ajouter les nouvelles actions (`fan_reverse`, `fan_natural`, `light_kelvin`, `timer_1h`…`timer_8h`, `sound_toggle`). Ajouter une section `entity` (select/switch/button names) si souhaité (optionnel — les `_attr_name` suffisent).

**Step 2 :** Valider le JSON : `python -c "import json,glob; [json.load(open(f,encoding='utf-8')) for f in glob.glob('custom_components/rf_fan/**/*.json', recursive=True)]"` → exit 0.

**Step 3 :** Commit `i18n: capabilities and new action labels`.

---

## Task 10 : Test config flow « toutes capacités » (phcc / CI)

**Files:** Modify `tests/test_config_flow.py`

**Spec :** ajouter un test qui initie un flow avec toutes les capacités à `true` (has_light + les 5), passe en mode manuel (plus simple que learn pour ce test), fournit un code par action requise, et vérifie que `CREATE_ENTRY` contient tous les codes + les flags. Utiliser `speed_count=3` pour limiter. Garder le `pytest.importorskip("pytest_homeassistant_custom_component")` en tête de fichier.

**Steps :** écrire le test (il ne tourne qu'en CI) → `python -m pytest tests/ -q` doit rester `6+ passed, N skipped` localement → commit `test(config_flow): all-capabilities manual flow`.

---

## Vérification finale

- `python -m pytest tests/ -q` → tous les tests purs verts, phcc skippés.
- `python -m py_compile custom_components/rf_fan/*.py` → exit 0.
- JSON valide.
- Revue finale (superpowers:requesting-code-review), puis superpowers:finishing-a-development-branch.
- Déploiement live + test manuel (recréer l'entrée avec capacités) : hors plan automatisé, à faire ensemble après.
