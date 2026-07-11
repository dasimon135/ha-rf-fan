# Flux de reconfiguration RF Fan — Plan d'implémentation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Ajouter un flux de reconfiguration (`async_step_reconfigure`) qui re-déclare toutes les capacités, apprend/ré-apprend seulement le delta, conserve les codes existants, et recharge l'entrée en place — sans casser dashboard / Node-RED.

**Architecture:** Une fonction pure `classify_reconfigure_actions()` calcule (à apprendre / gardées / oubliées). Le `config_flow` est rendu DRY (schéma partagé, liste d'actions paramétrée) puis étendu de deux étapes (`reconfigure`, `reconfigure_review`). Le merge des codes réutilise `self._learn_codes` pré-amorcé, et la fin bifurque `async_create_entry` (création) vs `async_update_reload_and_abort` (reconfig).

**Tech Stack:** Python 3.12, Home Assistant custom component (HA ≥ 2024.11 pour `_get_reconfigure_entry` / `async_update_reload_and_abort`), voluptuous, pytest. Repo FR. Design : [2026-07-09-reconfigure-flow-design.md](2026-07-09-reconfigure-flow-design.md). Branche `feat/reconfigure-flow`. Vérif locale : `python -m pytest tests/test_actions.py -q` + `python -m py_compile custom_components/rf_fan/*.py`. Tests phcc = CI (skip local via `importorskip`).

---

## Task 1 : `actions.py` — classification du delta (TDD, pur)

**Files:**
- Modify: `custom_components/rf_fan/actions.py`
- Test: `tests/test_actions.py`

**Step 1 : écrire les tests d'abord (les faire échouer)**

Ajouter à `tests/test_actions.py` :
```python
from actions import classify_reconfigure_actions
from const import ACTION_FAN_OFF, ACTION_LIGHT_TOGGLE, speed_action, timer_action


def test_classify_all_kept_when_codes_complete():
    required = [ACTION_FAN_OFF, speed_action(1), ACTION_LIGHT_TOGGLE]
    existing = {ACTION_FAN_OFF: "a", speed_action(1): "b", ACTION_LIGHT_TOGGLE: "c"}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == []
    assert kept == [ACTION_FAN_OFF, speed_action(1), ACTION_LIGHT_TOGGLE]
    assert forgotten == []


def test_classify_new_required_without_code_goes_to_learn():
    required = [ACTION_FAN_OFF, timer_action(1), timer_action(2)]
    existing = {ACTION_FAN_OFF: "a"}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == [timer_action(1), timer_action(2)]
    assert kept == [ACTION_FAN_OFF]
    assert forgotten == []


def test_classify_forgotten_action_dropped():
    required = [ACTION_FAN_OFF]
    existing = {ACTION_FAN_OFF: "a", ACTION_LIGHT_TOGGLE: "old"}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == []
    assert kept == [ACTION_FAN_OFF]
    assert forgotten == [ACTION_LIGHT_TOGGLE]


def test_classify_empty_code_counts_as_missing():
    required = [ACTION_FAN_OFF, speed_action(1)]
    existing = {ACTION_FAN_OFF: "a", speed_action(1): ""}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == [speed_action(1)]
    assert kept == [ACTION_FAN_OFF]


def test_classify_preserves_required_order():
    required = [ACTION_FAN_OFF, speed_action(1), speed_action(2), ACTION_LIGHT_TOGGLE]
    existing = {speed_action(1): "b", ACTION_LIGHT_TOGGLE: "c"}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == [ACTION_FAN_OFF, speed_action(2)]
    assert kept == [speed_action(1), ACTION_LIGHT_TOGGLE]
```

Run : `python -m pytest tests/test_actions.py -q` → FAIL (`ImportError: classify_reconfigure_actions`).

**Step 2 : implémenter dans `actions.py`** (après `caps_from_data`)
```python
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
```

Run : `python -m pytest tests/test_actions.py -q` → tous PASS.

**Step 3 : commit** `feat(actions): pure delta classification for reconfigure`.

---

## Task 2 : `config_flow.py` — refactor DRY (aucun changement de comportement)

**Files:** Modify `custom_components/rf_fan/config_flow.py`

**Objectif :** extraire le schéma commun et la liste d'actions traitées, sans changer le comportement de création. Les tests existants (phcc) et `py_compile` doivent rester verts.

**Step 1 : nouveaux champs d'état** dans `__init__` :
```python
self._reconfigure: bool = False
self._existing_codes: dict[str, str] = {}
self._pending_actions: list[str] | None = None
self._forgotten_actions: list[str] = []
```

**Step 2 : extraire `_base_schema`**
Créer une méthode qui construit le `vol.Schema` de l'étape 1, `include_device` conditionnel, tous les `default=` lus depuis l'état courant (`self._...`) pour être réutilisable en reconfig (pré-remplissage) :
```python
def _base_schema(self, *, include_device: bool) -> vol.Schema:
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
    fields[vol.Required(CONF_SPEED_COUNT, default=self._speed_count)] = vol.In([3, 4, 5, 6])
    fields[vol.Required(CONF_LIGHT_CONTROL, default=self._light_control)] = SelectSelector(
        SelectSelectorConfig(options=LIGHT_CONTROL_OPTIONS, translation_key="light_control")
    )
    fields[vol.Required(CONF_HAS_FAN_ON, default=self._has_fan_on)] = bool
    fields[vol.Required(CONF_HAS_DIRECTION, default=self._caps.get(CONF_HAS_DIRECTION, False))] = bool
    fields[vol.Required(CONF_HAS_NATURAL_PRESET, default=self._caps.get(CONF_HAS_NATURAL_PRESET, False))] = bool
    fields[vol.Required(CONF_HAS_COLOR_TEMP, default=self._caps.get(CONF_HAS_COLOR_TEMP, False))] = bool
    fields[vol.Required(CONF_HAS_TIMERS, default=self._caps.get(CONF_HAS_TIMERS, False))] = bool
    fields[vol.Required(CONF_HAS_SOUND, default=self._caps.get(CONF_HAS_SOUND, False))] = bool
    return vol.Schema(fields)
```
Note : `self._fan_name` défaut `""`, `self._speed_count` défaut `DEFAULT_SPEED_COUNT`, `self._caps` défaut `{}` — donc en création les `default=` sont neutres (comportement identique). Adapter `async_step_user` pour appeler `self._base_schema(include_device=True)` au lieu de reconstruire le schéma inline. **Conserver** `description_placeholders={"detected": ...}` et `errors`.

**Step 3 : extraire `_actions_to_process`**
```python
def _actions_to_process(self) -> list[str]:
    if self._pending_actions is not None:
        return self._pending_actions
    required_actions, optional_actions = split_actions(
        self._speed_count, self._light_control, has_fan_on=self._has_fan_on, **self._caps
    )
    return required_actions + optional_actions
```
Remplacer `self._learn_actions()` par `self._actions_to_process()` dans `async_step_learn` et `async_step_learn_resolve` ; supprimer `_learn_actions`. Dans `async_step_codes`, remplacer la construction `required_actions/optional_actions` par `actions = self._actions_to_process()` ; schéma = `vol.Required(action)` pour chaque action (les optionnelles n'existent plus) ; validation `validate_codes(codes, actions)`.

⚠️ En création, `async_step_codes` doit garder son comportement : `_actions_to_process()` retourne alors `required + optional` = identique à avant.

**Step 4 : renommer `_create_entry` → `_finish`** avec bifurcation :
```python
def _finish(self, codes: dict[str, str]) -> FlowResult:
    data = {
        CONF_ESPHOME_DEVICE: self._esphome_device,
        CONF_FAN_NAME: self._fan_name,
        CONF_SPEED_COUNT: self._speed_count,
        CONF_LIGHT_CONTROL: self._light_control,
        CONF_HAS_FAN_ON: self._has_fan_on,
        CONF_HAS_LIGHT: self._has_light,
        **self._caps,
        CONF_REPEAT_COUNT: self._repeat_count,
        CONF_CODES: codes,
    }
    if self._reconfigure:
        entry = self._get_reconfigure_entry()
        return self.async_update_reload_and_abort(entry, data=data)
    return self.async_create_entry(title=self._fan_name, data=data)
```
Ajouter `self._repeat_count: int = DEFAULT_REPEAT_COUNT` dans `__init__` (en création il vaut le défaut ; en reconfig on le pré-remplira depuis l'entrée existante). Remplacer les deux appels `self._create_entry(...)` (dans `async_step_codes` et `async_step_learn_resolve`) par `self._finish(...)`.

**Step 5 : vérifier** `python -m py_compile custom_components/rf_fan/config_flow.py` ; `python -m pytest tests/ -q` (test_actions verts, phcc skip). Le comportement de création est inchangé.

**Step 6 : commit** `refactor(config_flow): shared schema + parametrized action list`.

---

## Task 3 : `config_flow.py` — étapes de reconfiguration

**Files:** Modify `custom_components/rf_fan/config_flow.py`

**Step 1 : `async_step_reconfigure`** (pré-remplissage + re-déclaration)
```python
async def async_step_reconfigure(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Reconfigurer une entrée existante : re-déclarer + apprendre le delta."""
    entry = self._get_reconfigure_entry()
    data = entry.data

    if user_input is None:
        # Pré-remplir l'état depuis l'entrée existante.
        self._reconfigure = True
        self._esphome_device = data[CONF_ESPHOME_DEVICE]
        self._fan_name = data.get(CONF_FAN_NAME, entry.title)
        self._speed_count = int(data.get(CONF_SPEED_COUNT, DEFAULT_SPEED_COUNT))
        self._light_control = data.get(CONF_LIGHT_CONTROL, LIGHT_CONTROL_TOGGLE)
        self._has_fan_on = bool(data.get(CONF_HAS_FAN_ON, False))
        self._caps = caps_from_data(data)
        self._existing_codes = dict(data.get(CONF_CODES, {}))
        self._repeat_count = int(
            entry.options.get(CONF_REPEAT_COUNT, data.get(CONF_REPEAT_COUNT, DEFAULT_REPEAT_COUNT))
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._base_schema(include_device=False),
        )

    # Soumission : appliquer les nouvelles déclarations.
    self._fan_name = user_input[CONF_FAN_NAME].strip()
    self._speed_count = int(user_input[CONF_SPEED_COUNT])
    self._light_control = user_input[CONF_LIGHT_CONTROL]
    self._has_fan_on = bool(user_input[CONF_HAS_FAN_ON])
    self._has_light = self._light_control != LIGHT_CONTROL_NONE
    self._caps = caps_from_data(user_input)
    return await self.async_step_reconfigure_review()
```
Note : le device n'est pas dans le schéma reconfig → `self._esphome_device` reste celui pré-rempli.

**Step 2 : `async_step_reconfigure_review`** (récap delta + cases re-apprendre)
```python
async def async_step_reconfigure_review(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Récap : à apprendre / gardées (re-apprendre ?) / oubliées, puis capture."""
    required_actions, _ = split_actions(
        self._speed_count, self._light_control, has_fan_on=self._has_fan_on, **self._caps
    )
    to_learn, kept, forgotten = classify_reconfigure_actions(
        required_actions, self._existing_codes
    )

    if user_input is not None:
        relearn = [a for a in kept if bool(user_input.get(f"relearn::{a}"))]
        # Base de codes = codes existants encore requis (gardés + re-appris écrasés ensuite).
        self._learn_codes = {a: self._existing_codes[a] for a in kept}
        self._pending_actions = [a for a in required_actions if a in to_learn or a in relearn]
        self._forgotten_actions = forgotten
        if not self._pending_actions:
            return self._finish(dict(self._learn_codes))
        self._learn_action_index = 0
        return await self.async_step_method()

    # Formulaire : une case par action gardée.
    schema_fields: dict[Any, Any] = {
        vol.Optional(f"relearn::{a}", default=False): bool for a in kept
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
```

**Step 3 : merge à la fin de la boucle learn/manuel.**
`_finish` reçoit déjà `self._learn_codes` complet (kept pré-amorcés + delta appris). Vérifier que :
- `async_step_learn_resolve` écrit dans `self._learn_codes[actions[index]]` (déjà le cas) et appelle `self._finish(self._learn_codes)` quand `index >= len(actions)`.
- `async_step_codes` (manuel) en reconfig : partir de la base `self._learn_codes` puis surcharger. Adapter le calcul des `codes` :
```python
codes = dict(self._learn_codes) if self._reconfigure else {}
codes.update({
    action: str(user_input.get(action, "")).strip()
    for action in actions
    if str(user_input.get(action, "")).strip()
})
errors = validate_codes(codes, actions)
if not errors:
    return self._finish(codes)
```
(En création `self._learn_codes` est vide → `codes` repart de `{}`, comportement identique.)

**Step 4 : vérifier** `py_compile` + `pytest tests/ -q` (purs verts).

**Step 5 : commit** `feat(config_flow): reconfigure + review steps with code merge`.

---

## Task 4 : i18n — libellés des nouvelles étapes

**Files:** Modify `custom_components/rf_fan/strings.json`, `translations/en.json`, `translations/fr.json`

**Step 1 :** sous `config.step`, ajouter deux étapes (dans les 3 fichiers ; `strings.json` = `en.json` en anglais).

EN (`strings.json` + `en.json`) :
```json
"reconfigure": {
  "title": "RF Fan - Reconfigure",
  "description": "Re-declare the fan capabilities. Existing codes are kept; only newly required buttons are learned next.",
  "data": {
    "fan_name": "Fan display name",
    "speed_count": "Number of discrete speeds",
    "light_control": "Light control",
    "has_fan_on": "Fan has a dedicated on button",
    "has_direction": "Reverse direction (reverse button)",
    "has_natural_preset": "Natural airflow",
    "has_color_temp": "Color temperature (Kelvin)",
    "has_timers": "Sleep timers (1h/2h/4h/8h)",
    "has_sound": "Sound (beep)"
  }
},
"reconfigure_review": {
  "title": "RF Fan - Review changes",
  "description": "To learn: {to_learn}\nKept (tick to re-learn): {kept}\nRemoved: {forgotten}",
  "data": {}
}
```
FR (`fr.json`) :
```json
"reconfigure": {
  "title": "Ventilateur RF - Reconfiguration",
  "description": "Re-déclarez les capacités du ventilateur. Les codes existants sont conservés ; seuls les nouveaux boutons requis seront appris ensuite.",
  "data": {
    "fan_name": "Nom d'affichage du ventilateur",
    "speed_count": "Nombre de vitesses distinctes",
    "light_control": "Commande de la lumière",
    "has_fan_on": "Le ventilateur a un bouton marche dédié",
    "has_direction": "Sens inverse (bouton reverse)",
    "has_natural_preset": "Flux d'air naturel",
    "has_color_temp": "Température de couleur (Kelvin)",
    "has_timers": "Minuteries (1h/2h/4h/8h)",
    "has_sound": "Son (bip)"
  }
},
"reconfigure_review": {
  "title": "Ventilateur RF - Vérification",
  "description": "À apprendre : {to_learn}\nGardées (cocher pour ré-apprendre) : {kept}\nRetirées : {forgotten}",
  "data": {}
}
```
Les cases `relearn::<action>` sont dynamiques (clés générées) → pas de libellé i18n dédié (HA affiche la clé ; acceptable, le récap liste déjà les actions). Ne PAS inventer de libellés par action ici.

**Step 2 :** ajouter sous `config.abort` (créer la clé si absente) :
- EN : `"reconfigure_successful": "Reconfiguration saved and reloaded."`
- FR : `"reconfigure_successful": "Reconfiguration enregistrée et rechargée."`

**Step 3 :** valider le JSON des 3 fichiers (`python -c "import json,glob; [json.load(open(f,encoding='utf-8')) for f in glob.glob('custom_components/rf_fan/**/*.json', recursive=True)]"`).

**Step 4 : commit** `i18n: reconfigure + reconfigure_review labels`.

---

## Task 5 : test phcc + vérification finale

**Files:** Modify `tests/test_config_flow.py`

**Step 1 : test du flux reconfig** (skip si phcc absent, via le motif `importorskip` déjà en tête du fichier).
Scénario : créer une entrée basique (light toggle, 3 vitesses, codes basiques présents), lancer `entry.start_reconfigure_flow(hass)` (ou `hass.config_entries.flow.async_init(DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id})`), soumettre le formulaire `reconfigure` en activant `has_timers=True`, cocher aucun relearn dans `reconfigure_review`, choisir `method=manual`, fournir les 4 codes timer, et vérifier :
- résultat `type == FlowResultType.ABORT`, `reason == "reconfigure_successful"` ;
- `entry.data[CONF_CODES]` contient les codes basiques d'origine **et** `timer_1h..timer_8h` ;
- `entry.data[CONF_HAS_TIMERS] is True`.
Ajouter éventuellement un second cas : activer `has_color_temp`, cocher `relearn::light_toggle`, méthode manuel, vérifier que `light_toggle` est bien écrasé par le nouveau code et que `light_kelvin` est ajouté.

**Step 2 : lancer toute la suite** `python -m pytest tests/ -q` → purs verts, phcc skip en local (les nouveaux tests s'exécuteront en CI).

**Step 3 : vérification statique** `python -m py_compile custom_components/rf_fan/*.py`.

**Step 4 : commit** `test(config_flow): reconfigure adds capabilities and merges codes`.

---

## Vérification finale (contrôleur)

- `python -m pytest tests/ -q` (purs verts, phcc skip) + `py_compile` tous modules.
- Revue finale (`superpowers:requesting-code-review`) puis `superpowers:finishing-a-development-branch` (merge dans `main`).
- **Déploiement live + validation** (session utilisateur, hors fenêtre de boot ESP) :
  1. Copier `custom_components/rf_fan` sur HA, redémarrer HA (nouvelles étapes de flow).
  2. Réglages → Appareils → « Ventilateur Salon » → **Reconfigurer**.
  3. Activer une capacité (ex. minuteries), écran récap → apprendre les 4 boutons timer (une pression franche par bouton, hors des ~5 s post-boot).
  4. Vérifier l'apparition des 4 `button.*timer*` et le maintien de `fan.ventilateur_salon` / `light.lampe_salon` (dashboard + Node-RED intacts).
  5. Itérer sur kelvin / son / sens / flux naturel.
