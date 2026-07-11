# Flux de reconfiguration RF Fan — Design

*Date : 2026-07-09*

## Objectif

Aujourd'hui le learn (et la déclaration des capacités) n'existe qu'à la **création
initiale** de l'entrée. L'`OptionsFlow` ne permet de changer que `repeat_count`. Une
fois l'entrée créée, impossible d'ajouter une capacité (timer, kelvin, son, sens,
flux naturel) ni de ré-apprendre un code.

Ce design ajoute un **flux de reconfiguration** (`async_step_reconfigure`, bouton
natif *Reconfigurer*) permettant de **re-déclarer toutes les capacités** et
d'**apprendre uniquement le delta**, en conservant les codes existants — sans
détruire l'entrée ni casser le dashboard / Node-RED qui la référencent.

Contexte : le RX a été confirmé fonctionnel (2026-07-08) après reflash propre du
CC1101 ; le learn produit à nouveau des codes propres. Cette feature débloque enfin
l'usage des capacités étendues sur l'entrée de prod « Ventilateur Salon ».

## Décisions de conception

1. **Portée : re-déclaration complète + merge intelligent.** L'écran de reconfig
   re-montre tous les champs de l'étape initiale (sauf le device ESPHome, figé),
   pré-remplis avec l'existant. L'utilisateur peut tout modifier.
2. **Delta transparent (best practice).** Un écran récap montre, avant d'apprendre :
   les actions **à apprendre** (nouvellement requises, sans code), les actions
   **gardées** (déjà un code — avec une case *re-apprendre* par action, décochée par
   défaut), et les actions **oubliées** (plus requises → retirées). Rien de
   destructif en douce ; possibilité de corriger un code curé douteux.
3. **Réutilisation maximale.** Le schéma de l'étape 1 et la boucle
   `learn`/`learn_resolve` (avec timeout→skip/manuel) sont **partagés** entre la
   création initiale et la reconfig, paramétrés par la liste d'actions à traiter.

## Flux

### 1. Point d'entrée — `async_step_reconfigure`
- Récupère l'entrée via `self._get_reconfigure_entry()`.
- Pré-charge dans l'état du flow : `esphome_device` (figé), `fan_name`,
  `speed_count`, `light_control`, `has_fan_on`, capacités, et **codes existants**
  (`data[CONF_CODES]`).
- Enchaîne sur l'écran de re-déclaration.

### 2. Écran de re-déclaration — `async_step_reconfigure` (form)
- Réutilise le **schéma partagé** de l'étape 1, **sans** le champ `CONF_ESPHOME_DEVICE`
  (device non modifiable en reconfig), tous les `default=` pointant sur l'existant.
- À la soumission : stocke les nouvelles déclarations, dérive `has_light`, recalcule
  `required_actions` via `split_actions`, puis va à l'écran récap.

### 3. Écran récap du delta — `async_step_reconfigure_review` (form)
Classification à partir de `required_actions` (recalculées) vs `self._codes` (existants) :
- **à apprendre** = requises ∧ sans code existant.
- **gardées** = requises ∧ code existant → une case booléenne `relearn::<action>`
  (défaut `False`) par action.
- **oubliées** = codées ∧ plus requises (affichées en `description_placeholders`).

Le schéma = une case par action *gardée*. À la soumission :
`self._pending_actions = [à apprendre] + [gardées cochées relearn]`, dans l'ordre de
`required_actions`. Puis → étape méthode.

Cas limite : si `_pending_actions` est vide (aucune nouvelle action, aucune
re-apprise) → aller directement au merge + finish (pas d'étape méthode inutile).

### 4. Méthode + capture — réutilise `method` / `learn` / `learn_resolve` / `codes`
- La boucle de learn et l'étape manuelle itèrent sur **`self._pending_actions`** (au
  lieu de « toutes les actions »). Extraction d'un helper `_actions_to_process()` que
  la création initiale (toutes) et la reconfig (delta) alimentent différemment.
- En mode manuel de reconfig : le formulaire ne liste que `_pending_actions`, les
  champs des actions gardées non re-apprises étant absents (leur code est conservé).

### 5. Merge + persistance + reload
- `merged = {codes existants des actions toujours requises} ∪ {codes (ré)appris}`,
  moins les actions **oubliées**.
- Termine par `self.async_update_reload_and_abort(entry, data={...déclarations...,
  CONF_HAS_LIGHT dérivé, **caps, CONF_CODES: merged, CONF_REPEAT_COUNT conservé})`.
- Le reload fait apparaître/disparaître les entités des plateformes (select kelvin,
  boutons timer, bouton calibration kelvin, switch son, feature direction/preset du
  fan) selon les nouvelles capacités. Dashboard & Node-RED (qui référencent
  `fan.ventilateur_salon` / `light.lampe_salon`, inchangés) restent intacts.

## Refactor (DRY, pré-requis)

- **`_base_schema(include_device: bool)`** : construit le schéma commun (device
  optionnel) — appelé par `async_step_user` (avec device) et l'écran de reconfig
  (sans). Les `default=` proviennent d'un dict d'état pré-rempli.
- **`_actions_to_process()`** : retourne la liste d'actions que la boucle
  learn/manuel doit traiter. En création : `required + optional`. En reconfig :
  `self._pending_actions`. La boucle et l'étape codes n'utilisent plus que ce helper.
- Le stockage du code appris utilise déjà `self._learn_codes` ; en reconfig on
  **pré-remplit** `self._learn_codes` avec les codes existants gardés, pour que
  `_create_entry`/merge reparte d'une base complète.

## Rétrocompatibilité

- Aucune migration : les entrées existantes gardent leur `data`. La reconfig ne
  change une entrée que si l'utilisateur la lance et valide.
- L'`OptionsFlow` (`repeat_count`) reste inchangé et cohabite avec la reconfig.
- `manifest.json` : rien de spécial requis (le bouton *Reconfigurer* apparaît dès que
  `async_step_reconfigure` existe).

## Fichiers

- `config_flow.py` : `_base_schema`, `_actions_to_process`, `async_step_reconfigure`,
  `async_step_reconfigure_review`, généralisation de `method`/`learn`/`learn_resolve`/
  `codes` sur `_actions_to_process()`, merge + `async_update_reload_and_abort`.
- `strings.json` + `translations/{en,fr}.json` : libellés des étapes `reconfigure`,
  `reconfigure_review` (à apprendre / gardées / oubliées), cases `relearn`.
- Pas de changement `const.py` / `actions.py` (la logique d'actions est déjà pure et
  suffisante).

## Tests

- **Purs** (`tests/test_actions.py`) : inchangés — la logique `split_actions` couvre
  déjà le calcul des required ; on peut ajouter un test unitaire du **calcul de delta**
  (fonction pure extraite `classify_reconfigure_actions(required, existing_codes)` →
  `(to_learn, kept, forgotten)`) si on l'isole d'HA.
- **Config flow (phcc / CI)** : nouveau test `test_reconfigure_adds_capabilities` —
  entrée initiale basique, reconfig activant `has_timers`, learn des 4 timers,
  vérifier que les codes basiques sont conservés et les 4 timers ajoutés, et que
  l'entrée est rechargée avec les nouvelles entités.

## Hors scope

- Modifier le device ESPHome d'une entrée (figé ; supprimer/recréer si besoin).
- Fusion « intelligente » de codes raw (dédup / nettoyage du signal) — on stocke le
  code tel qu'appris.
- Import/export de codes entre entrées.
