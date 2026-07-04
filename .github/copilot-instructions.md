# ha-rf-fan — Copilot Instructions

## Contexte

Intégration HACS pour ventilateurs RF433 génériques pilotés par télécommande.

## Stack

- Python 3.12+
- Home Assistant custom component (`custom_components/rf_fan/`)
- ESPHome pour sniff et transmission RF

## Conventions

- Langue : français
- Python : snake_case, annotations de type complètes
- 1 config entry = 1 ventilateur
- État supposé par défaut tant qu'il n'existe pas de retour matériel fiable

## Architecture

- `config_flow.py` : mode manuel + apprentissage guidé
- `fan.py` : entité fan à vitesses discrètes
- `light.py` : lumière optionnelle si intégrée au ventilateur
- `entity.py` : émission RF via service ESPHome et filtrage d'événements par passerelle

## Mode apprentissage

- ESPHome publie l'événement `esphome.rf_fan_received`
- L'événement doit contenir au minimum `code`
- Ajouter `device` est recommandé pour filtrer si plusieurs passerelles RF coexistent
