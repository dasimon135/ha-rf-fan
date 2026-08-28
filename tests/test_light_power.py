"""A flip only goes on the air when it would change something (#41).

@elmr91, on `v1.8.0b5`:

> It seems the integration is sending the lamp toggle code instead of brightness+/-
> codes: the lamp is switching on (or off) every time a brightness is changed from
> the card!

`light.turn_on` is the service Home Assistant uses to set a brightness, and it
transmitted the power code unconditionally before stepping. On a remote whose only
light key is `light_toggle` — no `light_on` to fall back from — every move of the
slider flipped the lamp, and the walk that followed stepped a lamp that had just
gone dark. The card is not involved: the native more-info slider does the same, and
so does a scene.

The distinction the fix rests on is between the two shapes of power key:

- `light_on` / `light_off` are ABSOLUTE. Re-sending one lands the lamp where it
  already is, which is worth doing — a drifted assumed state realigns for free.
- `light_toggle` is a FLIP. Sending it towards a state the lamp is already in
  takes it out of that state.

Which is what `switch.py` has always done with the sound toggle. This module holds
`light.py` to the same rule, and asserts the COMPLETE list of frames: counting the
stepping frames while ignoring everything around them is how the stray toggle
shipped in the first place.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from tests.ha_helpers import actions_sent as _actions_sent
from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import setup_on_off as _setup_on_off
from tests.ha_helpers import setup_relative as _setup_relative


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


@pytest.fixture
def no_gap(monkeypatch):
    """Step without waiting on the event loop between presses."""

    async def _fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("custom_components.rf_fan.entity.sleep", _fake_sleep)


async def _power(hass: HomeAssistant, light_id: str, service: str) -> None:
    await hass.services.async_call("light", service, {"entity_id": light_id}, blocking=True)
    await hass.async_block_till_done()


async def test_setting_the_brightness_does_not_flip_a_lamp_that_is_on(
    hass: HomeAssistant, no_gap
) -> None:
    """The bug @elmr91 reported: nine steps up, and a power key among them."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_on")
    calls.clear()

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == ["light_bright_up"] * 9
    assert hass.states.get(light_id).state == "on"


async def test_setting_the_brightness_still_powers_a_lamp_that_is_off(
    hass: HomeAssistant, no_gap
) -> None:
    """Turning the lamp on is what `turn_on` is for; the ± keys need it lit anyway."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_off")
    calls.clear()

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == ["light_toggle"] + ["light_bright_up"] * 9


async def test_turning_on_a_lamp_that_is_already_on_sends_nothing(
    hass: HomeAssistant,
) -> None:
    """The same defect reached by the plain service: a scene asserting a lamp is on."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_on")
    calls.clear()

    await _power(hass, light_id, "turn_on")

    assert _actions_sent(calls) == []
    assert hass.states.get(light_id).state == "on"


async def test_turning_off_a_lamp_that_is_already_off_sends_nothing(
    hass: HomeAssistant,
) -> None:
    """The mirror image, and the one nobody had reported: turning off switched it on."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_off")
    calls.clear()

    await _power(hass, light_id, "turn_off")

    assert _actions_sent(calls) == []
    assert hass.states.get(light_id).state == "off"


async def test_an_unknown_state_still_transmits(hass: HomeAssistant) -> None:
    """Nothing is known until something is sent, so a first command always goes out.

    The same rule `switch.py` applies to the sound toggle (`is not True`): only a
    state the integration actually holds can justify staying silent.
    """
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    assert hass.states.get(light_id).state == "unknown"

    await _power(hass, light_id, "turn_on")

    assert _actions_sent(calls) == ["light_toggle"]


async def test_an_absolute_remote_re_asserts_the_state_it_is_asked_for(
    hass: HomeAssistant,
) -> None:
    """`light_on` lands the lamp on whether or not it was already there.

    So it is still sent, deliberately: on a device that never reports back, a free
    re-assertion is the cheapest way to recover from an assumed state that drifted.
    Only a flip has to hold its fire.
    """
    _entry, calls = await _setup_on_off(hass)
    light_id = _one_id(hass, "light")
    await _power(hass, light_id, "turn_on")
    calls.clear()

    await _power(hass, light_id, "turn_on")
    await _power(hass, light_id, "turn_off")
    await _power(hass, light_id, "turn_off")

    assert _actions_sent(calls) == ["light_on", "light_off", "light_off"]
