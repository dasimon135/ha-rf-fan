"""The shipped automation blueprint (requires a Home Assistant environment).

A blueprint is YAML nobody runs until a user imports it, so it is exactly the
kind of file that rots silently. These tests put it through Home Assistant's own
blueprint schema and then validate the substituted automation.
"""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import parse_yaml

BLUEPRINT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "blueprints"
    / "automation"
    / "rf_fan"
    / "fan_temperature_control.yaml"
)


@pytest.fixture(name="blueprint")
def _blueprint() -> Blueprint:
    """Parse the shipped blueprint through Home Assistant's schema."""
    return Blueprint(
        parse_yaml(BLUEPRINT_PATH.read_text(encoding="utf-8")),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )


def test_blueprint_matches_the_home_assistant_schema(blueprint: Blueprint) -> None:
    """Construction alone validates the `blueprint:` block and its inputs."""
    assert blueprint.domain == "automation"
    assert set(blueprint.inputs) == {
        "temperature_sensor",
        "fan",
        "temp_on",
        "temp_off",
        "speed",
    }


async def test_substituted_blueprint_is_a_valid_automation(
    hass: HomeAssistant, blueprint: Blueprint
) -> None:
    """Filling the inputs must yield an automation Home Assistant accepts.

    This is what actually runs on the user's machine; validating only the
    blueprint block would miss a malformed trigger or action.
    """
    from homeassistant.components.automation.config import async_validate_config_item

    inputs = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": "rf_fan/fan_temperature_control.yaml",
                "input": {
                    "temperature_sensor": "sensor.salon_temperature",
                    "fan": "fan.salon",
                    "temp_on": 26,
                    "temp_off": 24,
                    "speed": 66,
                },
            },
            "alias": "Ventilateur par température",
        },
    )

    config = inputs.async_substitute()
    validated = await async_validate_config_item(hass, "automation", config)
    assert validated is not None


def test_blueprint_uses_the_modern_trigger_and_action_keys() -> None:
    """`platform:`/`service:` are the pre-2024.10 spelling and are deprecated.

    Home Assistant still normalizes them, so nothing breaks — but a shipped
    blueprint is copied by users as a template, so it should teach the current
    syntax.
    """
    data = parse_yaml(BLUEPRINT_PATH.read_text(encoding="utf-8"))

    assert "triggers" in data, "use `triggers:` (plural), not `trigger:`"
    assert "actions" in data, "use `actions:` (plural), not `action:`"
    for trigger in data["triggers"]:
        assert "trigger" in trigger, "use `trigger:`, not `platform:`"
    raw = BLUEPRINT_PATH.read_text(encoding="utf-8")
    assert "\n    - service:" not in raw and "\n      - service:" not in raw, (
        "use `action:` instead of `service:`"
    )
