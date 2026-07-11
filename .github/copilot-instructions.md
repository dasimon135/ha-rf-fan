# ha-rf-fan — Copilot Instructions

## Context

HACS integration for generic RF433 fans controlled by a remote.

## Stack

- Python 3.12+
- Home Assistant custom component (`custom_components/rf_fan/`)
- ESPHome for RF sniffing and transmission

## Conventions

- Language: English
- Python: snake_case, full type annotations
- 1 config entry = 1 fan
- State assumed by default as long as there is no reliable hardware feedback

## Architecture

- `config_flow.py`: manual mode + guided learning
- `fan.py`: fan entity with discrete speeds
- `light.py`: optional light if integrated into the fan
- `entity.py`: RF transmission via the ESPHome service and per-gateway event filtering

## Learning mode

- ESPHome publishes the `esphome.rf_fan_received` event
- The event must contain at least `code`
- Adding `device` is recommended for filtering when multiple RF gateways coexist
