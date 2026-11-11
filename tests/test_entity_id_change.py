"""Renaming an entity_id: changed in place from Home Assistant 2026.11 on.

Home Assistant 2026.11 changes an entity_id in place instead of removing and
re-adding the entity. A custom entity class that defines `async_added_to_hass` or
`async_will_remove_from_hass` keeps the old remove-and-re-add path until 2027.11,
unless that class (or a subclass) also defines `async_entity_id_changed`.

Nothing here is keyed on the entity_id: the signals carry the config entry id and
the RF listener is on the bus. So every such class only has to declare the hook.

The first test mirrors `homeassistant.helpers.entity._entity_class_requires_readd`
(2026.11.1), so it runs on a harness that predates the hook.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity

from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import setup_full as _setup_full

PLATFORMS = ("button", "fan", "light", "select", "sensor", "switch")
ADD_REMOVE = (
    "async_prepare_to_add_to_hass",
    "async_added_to_hass",
    "async_will_remove_from_hass",
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


def _entity_classes() -> list[type[Entity]]:
    classes: list[type[Entity]] = []
    for platform in PLATFORMS:
        module = importlib.import_module(f"custom_components.esphome_rf_fan.{platform}")
        classes.extend(
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, Entity) and cls.__module__ == module.__name__
        )
    return classes


def _requires_readd(entity_class: type[Entity]) -> bool:
    mro = [c for c in entity_class.__mro__ if not c.__module__.startswith("homeassistant.")]
    owners = [c for c in mro if "async_entity_id_changed" in c.__dict__]
    return any(
        any(m in c.__dict__ for m in ADD_REMOVE)
        and not any(issubclass(owner, c) for owner in owners)
        for c in mro
    )


def test_every_entity_is_renamed_in_place() -> None:
    """No class of this integration falls back to remove-and-re-add."""
    classes = _entity_classes()
    assert len(classes) >= 12
    assert [c.__name__ for c in classes if _requires_readd(c)] == []


async def test_fan_follows_the_remote_after_a_rename(hass: HomeAssistant) -> None:
    """A renamed fan keeps its state and still runs services under the new id."""
    _entry, calls = await _setup_full(hass)
    fan_id = _one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 100}, blocking=True
    )
    er.async_get(hass).async_update_entity(fan_id, new_entity_id="fan.renamed_by_user")
    await hass.async_block_till_done()

    assert hass.states.get(fan_id) is None
    assert hass.states.get("fan.renamed_by_user").state == "on"
    sent = len(calls)
    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": "fan.renamed_by_user"}, blocking=True
    )
    assert len(calls) > sent
    assert hass.states.get("fan.renamed_by_user").state == "off"
