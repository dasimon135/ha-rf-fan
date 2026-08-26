"""A press is one press, however many times the remote repeats its frame (issue #24).

A remote does not send one frame per press: it sends the same frame four to six
times so that at least one gets through, and the gateway reports every one of them.
Before this, each copy was counted as a separate press — a toggle flickered and a
step key advanced the assumed position once per frame.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from custom_components.rf_fan.const import EVENT_RF_FAN_RECEIVED
from tests.ha_helpers import (
    DEVICE,
    fire_rf,
    id_by_unique_suffix,
    one_id,
    setup_full,
    setup_relative,
)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


BURST = 6
"""Frames in a burst, matching what @elmr91's remote puts on the air per press."""


def _rewind(entry, seconds: float = 10.0) -> None:
    """Age every tracked frame, as if the burst had ended `seconds` ago.

    The de-bounce window is measured on `hass.loop.time()`, which no test clock
    moves, so the state is aged instead of the clock advanced. Ageing the record is
    the same statement as waiting: what the next frame is compared against is how
    long ago the previous one arrived.
    """
    seen = entry.runtime_data.receive_seen
    for code in seen:
        seen[code] -= seconds


def _forget_our_own_transmissions(entry) -> None:
    """Close the anti-echo window opened by a command issued from Home Assistant.

    A toggle only follows the remote once its state is known, and the only way to
    establish that from a test is to command it — which arms the echo window over
    the very code the simulated remote press then uses. Clearing it is what makes
    the next frame a remote press rather than an echo of ours.
    """
    entry.runtime_data.echo_codes.clear()


async def _light_known_on(hass, entry) -> str:
    """Turn the light on through Home Assistant and hand back a clean slate."""
    light = one_id(hass, "light")
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light}, blocking=True
    )
    _forget_our_own_transmissions(entry)
    return light


async def test_a_repeated_frame_toggles_the_light_once(hass: HomeAssistant) -> None:
    """Six copies of the toggle frame are one press, not three on/off flips."""
    entry, _calls = await setup_full(hass)
    light = await _light_known_on(hass, entry)

    for _ in range(BURST):
        await fire_rf(hass, "c_lt")

    assert hass.states.get(light).state == "off"


async def test_a_repeated_frame_steps_the_brightness_once(hass: HomeAssistant) -> None:
    """The failure that made this visible: +1 press read as +6 steps."""
    entry, _calls = await setup_relative(hass)
    position = id_by_unique_suffix(hass, entry, "select", "_brightness_position")

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": position, "option": "1"},
        blocking=True,
    )

    for _ in range(BURST):
        await fire_rf(hass, "r_bu")

    assert hass.states.get(position).state == "2"


async def test_a_deliberate_second_press_still_counts(hass: HomeAssistant) -> None:
    """The window separates the frames of one burst, not two presses."""
    entry, _calls = await setup_full(hass)
    light = await _light_known_on(hass, entry)

    await fire_rf(hass, "c_lt")
    assert hass.states.get(light).state == "off"

    _rewind(entry)
    await fire_rf(hass, "c_lt")

    assert hass.states.get(light).state == "on"


async def test_another_button_pressed_during_a_burst_is_honoured(
    hass: HomeAssistant,
) -> None:
    """The window is per code: a different button is a different press.

    Both keys are pressed once, and their bursts overlap. Each has to be counted
    exactly once — the colour advances one position, and the direction ends up
    flipped rather than flipped back.
    """
    _entry, _calls = await setup_full(hass)
    fan = one_id(hass, "fan")
    color = one_id(hass, "select")

    for _ in range(BURST):
        await fire_rf(hass, "c_kel")
        await fire_rf(hass, "c_rev")

    assert hass.states.get(color).state == "Neutre"
    assert hass.states.get(fan).attributes["direction"] == "reverse"


async def test_every_entity_of_the_fan_agrees_on_the_first_frame(
    hass: HomeAssistant,
) -> None:
    """The verdict is shared, so no entity is starved by another's bookkeeping.

    Each platform of the entry listens to the same bus event. If the verdict were
    recomputed per listener, the first entity to see a frame would slide the window
    forward and every entity after it would conclude the frame was a repeat.

    Both directions are asserted here because which listener runs first is decided
    by platform setup order: `light_bright_up` is acted on by the light and
    `light_kelvin_up` by the colour select, so whichever of the two is registered
    second is the one that would have been starved.
    """
    entry, _calls = await setup_relative(hass)
    color = id_by_unique_suffix(hass, entry, "select", "_color_temp")
    position = id_by_unique_suffix(hass, entry, "select", "_brightness_position")

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": position, "option": "1"},
        blocking=True,
    )
    before_color = hass.states.get(color).state

    await fire_rf(hass, "r_bu")
    await fire_rf(hass, "r_ku")

    assert hass.states.get(position).state == "2"
    assert hass.states.get(color).state != before_color


async def test_a_frame_reporting_no_code_is_never_suppressed(
    hass: HomeAssistant,
) -> None:
    """With nothing to key a burst on, letting it through beats losing a press."""
    _entry, _calls = await setup_full(hass)
    color = one_id(hass, "select")

    for expected in ("Neutre", "Froid", "Chaud"):
        hass.bus.async_fire(
            EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "action": "light_kelvin"}
        )
        await hass.async_block_till_done()
        assert hass.states.get(color).state == expected


async def test_the_tracking_map_does_not_grow_without_bound(
    hass: HomeAssistant,
) -> None:
    """Stale codes are pruned, so a long-lived entry does not accumulate them."""
    entry, _calls = await setup_full(hass)

    await fire_rf(hass, "c_lt")
    _rewind(entry)
    await fire_rf(hass, "c_kel")

    assert set(entry.runtime_data.receive_seen) == {"c_kel"}
