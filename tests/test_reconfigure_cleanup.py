"""Entity-registry cleanup after a reconfiguration (requires a HA environment).

Turning a capability off stops the platform from creating its entity, but the
entity registry keeps the old row: without an explicit cleanup the entity lingers
forever as `unavailable` in the UI with no way to get rid of it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.ha_helpers import setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


def _unique_ids(hass: HomeAssistant, entry_id: str) -> set[str]:
    registry = er.async_get(hass)
    return {e.unique_id for e in er.async_entries_for_config_entry(registry, entry_id)}


async def test_disabling_capabilities_removes_their_entities(hass: HomeAssistant) -> None:
    """Sound and timers turned off → their registry rows must be gone."""
    entry, _calls = await setup_full(hass)
    before = _unique_ids(hass, entry.entry_id)
    assert f"{entry.entry_id}_sound" in before
    assert f"{entry.entry_id}_timer_1h" in before
    assert f"{entry.entry_id}_sleep_timer" in before

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "has_sound": False, "has_timers": False}
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    after = _unique_ids(hass, entry.entry_id)
    assert f"{entry.entry_id}_sound" not in after
    assert not any("_timer" in unique_id for unique_id in after)
    # The capabilities left enabled are untouched.
    assert f"{entry.entry_id}_fan" in after
    assert f"{entry.entry_id}_light" in after
    assert f"{entry.entry_id}_color_temp" in after


async def test_enabled_capabilities_survive_a_reload(hass: HomeAssistant) -> None:
    """A plain reload must not remove anything."""
    entry, _calls = await setup_full(hass)
    before = _unique_ids(hass, entry.entry_id)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert _unique_ids(hass, entry.entry_id) == before
