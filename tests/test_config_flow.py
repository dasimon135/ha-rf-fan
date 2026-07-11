"""Config flow tests — learn mode (require a HA environment).

⚠️ Not runnable on the Windows dev machine used for this repo:
Home Assistant 2026.3+ requires Python >= 3.14.2, but `lru-dict` has no wheel
for that interpreter and the machine has no MSVC compiler; the HA/phcc
combinations installable under Python 3.13 also fall back to a native build.
Run in CI Linux (or any machine with the HA test environment) via
`pytest-homeassistant-custom-component`. The module `skip`s cleanly if phcc
is absent, so it does not break the pure test suite (`test_actions.py`).

Main regression test: `test_learn_progress_event_fires_on_rf_signal`.
It verifies that HA does emit the `data_entry_flow_progressed` event when an
RF signal is received during learning. This is the event that makes the
frontend refresh; the original bug came from the learning loop keeping the
same `step_id` ("learn") between `async_show_progress` and
`async_show_progress_done(next_step_id="learn")` — since HA notifies the frontend
only on a change of `step_id` (or of `progress_action`/`description_placeholders`
of a `SHOW_PROGRESS`), the event was never emitted and the spinner stayed frozen.
A simple manual re-`async_configure` would mask the bug (the public loop
compensates for the missing notification): hence the assertion on the event itself.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.rf_fan.const import DOMAIN, EVENT_RF_FAN_RECEIVED  # noqa: E402

DEVICE = "esp32-test"
EVENT_PROGRESSED = "data_entry_flow_progressed"


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _start_learn(hass: HomeAssistant):
    """Bring the flow up to the learning screen for the 1st action (fan_off)."""
    # The config flow lists the gateways via the esphome *_transmit_rf_fan services.
    hass.services.async_register(
        "esphome", "esp32_test_transmit_rf_fan", lambda call: None
    )
    await hass.async_block_till_done()

    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "esphome_device": DEVICE,
            "fan_name": "Test",
            "speed_count": 3,
        },
    )
    result = await flow.async_configure(result["flow_id"], {"method": "learn"})
    return flow, result


async def test_learn_progress_event_fires_on_rf_signal(hass: HomeAssistant) -> None:
    """Regression: a `data_entry_flow_progressed` must be emitted on RF reception."""
    flow, result = await _start_learn(hass)
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    assert result["description_placeholders"]["action"] == "fan_off"

    progressed: list = []
    hass.bus.async_listen(EVENT_PROGRESSED, lambda event: progressed.append(event))

    hass.bus.async_fire(EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "C_off"})
    await hass.async_block_till_done()

    assert progressed, "no data_entry_flow_progressed emitted -> frontend frozen"


async def test_learn_flow_advances_and_creates_entry(hass: HomeAssistant) -> None:
    """Full happy-path: each RF signal advances the flow up to creation."""
    flow, result = await _start_learn(hass)
    flow_id = result["flow_id"]

    seen: list[str] = []
    for _ in range(10):
        if result["type"] != FlowResultType.SHOW_PROGRESS:
            break
        action = result["description_placeholders"]["action"]
        seen.append(action)
        hass.bus.async_fire(
            EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": f"C_{action}"}
        )
        await hass.async_block_till_done()
        # Simulates the frontend re-fetch after the progression event.
        result = await flow.async_configure(flow_id)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert seen[:4] == ["fan_off", "fan_speed_1", "fan_speed_2", "fan_speed_3"]
    codes = result["data"]["codes"]
    assert codes["fan_off"] == "C_fan_off"
    assert codes["fan_speed_1"] == "C_fan_speed_1"
    assert codes["fan_speed_3"] == "C_fan_speed_3"


async def test_all_capabilities_manual_flow(hass: HomeAssistant) -> None:
    """Manual with all capabilities: the action list and the entry are complete."""
    hass.services.async_register(
        "esphome", "esp32_test_transmit_rf_fan", lambda call: None
    )
    await hass.async_block_till_done()
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "esphome_device": DEVICE,
            "fan_name": "Full",
            "speed_count": 3,
            "light_control": "toggle",
            "has_fan_on": False,
            "has_direction": True,
            "has_natural_preset": True,
            "has_color_temp": True,
            "has_timers": True,
            "has_sound": True,
        },
    )
    result = await flow.async_configure(result["flow_id"], {"method": "manual"})
    assert result["step_id"] == "codes"

    # Provide a code per required action. required = fan_off + speed_1..3 +
    # light_toggle (via at-least-one) + fan_reverse + fan_natural + light_kelvin
    # + timer_1h/2h/4h/8h + sound_toggle. Also provide light_toggle for the
    # "at least one light code" rule.
    codes_input = {
        "fan_off": "C_off",
        "fan_speed_1": "C_s1", "fan_speed_2": "C_s2", "fan_speed_3": "C_s3",
        "light_toggle": "C_lt",
        "fan_reverse": "C_rev", "fan_natural": "C_nat", "light_kelvin": "C_kel",
        "timer_1h": "C_t1", "timer_2h": "C_t2", "timer_4h": "C_t4", "timer_8h": "C_t8",
        "sound_toggle": "C_snd",
    }
    result = await flow.async_configure(result["flow_id"], codes_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["has_direction"] and data["has_color_temp"] and data["has_sound"]
    codes = data["codes"]
    assert codes["fan_reverse"] == "C_rev"
    assert codes["light_kelvin"] == "C_kel"
    assert codes["timer_8h"] == "C_t8"
    assert codes["sound_toggle"] == "C_snd"


def _basic_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a basic entry (3 speeds + light toggle) registered in hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Recon",
        data={
            "esphome_device": DEVICE,
            "fan_name": "Recon",
            "speed_count": 3,
            "light_control": "toggle",
            "has_fan_on": False,
            "has_direction": False,
            "has_natural_preset": False,
            "has_color_temp": False,
            "has_timers": False,
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
    )
    entry.add_to_hass(hass)
    return entry


async def test_reconfigure_adds_capabilities(hass: HomeAssistant) -> None:
    """Reconfigure by enabling the timers: only the delta is requested, codes merged."""
    entry = _basic_entry(hass)
    flow = hass.config_entries.flow

    # The reload triggered by async_update_reload_and_abort is neutralized: here we
    # only test the flow logic, not the (re)mounting of the platforms.
    with patch(
        "custom_components.rf_fan.async_setup_entry", return_value=True
    ):
        result = await flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )
        assert result["step_id"] == "reconfigure"

        # Re-declare the same basics, but with the timers enabled.
        result = await flow.async_configure(
            result["flow_id"],
            {
                "fan_name": "Recon",
                "speed_count": 3,
                "light_control": "toggle",
                "has_fan_on": False,
                "has_direction": False,
                "has_natural_preset": False,
                "has_color_temp": False,
                "has_timers": True,
                "has_sound": False,
            },
        )
        assert result["step_id"] == "reconfigure_review"

        # Do not re-learn any kept action.
        result = await flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "method"

        result = await flow.async_configure(result["flow_id"], {"method": "manual"})
        assert result["step_id"] == "codes"

        # The form must request ONLY the delta: the 4 timers.
        fields = {str(key) for key in result["data_schema"].schema}
        assert fields == {"timer_1h", "timer_2h", "timer_4h", "timer_8h"}

        result = await flow.async_configure(
            result["flow_id"],
            {"timer_1h": "t1", "timer_2h": "t2", "timer_4h": "t4", "timer_8h": "t8"},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    codes = entry.data["codes"]
    # The 5 original codes + the 4 timers = 9 in total.
    assert codes == {
        "fan_off": "c_off",
        "fan_speed_1": "c1",
        "fan_speed_2": "c2",
        "fan_speed_3": "c3",
        "light_toggle": "c_tog",
        "timer_1h": "t1",
        "timer_2h": "t2",
        "timer_4h": "t4",
        "timer_8h": "t8",
    }
    assert entry.data["has_timers"] is True


async def test_reconfigure_relearn_and_light_control_change(hass: HomeAssistant) -> None:
    """Reconfigure by enabling color + re-learn light_toggle."""
    entry = _basic_entry(hass)
    flow = hass.config_entries.flow

    with patch(
        "custom_components.rf_fan.async_setup_entry", return_value=True
    ):
        result = await flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )
        result = await flow.async_configure(
            result["flow_id"],
            {
                "fan_name": "Recon",
                "speed_count": 3,
                "light_control": "toggle",
                "has_fan_on": False,
                "has_direction": False,
                "has_natural_preset": False,
                "has_color_temp": True,
                "has_timers": False,
                "has_sound": False,
            },
        )
        assert result["step_id"] == "reconfigure_review"

        # Check the re-learning of light_toggle (kept action).
        result = await flow.async_configure(
            result["flow_id"], {"relearn_light_toggle": True}
        )
        result = await flow.async_configure(result["flow_id"], {"method": "manual"})
        assert result["step_id"] == "codes"

        # Requested delta: light_toggle (re-learned) + light_kelvin (new).
        fields = {str(key) for key in result["data_schema"].schema}
        assert fields == {"light_toggle", "light_kelvin"}

        result = await flow.async_configure(
            result["flow_id"],
            {"light_toggle": "c_tog_new", "light_kelvin": "c_kel"},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    codes = entry.data["codes"]
    assert codes["light_toggle"] == "c_tog_new"  # overwritten by the re-learning
    assert codes["light_kelvin"] == "c_kel"  # new capability
    assert codes["fan_off"] == "c_off"  # basics kept
    assert codes["fan_speed_3"] == "c3"
    assert entry.data["has_color_temp"] is True


async def test_reconfigure_learn_keeps_kept_codes(hass: HomeAssistant) -> None:
    """Regression: reconfiguration in learn mode preserves the kept codes.

    This is the path where the seed-erasure bug lived: the learning loop
    must re-learn only the delta (`_pending_actions`) while keeping the 5
    existing codes (`_learn_codes` pre-filled from the entry).
    Modeled on `test_learn_flow_advances_and_creates_entry` to drive the
    `SHOW_PROGRESS` screens (fire `EVENT_RF_FAN_RECEIVED` then re-`async_configure`).
    """
    entry = _basic_entry(hass)
    # The gateway must be discoverable as in `_start_learn`.
    hass.services.async_register(
        "esphome", "esp32_test_transmit_rf_fan", lambda call: None
    )
    await hass.async_block_till_done()
    flow = hass.config_entries.flow

    learned = {"timer_1h": "t1", "timer_2h": "t2", "timer_4h": "t4", "timer_8h": "t8"}

    with patch(
        "custom_components.rf_fan.async_setup_entry", return_value=True
    ):
        result = await flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )
        result = await flow.async_configure(
            result["flow_id"],
            {
                "fan_name": "Recon",
                "speed_count": 3,
                "light_control": "toggle",
                "has_fan_on": False,
                "has_direction": False,
                "has_natural_preset": False,
                "has_color_temp": False,
                "has_timers": True,
                "has_sound": False,
            },
        )
        assert result["step_id"] == "reconfigure_review"
        result = await flow.async_configure(result["flow_id"], {})
        result = await flow.async_configure(result["flow_id"], {"method": "learn"})
        flow_id = result["flow_id"]

        # The learning loop must iterate ONLY over the delta (the 4 timers).
        seen: list[str] = []
        for _ in range(10):
            if result["type"] != FlowResultType.SHOW_PROGRESS:
                break
            action = result["description_placeholders"]["action"]
            seen.append(action)
            hass.bus.async_fire(
                EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": learned[action]}
            )
            await hass.async_block_till_done()
            # Simulates the frontend re-fetch after the progression event.
            result = await flow.async_configure(flow_id)
        await hass.async_block_till_done()

    assert seen == ["timer_1h", "timer_2h", "timer_4h", "timer_8h"]
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    codes = entry.data["codes"]
    # The 5 kept codes SURVIVE + the 4 learned timers = 9 in total.
    assert codes == {
        "fan_off": "c_off",
        "fan_speed_1": "c1",
        "fan_speed_2": "c2",
        "fan_speed_3": "c3",
        "light_toggle": "c_tog",
        "timer_1h": "t1",
        "timer_2h": "t2",
        "timer_4h": "t4",
        "timer_8h": "t8",
    }
    assert entry.data["has_timers"] is True
