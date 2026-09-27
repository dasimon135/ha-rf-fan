"""One request reaching the lamp twice presses the toggle key once.

A `light.turn_on` aimed at an area reaches the lamp directly AND through any light
group of that area, which relays the same call to its members (Home Assistant's
own group, and Magic Areas' groups, both forward it under the caller's context).
On a lamp whose only power key is `light_toggle`, the second arrival flipped the
lamp back: Home Assistant believed it on, the lamp was dark.

The lamp still presses its key for every request it is given (#45: a press towards
the state already believed is how a person resynchronises). What it no longer does
is press twice for ONE request, and one request is one `Context`.

Every test asserts the complete list of frames.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import Context, HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.ha_helpers import actions_sent as _actions_sent
from tests.ha_helpers import id_by_unique_suffix as _id_by
from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import setup_on_off as _setup_on_off
from tests.ha_helpers import setup_relative as _setup_relative


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _power(
    hass: HomeAssistant, light_id: str, service: str, context: Context | None = None
) -> None:
    await hass.services.async_call(
        "light", service, {"entity_id": light_id}, blocking=True, context=context
    )
    await hass.async_block_till_done()


async def _group_of(hass: HomeAssistant, light_id: str) -> str:
    """A native light group holding the lamp, as an area's group would."""
    entry = MockConfigEntry(
        domain="group",
        title="Salon lights",
        options={
            "group_type": "light",
            "name": "Salon lights",
            "entities": [light_id],
            "hide_members": False,
            "all": False,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    group_id = next(i for i in hass.states.async_entity_ids("light") if i != light_id)
    return group_id


@pytest.mark.parametrize(
    ("start", "service", "end"), [("turn_off", "turn_on", "on"), ("turn_on", "turn_off", "off")]
)
async def test_a_call_reaching_the_lamp_and_its_group_presses_once(
    hass: HomeAssistant, start: str, service: str, end: str
) -> None:
    """The reported case: one call targets the lamp and a group relaying to it.

    Home Assistant runs the two entity calls concurrently, so whichever arrives
    first, the other must stay silent.
    """
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    group_id = await _group_of(hass, light_id)
    await _power(hass, light_id, start)
    calls.clear()

    await _power(hass, [light_id, group_id], service)

    assert _actions_sent(calls) == ["light_toggle"]
    assert hass.states.get(light_id).state == end


@pytest.mark.parametrize("order", ["direct_first", "relay_first"])
async def test_the_order_of_arrival_does_not_matter(hass: HomeAssistant, order: str) -> None:
    """Two calls under one context, sequential, in either order: one press."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    group_id = await _group_of(hass, light_id)
    await _power(hass, light_id, "turn_off")
    calls.clear()

    context = Context()
    targets = [light_id, group_id] if order == "direct_first" else [group_id, light_id]
    for target in targets:
        await _power(hass, target, "turn_on", context)

    assert _actions_sent(calls) == ["light_toggle"]
    assert hass.states.get(light_id).state == "on"


async def test_two_concurrent_calls_under_one_context_press_once(hass: HomeAssistant) -> None:
    """The claim is taken before the first press goes on the air, not after."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_off")
    calls.clear()

    context = Context()
    await asyncio.gather(
        _power(hass, light_id, "turn_on", context), _power(hass, light_id, "turn_on", context)
    )

    assert _actions_sent(calls) == ["light_toggle"]
    assert hass.states.get(light_id).state == "on"


async def test_separate_requests_still_press_every_time(hass: HomeAssistant) -> None:
    """The #45 gesture: a second, separate `turn_on` is a request of its own."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_on", Context())
    await _power(hass, light_id, "turn_on", Context())

    assert _actions_sent(calls) == ["light_toggle", "light_toggle"]


async def test_one_script_run_can_still_blink_the_lamp(hass: HomeAssistant) -> None:
    """A script runs every step under one context: on, off, on is three presses.

    Only a repeat of the very press just made under the same context is dropped.
    """
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_off")
    calls.clear()

    context = Context()
    for service in ("turn_on", "turn_off", "turn_on"):
        await _power(hass, light_id, service, context)

    assert _actions_sent(calls) == ["light_toggle"] * 3
    assert hass.states.get(light_id).state == "on"


async def test_toggle_presses_every_time_under_one_context(hass: HomeAssistant) -> None:
    """`light.toggle` flips the belief each time, so each one is a real press."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_off")
    calls.clear()

    context = Context()
    await _power(hass, light_id, "toggle", context)
    await _power(hass, light_id, "toggle", context)

    assert _actions_sent(calls) == ["light_toggle", "light_toggle"]
    assert hass.states.get(light_id).state == "off"


async def test_an_absolute_code_is_re_sent_under_the_same_context(hass: HomeAssistant) -> None:
    """`light_on` twice lands the lamp on twice: nothing to protect, nothing withheld."""
    _entry, calls = await _setup_on_off(hass)
    light_id = _one_id(hass, "light")
    group_id = await _group_of(hass, light_id)
    calls.clear()

    await _power(hass, [light_id, group_id], "turn_on")

    assert _actions_sent(calls) == ["light_on", "light_on"]


async def test_a_declared_state_lets_the_same_request_press_again(hass: HomeAssistant) -> None:
    """The select moved the belief without a press: the next request is not a repeat.

    A script that turns the lamp on, waits for someone to declare it off, and turns
    it on again runs under one context; its second press is meant.
    """
    entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    select_id = _id_by(hass, entry, "select", "_light_state")
    await _power(hass, light_id, "turn_off")
    calls.clear()

    context = Context()
    await _power(hass, light_id, "turn_on", context)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "off"}, blocking=True
    )
    await hass.async_block_till_done()
    await _power(hass, light_id, "turn_on", context)

    assert _actions_sent(calls) == ["light_toggle", "light_toggle"]
    assert hass.states.get(light_id).state == "on"
