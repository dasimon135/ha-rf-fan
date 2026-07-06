# Style de commande déclaré + calibration Kelvin — Design

*Date : 2026-07-06*

## Objectif

Deux raffinements du modèle d'actions, issus du test live :

1. **Déclarer le style de commande** à l'étape 1 pour que l'apprentissage/manuel ne
   demande **que les boutons réellement présents** → suppression totale des « skips »
   à 30 s (aujourd'hui `fan_on`, `light_on`, `light_off` sont demandés puis ignorés).
2. **Calibrer le Kelvin** : le `select` est en dead-reckoning depuis une position
   supposée (Chaud) ; si la lampe est ailleurs, les choix sont décalés. Ajout d'une
   calibration + persistance entre redémarrages.

## 1. Style de commande

### Lumière — `light_control` (remplace `has_light` au config flow)
Choix à 3 valeurs à l'étape 1 : `none` / `toggle` / `on_off`.
- `none` → pas d'entité light, aucune action lumière.
- `toggle` → entité light ; action requise : **`light_toggle`** seulement.
- `on_off` → entité light ; actions requises : **`light_on` + `light_off`**.

### Ventilo — `has_fan_on` (nouveau booléen)
« Bouton marche dédié ? » (défaut `false`). Coché → `fan_on` requis. Non coché →
jamais demandé (l'allumage retombe sur vitesse 1, déjà le comportement).

### Effet sur `split_actions()`
Nouvelle signature (pure, testable) :
```
split_actions(speed_count, light_control="none", *, has_fan_on=False,
              has_direction=False, has_natural_preset=False,
              has_color_temp=False, has_timers=False, has_sound=False)
```
- required = `fan_off` + vitesses + (`fan_on` si `has_fan_on`) + les actions des
  capacités cochées + les actions lumière selon `light_control`.
- optional = `[]` (tout ce qui est déclaré est requis).
- `validate_codes` : la règle spéciale « au moins un code lumière » **disparaît**
  (les actions lumière sont désormais des `required` classiques).

### Rétrocompatibilité
- Les **entités** continuent de lire `CONF_HAS_LIGHT` (inchangé). Les nouvelles
  entrées stockent `has_light` **dérivé** (`light_control != "none"`) en plus de
  `light_control` et `has_fan_on`.
- `light_control`/`has_fan_on` ne servent qu'au **config flow** (nouvelles entrées).
  L'entrée existante « Ventilateur Salon » (`has_light: true`, code `light_toggle`)
  n'exécute pas le config flow → **inchangée**. Aucune migration.

## 2. Calibration Kelvin

### a) Bouton de calibration
Une entité `button` « Couleur → Chaud (calibrer) » (si `has_color_temp`). Presser
remet la position supposée à **0 (Chaud)** **sans émettre**. L'utilisateur amène la
lampe sur Chaud physiquement, presse → le `select` est réaligné. Équivalent propre
du recalibrage manuel de l'ancien setup.

### b) Persistance entre redémarrages
Le `select` devient un `RestoreEntity` : au démarrage il restaure sa dernière
position au lieu de repartir de Chaud, et **réamorce** `hass.data[DOMAIN][entry_id]
["kelvin_position"]` depuis l'état restauré. Plus de dérive à chaque restart ; la
calibration ne sert que si la vraie télécommande est utilisée.

**Limite assumée** : dead-reckoning open-loop (la lampe ne dit jamais sa couleur).
Calibration + persistance couvrent l'essentiel ; pas de perfection visée.

## Fichiers

- `const.py` : `CONF_LIGHT_CONTROL`, `LIGHT_CONTROL_NONE/TOGGLE/ON_OFF`,
  `CONF_HAS_FAN_ON`.
- `actions.py` : nouvelle signature `split_actions` + `validate_codes` simplifié +
  helper de construction des kwargs depuis les données d'entrée.
- `config_flow.py` : étape 1 (`light_control` en select, `has_fan_on` en case),
  stockage `light_control`/`has_fan_on`/`has_light` dérivé, appel `split_actions`.
- `button.py` : ajout du bouton de calibration (gated `has_color_temp`), en plus
  des minuteries (gated `has_timers`).
- `select.py` : `RestoreEntity` (restauration + réamorçage runtime).
- `strings.json` + `translations/{en,fr}.json` : libellés `light_control`,
  `has_fan_on`, bouton calibration ; retrait du libellé `has_light`.

## Tests

- **Purs** (`test_actions.py`) : `split_actions`/`validate_codes` nouvelle
  signature (none/toggle/on_off, has_fan_on) — exécutables localement.
- **Config flow** (phcc/CI) : mise à jour du test all-capabilities (light_control).
- Restore/calibration : testable en phcc (CI), noté.

## Hors scope

- Migration active des entrées existantes (elles marchent telles quelles).
- Calibration sur un cran autre que Chaud (un seul point de référence suffit).
