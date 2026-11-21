"""The declaration file's format, without Home Assistant (#58)."""

from __future__ import annotations

import pytest
from declaration import (
    REASON_BAD_VALUE,
    REASON_CODE_NOT_TEXT,
    REASON_FORMAT,
    REASON_UNKNOWN_KEY,
    REASON_UNREADABLE,
    DeclarationError,
    dump_declaration,
    parse_declaration,
)

FORM = {
    "speed_count": 6,
    "light_control": "toggle",
    "has_fan_on": False,
    "direction_control": "none",
    "natural_control": "toggle",
    "natural_levels": 0,
    "color_control": "none",
    "color_temp_steps": 3,
    "light_level": "none",
    "light_level_steps": 10,
    "timer_hours": ["2", "4"],
    "has_timer_off": True,
    "has_sound": False,
    "extra_count": 1,
}
# Codes that YAML would read back as something else if they were not quoted.
CODES = {"fan_off": "0123", "speed_1": "1234567", "speed_2": "yes", "light_toggle": "raw:1,-2"}


def _reason(text: str) -> tuple[str, str]:
    with pytest.raises(DeclarationError) as caught:
        parse_declaration(text)
    return caught.value.reason, caught.value.key


def test_a_dumped_declaration_reads_back_identical() -> None:
    text = dump_declaration(
        name="Salon",
        form=FORM,
        extra_names={"extra_1": "Ionisation"},
        repeat_count=4,
        codes=CODES,
    )
    parsed = parse_declaration(text)
    assert parsed.name == "Salon"
    assert parsed.form == FORM
    assert parsed.extra_names == {"extra_1": "Ionisation"}
    assert parsed.repeat_count == 4
    assert parsed.codes == CODES


def test_the_document_names_no_gateway() -> None:
    text = dump_declaration(name="x", form=FORM, extra_names={}, repeat_count=3, codes={})
    assert "esphome_device" not in text
    assert "gateway_service" not in text
    assert text.startswith("format: 1\n")


def test_timer_hours_are_written_as_numbers() -> None:
    text = dump_declaration(name="x", form=FORM, extra_names={}, repeat_count=3, codes={})
    assert "timer_hours:\n- 2\n- 4\n" in text


def test_a_hand_written_file_needs_only_format() -> None:
    parsed = parse_declaration("format: 1\n")
    assert parsed.form == {}
    assert parsed.codes == {}
    assert parsed.repeat_count is None
    assert parsed.name == ""


@pytest.mark.parametrize(
    "text",
    ["format: [1", "- format: 1", "just words", "", "x" * (64 * 1024 + 1)],
)
def test_what_is_not_a_document_is_unreadable(text: str) -> None:
    assert _reason(text)[0] == REASON_UNREADABLE


@pytest.mark.parametrize("text", ["speed_count: 3\n", "format: 2\n", "format: '1'\n"])
def test_a_document_without_the_supported_format_is_refused(text: str) -> None:
    assert _reason(text) == (REASON_FORMAT, "format")


def test_an_unknown_key_is_named() -> None:
    assert _reason("format: 1\nspeed_cout: 3\n") == (REASON_UNKNOWN_KEY, "speed_cout")


def test_the_gateway_is_not_accepted_from_a_file() -> None:
    assert _reason("format: 1\nesphome_device: gw\n") == (REASON_UNKNOWN_KEY, "esphome_device")


def test_an_unquoted_number_as_a_code_is_refused() -> None:
    assert _reason("format: 1\ncodes:\n  fan_off: 0123\n") == (
        REASON_CODE_NOT_TEXT,
        "codes.fan_off",
    )


def test_an_empty_code_is_refused() -> None:
    assert _reason("format: 1\ncodes:\n  fan_off: ''\n") == (
        REASON_CODE_NOT_TEXT,
        "codes.fan_off",
    )


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("format: 1\nname: 3\n", "name"),
        ("format: 1\nrepeat_count: true\n", "repeat_count"),
        ("format: 1\nrepeat_count: '3'\n", "repeat_count"),
        ("format: 1\ncodes: [a]\n", "codes"),
        ("format: 1\nextra_names: [a]\n", "extra_names"),
        ("format: 1\ntimer_hours: 2\n", "timer_hours"),
        ("format: 1\ntimer_hours: [true]\n", "timer_hours"),
    ],
)
def test_a_part_of_the_wrong_type_is_named(text: str, key: str) -> None:
    assert _reason(text) == (REASON_BAD_VALUE, key)


def test_codes_are_trimmed() -> None:
    assert parse_declaration("format: 1\ncodes:\n  fan_off: ' 12 '\n").codes == {
        "fan_off": "12"
    }
