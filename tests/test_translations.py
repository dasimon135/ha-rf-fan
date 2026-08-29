"""Every action the config flow can ask for must have a label, in every language.

This gap has now shipped three times. @elmr91 reported the first two on
[#18](https://github.com/dasimon135/ha-rf-fan/issues/18) — the twelve `_reverse`
speeds and speeds 7 to 12 were raw keys on screen, because the files stopped at
`fan_speed_6`. Filling those in by hand missed the four stepping keys the same
release introduced (`light_kelvin_up/down`, `light_bright_up/down`), which is
exactly the shape of remote he owns.

Adding a capability means adding an action, and an action with no label is not a
cosmetic defect: the learning screen names the button you are supposed to press on
your remote, so a raw key leaves you guessing which one it means.

These are pure file checks — no Home Assistant, no fixtures.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from custom_components.rf_fan.actions import split_actions

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "rf_fan"
FILES = {
    "strings.json": COMPONENT / "strings.json",
    "en.json": COMPONENT / "translations" / "en.json",
    "fr.json": COMPONENT / "translations" / "fr.json",
}

# Every shape the config flow offers, so the product below is the whole space of
# remotes the integration claims to support rather than a sample of it.
LIGHT_CONTROL = ("none", "toggle", "on_off")
DIRECTION_CONTROL = ("none", "toggle", "per_speed")
NATURAL_CONTROL = ("none", "toggle", "dedicated")
COLOR_CONTROL = ("none", "cycle", "relative")
LIGHT_LEVEL = ("none", "relative")
# 2 and 12 are the bounds; 6 was the old cap, and the range either side of it is
# where the missing speed labels hid.
SPEED_COUNTS = (2, 6, 12)
# 0 and the cap: an extra key exists or it does not, and the cap is what makes the
# label guarantee keepable at all.
EXTRA_COUNTS = (0, 8)


def _loaded(name: str) -> dict:
    return json.loads(FILES[name].read_text(encoding="utf-8"))


def _every_reachable_action() -> set[str]:
    """The union of what `split_actions` asks for across every capability combination."""
    actions: set[str] = set()
    for speed_count in SPEED_COUNTS:
        for (
            light,
            direction,
            natural,
            color,
            level,
            timers,
            sound,
            fan_on,
            extras,
        ) in itertools.product(
            LIGHT_CONTROL,
            DIRECTION_CONTROL,
            NATURAL_CONTROL,
            COLOR_CONTROL,
            LIGHT_LEVEL,
            (False, True),
            (False, True),
            (False, True),
            EXTRA_COUNTS,
        ):
            required, _optional = split_actions(
                speed_count,
                light,
                has_fan_on=fan_on,
                direction_control=direction,
                natural_control=natural,
                color_control=color,
                light_level=level,
                has_timers=timers,
                has_sound=sound,
                extra_count=extras,
            )
            actions.update(required)
    return actions


REACHABLE = _every_reachable_action()


def _key_tree(node: object, prefix: str = "") -> set[str]:
    """Every dotted key path in a nested dict, so two files can be compared wholesale."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(prefix + key)
            found |= _key_tree(value, f"{prefix}{key}.")
    return found


def test_the_action_space_is_not_empty() -> None:
    """A guard on the guard: a broken product would make every test below vacuous."""
    assert len(REACHABLE) > 40
    assert "fan_speed_12_reverse" in REACHABLE
    assert "light_bright_up" in REACHABLE


@pytest.mark.parametrize("name", sorted(FILES))
def test_every_action_has_a_code_label(name: str) -> None:
    """The learning screen names the remote button to press; a raw key names nothing."""
    labels = _loaded(name)["config"]["step"]["codes"]["data"]

    assert sorted(a for a in REACHABLE if a not in labels) == []


@pytest.mark.parametrize("name", sorted(FILES))
def test_every_action_can_be_relearned_by_name(name: str) -> None:
    """The reconfigure recap offers one checkbox per kept code, and labels it."""
    labels = _loaded(name)["config"]["step"]["reconfigure_review"]["data"]

    assert sorted(a for a in REACHABLE if f"relearn_{a}" not in labels) == []


@pytest.mark.parametrize("name", sorted(FILES))
def test_no_label_describes_an_action_that_cannot_exist(name: str) -> None:
    """A label left behind by a removed capability is a lie waiting to be read."""
    step = _loaded(name)["config"]["step"]
    codes = set(step["codes"]["data"])
    relearn = {
        key[len("relearn_") :]
        for key in step["reconfigure_review"]["data"]
        if key.startswith("relearn_")
    }

    assert sorted(codes - REACHABLE) == []
    assert sorted(relearn - REACHABLE) == []


def test_the_three_files_have_the_same_shape() -> None:
    """A key added to one file and forgotten in another falls back to the raw key."""
    trees = {name: _key_tree(_loaded(name)) for name in FILES}
    reference = trees["strings.json"]

    for name, tree in trees.items():
        assert sorted(reference - tree) == [], f"{name} is missing keys"
        assert sorted(tree - reference) == [], f"{name} has keys strings.json does not"


def test_english_is_a_mirror_of_strings() -> None:
    """`strings.json` is the source; `en.json` is what Home Assistant actually serves.

    Editing one and not the other is silent — the UI keeps showing the stale copy,
    and `hassfest` does not compare their values.
    """
    assert _loaded("en.json") == _loaded("strings.json")


def test_french_is_actually_translated() -> None:
    """Copying the English string across is how a language file rots unnoticed."""
    english = _loaded("en.json")["config"]["step"]["codes"]["data"]
    french = _loaded("fr.json")["config"]["step"]["codes"]["data"]

    untranslated = sorted(key for key, value in french.items() if value == english.get(key))

    assert untranslated == []
