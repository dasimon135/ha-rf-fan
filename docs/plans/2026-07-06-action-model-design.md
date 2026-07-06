# Modèle d'actions étendu + capacités optionnelles — Design

*Date : 2026-07-06*

## Objectif

Étendre `rf_fan` pour modéliser plus de capacités des ventilateurs RF réels
(sens inverse, flux d'air naturel, température de couleur, minuteries, son), tout
en gardant l'intégration **utilisable pour des ventilos simples** : chaque
capacité est **optionnelle**, déclarée au config flow, et ne crée d'entités /
features / actions que si elle est cochée. Améliore aussi le config flow : le
choix de la passerelle ESPHome passe d'un champ texte libre à un **menu
déroulant** des passerelles détectées.

Contexte : la télécommande du ventilo de l'utilisateur n'a **pas** de `fan_on`
ni de `light_on`/`off` séparés (seulement toggle light, vitesses 1-6, off), et a
en plus : sens inverse, flux d'air naturel, kelvin (cycle 3 crans), minuteries
1h/2h/4h/8h, toggle son.

## Principe : tout est piloté par capacités

À l'étape 1 du config flow, l'utilisateur coche les capacités de son ventilo.
Chaque capacité pilote en cascade : (1) les **actions RF** demandées en
learn/manuel, (2) les **features/entités** créées, (3) rien si non cochée.

**Capacités** (booléens, défaut `false`) :
`has_light` (existant), `has_direction`, `has_natural_preset`,
`has_color_temp`, `has_timers`, `has_sound`.

**Rétrocompatibilité (crucial)** : les entrées existantes n'ont aucun de ces
flags. Toute lecture se fait en `data.get(flag, False)` → capacités absentes →
comportement strictement inchangé. Aucune migration destructive.

## Entités (toutes en dead-reckoning / état supposé)

| Capacité | Entité / feature | Comportement |
|---|---|---|
| (base) | `fan` : vitesse + on/off | existant |
| `has_direction` | `fan` feature **DIRECTION** | `set_direction(fwd/rev)` → envoie `fan_reverse` (toggle) si direction supposée ≠ cible |
| `has_natural_preset` | `fan` feature **PRESET_MODE** | `preset_modes = ["normal","natural"]` → `set_preset_mode` envoie `fan_natural` (toggle) si preset supposé ≠ cible |
| `has_light` | `light` : on/off | existant (toggle-only supporté) |
| `has_color_temp` | `select` « Température couleur » | options `[Chaud, Neutre, Froid]` → `select_option` envoie `(cible − pos) mod 3` appuis `light_kelvin` |
| `has_timers` | 4 `button` « Minuterie 1h/2h/4h/8h » | chaque appui envoie son code (stateless) |
| `has_sound` | `switch` « Son » | `turn_on/off` envoie `sound_toggle` si état supposé ≠ cible |

**Couplage kelvin (seul couplage modélisé)** : le matériel avance la couleur
d'un cran à chaque **allumage** de la lampe. Donc `light.turn_on` incrémente la
position couleur (`pos += 1 mod 3`). Comme `light` et `select` sont dans le même
composant, on partage la position via `hass.data[DOMAIN][entry_id]` et un signal
**dispatcher** (`async_dispatcher_send`) que le `select` écoute pour se
rafraîchir. Pattern HA standard.

Pour le ventilo de l'utilisateur (tout coché) : 1 `fan` (vitesse+direction+preset),
1 `light`, 1 `select`, 4 `button`, 1 `switch`.

## Config flow

**Étape 1** — schéma :
- `esphome_device` : **`SelectSelector`** rempli avec les passerelles détectées
  (services esphome `*_transmit_rf_fan`), au lieu du champ `str` libre.
- `fan_name`, `speed_count`, `has_light` (existant).
- `has_direction`, `has_natural_preset`, `has_color_temp`, `has_timers`,
  `has_sound` (nouveaux booléens).

**Actions gated** (`actions.py`, fonctions pures) — `split_actions()` s'étend :
- toujours : `fan_off`, `fan_speed_1..N` (requis) ; `fan_on` (optionnel)
- si `has_light` : `light_on`/`off`/`toggle` (au moins un — déjà en place)
- si `has_direction` : `fan_reverse` (requis)
- si `has_natural_preset` : `fan_natural` (requis)
- si `has_color_temp` : `light_kelvin` (requis)
- si `has_timers` : `timer_1h`/`2h`/`4h`/`8h` (requis)
- si `has_sound` : `sound_toggle` (requis)

Règle : cocher une capacité ⇒ son/ses code(s) requis. `validate_codes()` étendu.

**Learn & manuel** : inchangés dans leur structure — les deux consomment déjà la
liste de `split_actions()`. Ils héritent automatiquement des nouvelles actions.

**Options flow** : reste limité à `repeat_count` (reconfig des capacités = hors
scope v1 ; pour changer, supprimer/recréer l'entrée).

## Fichiers

- `const.py` : `CONF_HAS_*` + `ACTION_FAN_REVERSE`, `ACTION_FAN_NATURAL`,
  `ACTION_LIGHT_KELVIN`, `ACTION_TIMER_1H/2H/4H/8H`, `ACTION_SOUND_TOGGLE` +
  labels/positions kelvin.
- `actions.py` : `split_actions`/`validate_codes` étendus (purs, testables).
- `config_flow.py` : schéma étape 1 (dropdown + booléens), `_create_entry`
  stocke les flags.
- `entity.py` : helper d'envoi de N appuis (cycle) réutilisable.
- `fan.py` : features DIRECTION + PRESET_MODE conditionnelles + sync RX.
- **Nouveaux** : `select.py`, `button.py`, `switch.py`.
- `__init__.py` : `PLATFORMS = [FAN, LIGHT, SELECT, BUTTON, SWITCH]` (chaque
  plateforme `return` si capacité absente) ; init de `hass.data[DOMAIN][entry_id]`
  (position kelvin partagée).
- `strings.json` + `translations/{en,fr}.json` : labels capacités, actions,
  noms d'entités.

## Tests

- **Purs** (`test_actions.py`) : `split_actions`/`validate_codes` avec les
  nouvelles capacités — exécutables localement.
- **Config flow** (`test_config_flow.py`, phcc/CI) : cas « toutes capacités » →
  liste d'actions correcte + création d'entrée. (Non exécutable sur le poste
  Windows — cf. note du fichier ; CI Linux.)
- Comportement entités : testable en phcc (CI).

## Hors scope

- Reconfiguration des capacités via l'options flow (v1 : supprimer/recréer).
- Modélisation d'un couplage kelvin plus fin que « allumage = +1 cran ».
- Support des rolling codes / accusé de réception (limites générales connues).
