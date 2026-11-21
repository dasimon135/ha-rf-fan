"""A fan's declaration as one YAML document (#58).

Pure (no Home Assistant import), so the file format is testable on its own. The
config flow owns everything that needs the form: validating the declaration's
values against the same schema, and deciding which codes are still missing.

The document carries what describes the fan and its remote -- capabilities, the
names of its free-form keys, the repeat count, the learned codes -- and never the
gateway. The gateway belongs to one installation; leaving it out is what lets one
file serve every owner of the same remote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

try:  # Home Assistant runtime: relative import within the package
    from .const import (
        CONF_CODES,
        CONF_COLOR_CONTROL,
        CONF_COLOR_TEMP_STEPS,
        CONF_DIRECTION_CONTROL,
        CONF_EXTRA_COUNT,
        CONF_EXTRA_NAMES,
        CONF_HAS_FAN_ON,
        CONF_HAS_SOUND,
        CONF_HAS_TIMER_OFF,
        CONF_LIGHT_CONTROL,
        CONF_LIGHT_LEVEL,
        CONF_LIGHT_LEVEL_STEPS,
        CONF_NATURAL_CONTROL,
        CONF_NATURAL_LEVELS,
        CONF_REPEAT_COUNT,
        CONF_SPEED_COUNT,
        CONF_TIMER_HOURS,
    )
except ImportError:  # pragma: no cover - tests: top-level import via conftest
    from const import (
        CONF_CODES,
        CONF_COLOR_CONTROL,
        CONF_COLOR_TEMP_STEPS,
        CONF_DIRECTION_CONTROL,
        CONF_EXTRA_COUNT,
        CONF_EXTRA_NAMES,
        CONF_HAS_FAN_ON,
        CONF_HAS_SOUND,
        CONF_HAS_TIMER_OFF,
        CONF_LIGHT_CONTROL,
        CONF_LIGHT_LEVEL,
        CONF_LIGHT_LEVEL_STEPS,
        CONF_NATURAL_CONTROL,
        CONF_NATURAL_LEVELS,
        CONF_REPEAT_COUNT,
        CONF_SPEED_COUNT,
        CONF_TIMER_HOURS,
    )

DECLARATION_FORMAT = 1
KEY_FORMAT = "format"
KEY_NAME = "name"
# Far above any real declaration (a few kilobytes with raw timings), low enough that
# a wrong paste is refused before it is parsed.
MAX_DECLARATION_LENGTH = 64 * 1024

# The declaration form's own fields, in the order the form shows them. These are
# the keys the file shares with the entry data and with the form.
FORM_KEYS: tuple[str, ...] = (
    CONF_SPEED_COUNT,
    CONF_LIGHT_CONTROL,
    CONF_HAS_FAN_ON,
    CONF_DIRECTION_CONTROL,
    CONF_NATURAL_CONTROL,
    CONF_NATURAL_LEVELS,
    CONF_COLOR_CONTROL,
    CONF_COLOR_TEMP_STEPS,
    CONF_LIGHT_LEVEL,
    CONF_LIGHT_LEVEL_STEPS,
    CONF_TIMER_HOURS,
    CONF_HAS_TIMER_OFF,
    CONF_HAS_SOUND,
    CONF_EXTRA_COUNT,
)
_KNOWN_KEYS = {
    KEY_FORMAT,
    KEY_NAME,
    *FORM_KEYS,
    CONF_EXTRA_NAMES,
    CONF_REPEAT_COUNT,
    CONF_CODES,
}

# Error reasons, each the suffix of a translated config-flow error.
REASON_UNREADABLE = "declaration_unreadable"
REASON_FORMAT = "declaration_format"
REASON_UNKNOWN_KEY = "declaration_unknown_key"
REASON_BAD_VALUE = "declaration_bad_value"
REASON_CODE_NOT_TEXT = "declaration_code_not_text"


class DeclarationError(ValueError):
    """A pasted declaration that cannot be used, and the key it is about."""

    def __init__(self, reason: str, key: str = "") -> None:
        """Keep the reason (a translation key) and the offending key, if any."""
        super().__init__(f"{reason}: {key}" if key else reason)
        self.reason = reason
        self.key = key


@dataclass
class Declaration:
    """A parsed document; its form values are not validated yet."""

    name: str = ""
    form: dict[str, Any] = field(default_factory=dict)
    extra_names: dict[str, str] = field(default_factory=dict)
    repeat_count: int | None = None
    codes: dict[str, str] = field(default_factory=dict)


def dump_declaration(
    *,
    name: str,
    form: dict[str, Any],
    extra_names: dict[str, str],
    repeat_count: int,
    codes: dict[str, str],
) -> str:
    """The YAML document for one fan, keys in the form's order.

    `safe_dump` quotes every code that would read back as anything but text (a
    decimal code, `yes`, `0123`), so the document round-trips by construction.
    """
    document: dict[str, Any] = {KEY_FORMAT: DECLARATION_FORMAT, KEY_NAME: name}
    for key in FORM_KEYS:
        if key not in form:
            continue
        value = form[key]
        if key == CONF_TIMER_HOURS:
            value = [int(hours) for hours in value]
        document[key] = value
    named = {action: label for action, label in extra_names.items() if label}
    if named:
        document[CONF_EXTRA_NAMES] = named
    document[CONF_REPEAT_COUNT] = int(repeat_count)
    document[CONF_CODES] = {action: str(code) for action, code in codes.items() if code}
    return yaml.safe_dump(
        document, sort_keys=False, allow_unicode=True, default_flow_style=False
    )


def parse_declaration(text: str) -> Declaration:
    """Read a pasted document into its parts, or raise DeclarationError.

    Only the shape is checked here: which keys exist, and that each part has the
    type it must have. Whether `speed_count: 40` is acceptable is the form's
    schema's call, made by the config flow.

    A code must be text. YAML reads an unquoted `0123` as the integer 83, so
    accepting numbers would turn a typed file into a remote that sends the wrong
    frame; the error asks for quotes instead.
    """
    if len(text) > MAX_DECLARATION_LENGTH:
        raise DeclarationError(REASON_UNREADABLE)
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise DeclarationError(REASON_UNREADABLE) from err
    if not isinstance(raw, dict):
        raise DeclarationError(REASON_UNREADABLE)
    if raw.get(KEY_FORMAT) != DECLARATION_FORMAT:
        raise DeclarationError(REASON_FORMAT, KEY_FORMAT)
    for key in raw:
        if key not in _KNOWN_KEYS:
            raise DeclarationError(REASON_UNKNOWN_KEY, str(key))

    declaration = Declaration()

    name = raw.get(KEY_NAME)
    if name is not None:
        if not isinstance(name, str):
            raise DeclarationError(REASON_BAD_VALUE, KEY_NAME)
        declaration.name = name.strip()

    for key in FORM_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if key == CONF_TIMER_HOURS:
            # The form's multi-select speaks strings; a file is written with numbers.
            if not isinstance(value, list) or any(
                isinstance(hours, bool) or not isinstance(hours, (int, str))
                for hours in value
            ):
                raise DeclarationError(REASON_BAD_VALUE, key)
            value = [str(hours) for hours in value]
        declaration.form[key] = value

    names = raw.get(CONF_EXTRA_NAMES, {})
    if not isinstance(names, dict) or any(
        not isinstance(action, str) or not isinstance(label, str)
        for action, label in names.items()
    ):
        raise DeclarationError(REASON_BAD_VALUE, CONF_EXTRA_NAMES)
    declaration.extra_names = {action: label.strip() for action, label in names.items()}

    if CONF_REPEAT_COUNT in raw:
        count = raw[CONF_REPEAT_COUNT]
        if isinstance(count, bool) or not isinstance(count, int):
            raise DeclarationError(REASON_BAD_VALUE, CONF_REPEAT_COUNT)
        declaration.repeat_count = count

    codes = raw.get(CONF_CODES, {})
    if codes is None:
        codes = {}
    if not isinstance(codes, dict):
        raise DeclarationError(REASON_BAD_VALUE, CONF_CODES)
    for action, code in codes.items():
        if not isinstance(action, str):
            raise DeclarationError(REASON_BAD_VALUE, CONF_CODES)
        if not isinstance(code, str) or not code.strip():
            raise DeclarationError(REASON_CODE_NOT_TEXT, f"{CONF_CODES}.{action}")
        declaration.codes[action] = code.strip()
    return declaration
