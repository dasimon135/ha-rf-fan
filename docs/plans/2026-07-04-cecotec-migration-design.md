# ha-rf-fan — Finaliser l'intégration et migrer le Cecotec (design)

*Date : 2026-07-04*

## Objectif

Terminer l'intégration Home Assistant `rf_fan` (repo `ha-rf-fan`) et y migrer le
**ventilateur Cecotec du salon**, aujourd'hui piloté via des boutons ESPHome +
helpers + un flow Node-RED (dead-reckoning). Cible : une vraie entité `fan`
(slider 1-6) + une entité `light` (on/off), configurées via l'UI.

## Résultats du spike (2026-07-04)

Testé en direct sur le device ESPHome `esp32-ventilateur-cecotec` via le MCP HA.

| Question | Résultat |
|----------|----------|
| **Q1 — RX rc_switch** : la télécommande physique produit-elle un code décodé stable ? | ❌ Les events `esphome.rf_fan_received` sortent **uniquement en `p=raw`**, jamais en rc_switch. Le décodeur rc_switch intégré d'ESPHome ne décode pas le Cecotec (sync ~5820 µs, hors protocoles 1-8). |
| **Q2 — TX via le service** `transmit_rf_fan` avec un code `raw:` | ✅ Le ventilo réagit ; Vitesse 1 et Vitesse 6 sont nettement distinctes. |

## Décisions de conception

1. **TX en `raw:`** (format éprouvé). Les codes raw existent déjà dans
   `esphome-configs/esp32-ventilateur-cecotec.yaml` → pré-remplissage **manuel**,
   pas besoin du mode apprentissage.
2. **Lampe en on/off simple** (bouton toggle unique). La gestion kelvin/couleur
   est **hors scope** pour cette version.
3. **`assumed_state`, pas de synchro depuis la télécommande physique.** Le raw ne
   se matche pas en exact (jitter). L'état est supposé ; si la télécommande
   physique est utilisée, HA peut se désynchroniser jusqu'à la prochaine commande
   HA. Acceptable : le pilotage courant passe par les interrupteurs muraux (→ HA).

## Modifications de l'intégration `rf_fan`

### 1. config_flow — lampe toggle-only
Aujourd'hui `custom_components/rf_fan/config_flow.py` rend `light_on` **et**
`light_off` obligatoires. Le Cecotec n'a qu'un bouton toggle. Assouplir :
accepter **soit** `light_on`+`light_off`, **soit** `light_toggle` seul.
Le runtime est déjà OK : `light.py` retombe sur le toggle quand on/off n'est pas
mappé, et avec `assumed_state` un `turn_on` n'est émis que si HA croit la lampe
éteinte → comportement toggle correct.

### 2. Mapping des codes Cecotec (actions → code `raw:`)
Pré-remplis en mode manuel depuis le YAML ESPHome existant :

| Action rf_fan | Bouton Cecotec |
|---------------|----------------|
| `fan_off` | Stop |
| `fan_speed_1` … `fan_speed_6` | Vitesse 1 … 6 |
| `light_toggle` | Lumière |
| *(non mappé)* | Kelvin — hors scope v1 |

`speed_count = 6`, `has_light = true`, `esphome_device = esp32-ventilateur-cecotec`.

### 3. Écouteur d'events RX
Inoffensif de le laisser (il fait un match exact qui ne matchera jamais le raw).
Aucune modification nécessaire pour cette version.

## Migration Home Assistant

1. **Déployer** `custom_components/rf_fan/` dans la config HA (HACS repo perso ou
   copie), redémarrer HA.
2. **Ajouter l'intégration** via l'UI (config flow) avec les codes ci-dessus.
3. **Remapper** les déclencheurs des interrupteurs muraux Zigbee (flow Node-RED
   `94ba22cd9798a2a7`) vers les nouvelles entités `fan`/`light`.
4. **Retirer** l'ancien setup Cecotec : boutons ESPHome, helpers dead-reckoning,
   branche de décodage RF dans Node-RED. (Optionnel, après validation.)

## Hors scope / plus tard

- **Kelvin / température de couleur** de la lampe (dead-reckoning, comme
  aujourd'hui) → à réintégrer ensuite, éventuellement via `color_temp` dans
  `light.py`.
- **Synchro depuis la télécommande physique** : ajouter une lambda `on_raw` dans
  le firmware qui décode la trame en ~30 bits stables et émet un code propre →
  match exact possible, sans Node-RED. Nécessite une petite évolution de
  l'intégration (code TX `raw:` ≠ code de match `bits`).

## Risques

- Le déploiement du custom_component dépend de l'accès à la config HA
  (`\\homeassistant.local\config` / `H:`).
- Les codes raw pré-remplis sont de longues chaînes ; vérifier qu'ils passent
  bien dans les champs du config flow (str, pas de limite bloquante attendue).
