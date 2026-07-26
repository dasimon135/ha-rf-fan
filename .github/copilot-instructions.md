# ha-rf-fan — Copilot Instructions

## Context

HACS integration for generic RF433 fans controlled by a remote.

## Stack

- Python 3.14+ (Home Assistant 2026.5, the `hacs.json` target, requires it)
- Home Assistant custom component (`custom_components/rf_fan/`)
- ESPHome for RF sniffing and transmission
- A bundled Lovelace card in `custom_components/rf_fan/frontend/` (plain JS, no build)

## Conventions

- Language: English (except the `translations/*.json` locale files)
- Python: snake_case, full type annotations
- 1 config entry = 1 fan
- State assumed by default as long as there is no reliable hardware feedback
- The integration is protocol-agnostic: RF codes are **opaque strings**. Never parse or
  interpret them — decoding belongs in the ESPHome gateway.

## Architecture

- `config_flow.py`: manual mode + guided learning; reconfigure opens on a menu
  (relearn codes only / re-declare capabilities)
- `entity.py`: RF transmission via the ESPHome service, per-gateway event filtering,
  and per-code echo suppression
- `data.py`: `RfFanRuntimeData`, the assumed state shared by the platforms of an entry
- `fan.py` / `light.py` / `select.py` / `switch.py` / `sensor.py` / `button.py`: platforms
- `actions.py`: pure logic (required-action lists, code validation, expected unique ids),
  importable without Home Assistant so it can be tested anywhere

## Learning mode

- ESPHome publishes the `esphome.rf_fan_received` event
- The event must contain at least `code`
- Adding `device` is recommended for filtering when multiple RF gateways coexist
- A code already assigned to another action is refused: the received-frame lookup maps
  codes back to actions, so a duplicate would make one of them unreachable

## Tests

- `tests/test_actions.py` is pure and runs anywhere
- Everything else needs `pytest-homeassistant-custom-component`; those modules
  `importorskip` cleanly. Home Assistant's runner imports the POSIX-only `fcntl`, so on
  Windows use `scripts/run-tests.ps1` (Docker, same image as CI)
- Card tests: `node --test "tests/frontend/*.test.mjs"` — no dependency, a DOM stub
- Any behaviour change needs a test that failed before the fix
