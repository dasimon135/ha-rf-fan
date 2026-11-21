"""A fan declared, exported and replaced from one pasted document (#58)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

import yaml
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.esphome_rf_fan.const import DOMAIN

DEVICE = "esp32-test"

FULL = """\
format: 1
name: Bedroom
speed_count: 3
light_control: toggle
has_fan_on: false
direction_control: toggle
timer_hours: [2]
extra_count: 1
extra_names:
  extra_1: Ionisation
repeat_count: 4
codes:
  fan_off: c_off
  fan_speed_1: c1
  fan_speed_2: c2
  fan_speed_3: c3
  light_toggle: c_tog
  fan_reverse: c_rev
  timer_2h: c_t2
  extra_1: c_x1
"""


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _paste_step(hass: HomeAssistant):
    hass.services.async_register("esphome", "esp32_test_transmit_rf_fan", lambda call: None)
    await hass.async_block_till_done()
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"], {"next_step_id": "paste_declaration"}
    )
    assert result["step_id"] == "paste_declaration"
    return flow, result


async def _paste(hass: HomeAssistant, text: str, name: str = ""):
    flow, result = await _paste_step(hass)
    result = await flow.async_configure(
        result["flow_id"],
        {"esphome_device": DEVICE, "fan_name": name, "declaration": text},
    )
    return flow, result


def _entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Recon",
        unique_id="esp32_test_recon",
        data={
            "esphome_device": DEVICE,
            "gateway_service": "esp32_test",
            "fan_name": "Recon",
            "speed_count": 3,
            "light_control": "toggle",
            "has_fan_on": False,
            "direction_control": "none",
            "natural_control": "none",
            "color_control": "none",
            "light_level": "none",
            "timer_hours": [],
            "has_timer_off": False,
            "has_sound": False,
            "has_light": True,
            "repeat_count": 2,
            "codes": {
                "fan_off": "c_off",
                "fan_speed_1": "c1",
                "fan_speed_2": "c2",
                "fan_speed_3": "c3",
                "light_toggle": "c_tog",
            },
        },
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


async def test_adding_a_fan_opens_on_a_menu(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["menu_options"] == ["declare", "paste_declaration"]


async def test_a_complete_declaration_creates_the_fan(hass: HomeAssistant) -> None:
    _flow, result = await _paste(hass, FULL)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bedroom"
    data = result["data"]
    assert data["esphome_device"] == DEVICE
    assert data["gateway_service"] == "esp32_test"
    assert data["fan_name"] == "Bedroom"
    assert data["speed_count"] == 3
    assert data["direction_control"] == "toggle"
    assert data["timer_hours"] == (2,)
    assert data["extra_count"] == 1
    assert data["extra_names"] == {"extra_1": "Ionisation"}
    assert data["repeat_count"] == 4
    assert data["codes"]["fan_reverse"] == "c_rev"
    assert data["codes"]["extra_1"] == "c_x1"
    # The form's defaults fill what the file leaves out.
    assert data["natural_control"] == "none"
    assert data["has_sound"] is False


async def test_the_name_typed_on_the_form_wins_over_the_file(hass: HomeAssistant) -> None:
    _flow, result = await _paste(hass, FULL, name="Office")
    assert result["title"] == "Office"
    assert result["data"]["fan_name"] == "Office"


async def test_a_declaration_without_any_name_asks_for_one(hass: HomeAssistant) -> None:
    _flow, result = await _paste(hass, FULL.replace("name: Bedroom\n", ""))
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"fan_name": "required"}


async def test_missing_codes_are_asked_for_and_only_those(hass: HomeAssistant) -> None:
    flow, result = await _paste(
        hass, FULL.replace("  fan_reverse: c_rev\n", "").replace("  timer_2h: c_t2\n", "")
    )
    assert result["step_id"] == "method"

    result = await flow.async_configure(result["flow_id"], {"method": "manual"})
    assert result["step_id"] == "codes"
    asked = {str(field) for field in result["data_schema"].schema}
    assert asked == {"fan_reverse", "timer_2h"}

    result = await flow.async_configure(
        result["flow_id"], {"fan_reverse": "c_rev", "timer_2h": "c_t2"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["codes"] == yaml.safe_load(FULL)["codes"]


async def test_a_code_asked_for_must_not_reuse_one_from_the_file(
    hass: HomeAssistant,
) -> None:
    flow, result = await _paste(hass, FULL.replace("  fan_reverse: c_rev\n", ""))
    result = await flow.async_configure(result["flow_id"], {"method": "manual"})
    result = await flow.async_configure(result["flow_id"], {"fan_reverse": "c1"})
    assert result["errors"] == {"fan_reverse": "duplicate_code"}


@pytest.mark.parametrize(
    ("text", "error", "key"),
    [
        ("format: [1", "declaration_unreadable", ""),
        ("speed_count: 3", "declaration_format", "format"),
        ("format: 1\nname: x\nspeed_cout: 3\n", "declaration_unknown_key", "speed_cout"),
        ("format: 1\nname: x\nspeed_count: 40\n", "declaration_bad_value", "speed_count"),
        (
            "format: 1\nname: x\nlight_control: dimmer\n",
            "declaration_bad_value",
            "light_control",
        ),
        (
            "format: 1\nname: x\ncodes:\n  fan_reverse: r\n",
            "declaration_unknown_action",
            "codes.fan_reverse",
        ),
        (
            "format: 1\nname: x\ncodes:\n  fan_off: '7'\n  fan_speed_1: '7'\n",
            "declaration_duplicate_code",
            "codes.fan_speed_1",
        ),
        (
            "format: 1\nname: x\nextra_names:\n  extra_1: a\n",
            "declaration_unknown_action",
            "extra_names.extra_1",
        ),
        (
            "format: 1\nname: x\ncodes:\n  fan_off: 0123\n",
            "declaration_code_not_text",
            "codes.fan_off",
        ),
        (
            "format: 1\nname: x\nrepeat_count: 20\n",
            "declaration_bad_value",
            "repeat_count",
        ),
        (
            "format: 1\nname: x\nnatural_control: toggle\nnatural_levels: 3\n",
            "natural_levels_need_dedicated",
            "",
        ),
    ],
)
async def test_a_declaration_that_cannot_be_used_says_why(
    hass: HomeAssistant, text: str, error: str, key: str
) -> None:
    _flow, result = await _paste(hass, text)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "paste_declaration"
    assert result["errors"] == {"declaration": error}
    assert result["description_placeholders"]["key"] == key


async def test_a_name_already_used_on_the_gateway_is_refused(hass: HomeAssistant) -> None:
    _entry(hass)
    _flow, result = await _paste(hass, FULL, name="Recon")
    assert result["errors"] == {"fan_name": "name_already_used"}


async def test_reconfigure_offers_export_and_replace(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert set(result["menu_options"]) == {
        "reconfigure_codes",
        "reconfigure_capabilities",
        "reconfigure_export",
        "reconfigure_paste",
    }


async def _export(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_export"}
    )
    assert result["step_id"] == "reconfigure_export"
    block = result["description_placeholders"]["declaration"]
    result = await flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "declaration_exported"
    return block.removeprefix("```yaml\n").removesuffix("```")


async def test_export_changes_nothing_and_carries_no_gateway(hass: HomeAssistant) -> None:
    entry = _entry(hass, repeat_count=5)
    before = dict(entry.data)
    text = await _export(hass, entry)

    document = yaml.safe_load(text)
    assert document["format"] == 1
    assert document["name"] == "Recon"
    # The repeat count in force is the options one.
    assert document["repeat_count"] == 5
    assert document["codes"] == before["codes"]
    assert "esp32" not in text
    assert dict(entry.data) == before


async def test_an_exported_declaration_recreates_the_same_fan(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    text = await _export(hass, entry)

    _flow, result = await _paste(hass, text, name="Copy")
    assert result["type"] == FlowResultType.CREATE_ENTRY
    created = dict(result["data"])
    original = dict(entry.data)
    del created["fan_name"], original["fan_name"]
    created["timer_hours"] = list(created["timer_hours"])
    original["timer_hours"] = list(original["timer_hours"])
    assert {key: created[key] for key in original} == original
    # What the original does not store, the copy states with the value the
    # original is already read with.
    assert set(created) - set(original) <= {
        "color_temp_steps",
        "light_level_steps",
        "natural_levels",
        "extra_count",
        "extra_names",
    }


async def test_replacing_keeps_the_name_and_gateway(hass: HomeAssistant) -> None:
    entry = _entry(hass, repeat_count=5)
    flow = hass.config_entries.flow
    with patch("custom_components.esphome_rf_fan.async_setup_entry", return_value=True):
        result = await flow.async_init(
            DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        result = await flow.async_configure(
            result["flow_id"], {"next_step_id": "reconfigure_paste"}
        )
        assert result["step_id"] == "reconfigure_paste"
        result = await flow.async_configure(result["flow_id"], {"declaration": FULL})
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "Recon"
    assert entry.data["fan_name"] == "Recon"
    assert entry.data["esphome_device"] == DEVICE
    assert entry.data["direction_control"] == "toggle"
    # Replaced, not merged.
    assert entry.data["codes"] == yaml.safe_load(FULL)["codes"]
    # The file's repeat count is the one in force afterwards.
    assert entry.data["repeat_count"] == 4
    assert entry.options["repeat_count"] == 4


async def test_replacing_asks_for_what_the_file_lacks(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    flow = hass.config_entries.flow
    with patch("custom_components.esphome_rf_fan.async_setup_entry", return_value=True):
        result = await flow.async_init(
            DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        result = await flow.async_configure(
            result["flow_id"], {"next_step_id": "reconfigure_paste"}
        )
        result = await flow.async_configure(
            result["flow_id"], {"declaration": FULL.replace("  timer_2h: c_t2\n", "")}
        )
        assert result["step_id"] == "method"
        result = await flow.async_configure(result["flow_id"], {"method": "manual"})
        result = await flow.async_configure(result["flow_id"], {"timer_2h": "c_t2"})
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data["codes"]["timer_2h"] == "c_t2"


async def test_a_refused_replacement_changes_nothing(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    before = dict(entry.data)
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_paste"}
    )
    result = await flow.async_configure(
        result["flow_id"], {"declaration": "format: 1\nspeed_count: 40\n"}
    )
    assert result["errors"] == {"declaration": "declaration_bad_value"}
    assert dict(entry.data) == before
