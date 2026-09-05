"""Sleep-timer durations are declared one by one, and can be cancelled (#59).

`has_timers` was a single boolean meaning "all four of 1/2/4/8 h", so @Ltek's
remote — whose timer key walks off/2/4/8 — could not declare timers at all. The
capability is now the list of durations the remote actually has, plus an optional
dedicated cancel key.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.rf_fan.const import ACTION_TIMER_OFF
from tests.ha_helpers import actions_sent, id_by_unique_suffix, setup_full

CANCEL_CODE = {ACTION_TIMER_OFF: "c_toff"}


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


def _timer_suffixes(hass: HomeAssistant, entry) -> set[str]:
    """The timer-related unique-id suffixes this entry actually created."""
    registry = er.async_get(hass)
    return {
        e.unique_id[len(entry.entry_id) + 1 :]
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if "timer" in e.unique_id
    }


async def test_only_the_declared_durations_become_buttons(
    hass: HomeAssistant,
) -> None:
    """@Ltek's shape: off/2/4/8, so three buttons and no 1 h."""
    entry, _calls = await setup_full(hass, extra_data={"timer_hours": ["2", "4", "8"]})

    suffixes = _timer_suffixes(hass, entry)
    assert "timer_1h" not in suffixes
    assert {"timer_2h", "timer_4h", "timer_8h"} <= suffixes
    # The sensor still exists: one timer key is enough for a switch-off time.
    assert "sleep_timer" in suffixes


async def test_no_durations_means_no_timer_entities_at_all(
    hass: HomeAssistant,
) -> None:
    entry, _calls = await setup_full(hass, extra_data={"timer_hours": []})
    assert _timer_suffixes(hass, entry) == set()


async def test_the_cancel_button_exists_only_when_declared(
    hass: HomeAssistant,
) -> None:
    entry, _calls = await setup_full(hass)
    assert "timer_off" not in _timer_suffixes(hass, entry)


async def test_the_cancel_button_emits_and_clears_the_assumed_switch_off(
    hass: HomeAssistant,
) -> None:
    """Unlike the calibration buttons this one DOES emit.

    The fan is holding a countdown of its own, and only a frame calls it off.
    """
    entry, calls = await setup_full(
        hass, extra_codes=CANCEL_CODE, extra_data={"has_timer_off": True}
    )
    two_hours = id_by_unique_suffix(hass, entry, "button", "timer_2h")
    cancel = id_by_unique_suffix(hass, entry, "button", "timer_off")
    sensor = id_by_unique_suffix(hass, entry, "sensor", "sleep_timer")

    await hass.services.async_call(
        "button", "press", {"entity_id": two_hours}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state not in ("unknown", "unavailable")

    calls.clear()
    await hass.services.async_call(
        "button", "press", {"entity_id": cancel}, blocking=True
    )
    await hass.async_block_till_done()

    assert actions_sent(calls) == [ACTION_TIMER_OFF]
    assert hass.states.get(sensor).state == "unknown"


async def test_cancelling_without_a_code_keeps_the_countdown(
    hass: HomeAssistant,
) -> None:
    """Nothing on the air means nothing was cancelled, so the estimate must stand.

    The same rule the timer buttons follow in reverse: they only claim a
    switch-off time once their code is sent, and this only drops one once its own
    code is sent. Claiming otherwise would announce an extinction that never comes
    — or hide one that does.
    """
    entry, calls = await setup_full(hass, extra_data={"has_timer_off": True})
    two_hours = id_by_unique_suffix(hass, entry, "button", "timer_2h")
    cancel = id_by_unique_suffix(hass, entry, "button", "timer_off")
    sensor = id_by_unique_suffix(hass, entry, "sensor", "sleep_timer")

    await hass.services.async_call(
        "button", "press", {"entity_id": two_hours}, blocking=True
    )
    await hass.async_block_till_done()
    running = hass.states.get(sensor).state

    calls.clear()
    await hass.services.async_call(
        "button", "press", {"entity_id": cancel}, blocking=True
    )
    await hass.async_block_till_done()

    assert actions_sent(calls) == []
    assert hass.states.get(sensor).state == running
