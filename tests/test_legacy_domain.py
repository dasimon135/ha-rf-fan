"""Fans set up under the old `rf_fan` domain come over to `esphome_rf_fan`.

The domain was renamed for the default HACS store (hacs/default#10711): it clashed
with clevrdavid/rf_fan. A config entry cannot change domain, so each old entry is
copied and its registry rows re-pointed. The promise to the user is that nothing is
relearned and no automation breaks: same codes, same options, same entity_id, same
device.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.esphome_rf_fan import CARD_URL, LEGACY_CARD_URL
from custom_components.esphome_rf_fan.const import DOMAIN, LEGACY_DOMAIN
from custom_components.esphome_rf_fan.legacy import is_legacy_package, remove_legacy_package
from tests.ha_helpers import CODES, DEVICE, full_entry, register_stub


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


@pytest.fixture(autouse=True)
def _old_package_gone():
    """By default the old folder is already deleted, as after a restart."""
    with patch(
        "custom_components.esphome_rf_fan.legacy.async_legacy_installed",
        return_value=False,
    ):
        yield


_LEGACY_ACTIONS = ("fan_off", "fan_speed_1", "fan_speed_2", "fan_speed_3", "light_toggle")


def _legacy_entry(
    hass: HomeAssistant,
    title: str = "Salon",
    *,
    version: int = 6,
    minor_version: int = 2,
    data: dict | None = None,
) -> MockConfigEntry:
    """An entry the old `rf_fan` code created, with the registry rows it left."""
    entry = MockConfigEntry(
        domain=LEGACY_DOMAIN,
        title=title,
        version=version,
        minor_version=minor_version,
        unique_id=f"{DEVICE}_{title.lower()}",
        data=data
        or {
            "esphome_device": DEVICE,
            "gateway_service": DEVICE.replace("-", "_"),
            "fan_name": title,
            "speed_count": 3,
            "light_control": "toggle",
            "has_fan_on": False,
            "direction_control": "none",
            "natural_control": "none",
            "natural_levels": 0,
            "color_control": "none",
            "light_level": "none",
            "timer_hours": [],
            "has_timer_off": False,
            "has_sound": False,
            "has_light": True,
            "repeat_count": 3,
            "codes": {key: CODES[key] for key in _LEGACY_ACTIONS},
        },
        options={"disable_card": False},
    )
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(LEGACY_DOMAIN, entry.entry_id)},
        name=title,
    )
    dr.async_get(hass).async_update_device(device.id, name_by_user=f"My {title}")
    registry = er.async_get(hass)
    for platform, suffix in (("fan", "fan"), ("light", "light")):
        registry.async_get_or_create(
            platform,
            LEGACY_DOMAIN,
            f"{entry.entry_id}_{suffix}",
            config_entry=entry,
            device_id=device.id,
            suggested_object_id=title.lower(),
        )
    return entry


async def _start(hass: HomeAssistant) -> None:
    """Set the integration up, as adding a first entry does."""
    register_stub(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def test_an_old_entry_comes_over_with_its_codes_and_entity_ids(
    hass: HomeAssistant,
) -> None:
    old = _legacy_entry(hass)
    old_device = dr.async_get(hass).async_get_device({(LEGACY_DOMAIN, old.entry_id)})

    await _start(hass)

    assert hass.config_entries.async_get_entry(old.entry_id) is None, "old entry left behind"
    [new] = hass.config_entries.async_entries(DOMAIN)
    assert new.title == "Salon"
    assert new.unique_id == old.unique_id
    assert new.data["codes"] == old.data["codes"]
    assert "legacy_entry_id" not in new.data
    assert new.options == {"disable_card": False}

    # Same entity_id, now owned by the new entry: automations keep working.
    registry = er.async_get(hass)
    fan = registry.async_get("fan.salon")
    assert fan is not None
    assert fan.platform == DOMAIN
    assert fan.config_entry_id == new.entry_id
    assert fan.unique_id == f"{new.entry_id}_fan"
    assert hass.states.get("fan.salon") is not None
    assert "fan.salon_2" not in hass.states.async_entity_ids("fan")

    # Same device, with the name and area the user gave it.
    device = dr.async_get(hass).async_get_device({(DOMAIN, new.entry_id)})
    assert device is not None
    assert device.id == old_device.id
    assert device.name_by_user == "My Salon"
    assert device.config_entries == {new.entry_id}


async def test_every_old_entry_comes_over(hass: HomeAssistant) -> None:
    _legacy_entry(hass, "Salon")
    _legacy_entry(hass, "Chambre")

    await _start(hass)

    assert not hass.config_entries.async_entries(LEGACY_DOMAIN)
    assert sorted(e.title for e in hass.config_entries.async_entries(DOMAIN)) == [
        "Chambre",
        "Salon",
    ]
    assert hass.states.get("fan.salon") is not None
    assert hass.states.get("fan.chambre") is not None


async def test_an_entry_several_versions_behind_is_migrated_on_the_way(
    hass: HomeAssistant,
) -> None:
    """Created at the current version, it would never run the migrations it missed."""
    data = {
        "esphome_device": DEVICE,
        "gateway_service": DEVICE.replace("-", "_"),
        "fan_name": "Salon",
        "speed_count": 3,
        "light_control": "toggle",
        "has_fan_on": False,
        "direction_control": "none",
        "natural_control": "none",
        "color_control": "none",
        "light_level": "none",
        "has_timers": True,
        "has_sound": False,
        "has_light": True,
        "repeat_count": 3,
        "codes": dict(CODES),
    }
    _legacy_entry(hass, version=4, minor_version=1, data=data)

    await _start(hass)

    [new] = hass.config_entries.async_entries(DOMAIN)
    assert new.data["timer_hours"] == ["1", "2", "4", "8"]
    assert new.data["natural_levels"] == 0
    assert "has_timers" not in new.data


async def test_another_integrations_rf_fan_entries_are_left_alone(
    hass: HomeAssistant,
) -> None:
    """clevrdavid/rf_fan uses the same domain; its entries are not ours to take."""
    theirs = MockConfigEntry(domain=LEGACY_DOMAIN, title="Broadlink fan", data={"host": "x"})
    theirs.add_to_hass(hass)

    await _start(hass)

    assert hass.config_entries.async_get_entry(theirs.entry_id) is not None
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_nothing_is_taken_while_the_old_version_still_runs(
    hass: HomeAssistant,
) -> None:
    """HACS leaves the old folder in place: importing then gives a fan two masters."""
    old = _legacy_entry(hass)

    with patch(
        "custom_components.esphome_rf_fan.legacy.async_legacy_installed",
        return_value=True,
    ):
        await _start(hass)

    assert hass.config_entries.async_get_entry(old.entry_id) is not None
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_old_repairs_are_cleared(hass: HomeAssistant) -> None:
    old = _legacy_entry(hass)
    ir.async_create_issue(
        hass,
        LEGACY_DOMAIN,
        f"gateway_service_missing_{old.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="gateway_service_missing",
    )

    await _start(hass)

    assert (LEGACY_DOMAIN, f"gateway_service_missing_{old.entry_id}") not in (
        ir.async_get(hass).issues
    )


async def test_adding_the_integration_offers_to_bring_the_fans_over(
    hass: HomeAssistant,
) -> None:
    """The only way in on the first start: a domain with no entry is never set up."""
    register_stub(hass)
    _legacy_entry(hass, "Salon")
    _legacy_entry(hass, "Chambre")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "import_legacy"
    assert "Salon" in result["description_placeholders"]["fans"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not hass.config_entries.async_entries(LEGACY_DOMAIN)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2
    assert hass.states.get("fan.salon") is not None
    assert hass.states.get("fan.chambre") is not None


async def test_adding_the_integration_first_removes_a_running_old_version(
    hass: HomeAssistant,
) -> None:
    _legacy_entry(hass)

    with (
        patch(
            "custom_components.esphome_rf_fan.config_flow.async_legacy_installed",
            return_value=True,
        ),
        patch(
            "custom_components.esphome_rf_fan.config_flow.async_remove_legacy_installed",
            return_value=True,
        ) as remove,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "legacy_installed"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert remove.called
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "restart_to_finish"
    assert len(hass.config_entries.async_entries(LEGACY_DOMAIN)) == 1


async def test_without_old_fans_adding_the_integration_is_unchanged(
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"


async def test_the_card_resource_left_at_the_old_path_is_adopted(
    hass: HomeAssistant,
) -> None:
    """Left alone it points at a file nothing serves, reported on every dashboard."""
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_create_item(
        {"res_type": "module", "url": f"{LEGACY_CARD_URL}?v=1.11.0"}
    )
    register_stub(hass)
    entry = full_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    urls = [item["url"] for item in resources.async_items()]
    assert not [url for url in urls if url.startswith(LEGACY_CARD_URL)], urls
    assert len([url for url in urls if url.startswith(CARD_URL)]) == 1, urls


def _package(path: Path, manifest: dict) -> Path:
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (path / "__init__.py").write_text("", encoding="utf-8")
    return path


def test_the_old_package_is_recognised_and_removed(tmp_path: Path) -> None:
    path = _package(
        tmp_path / "rf_fan",
        {"domain": "rf_fan", "documentation": "https://github.com/dasimon135/ha-rf-fan"},
    )
    assert is_legacy_package(path)
    assert remove_legacy_package(path)
    assert not path.exists()


def test_clevrdavids_package_is_never_removed(tmp_path: Path) -> None:
    """Same folder name, somebody else's integration."""
    path = _package(
        tmp_path / "rf_fan",
        {"domain": "rf_fan", "documentation": "https://github.com/clevrdavid/rf_fan"},
    )
    assert not is_legacy_package(path)
    assert not remove_legacy_package(path)
    assert path.exists()


def test_a_missing_folder_is_not_the_old_package(tmp_path: Path) -> None:
    assert not is_legacy_package(tmp_path / "rf_fan")
