"""The bundled card must be themeable.

Checked on the shipped file so it cannot regress silently:

1. The card renders inside a real ``<ha-card>`` — anything a theme or card-mod
   applies to the card element selects ``ha-card``.

2. No frozen colour. Every colour literal must be the fallback of a
   ``var(--rf-fan-*, …)`` (or of a Home Assistant variable), so a theme can
   repaint the card while the default rendering stays what it is today. The
   console banner printed at load time is the only exception.
"""

import re
from pathlib import Path

CARD = Path(__file__).parents[1] / "custom_components" / "rf_fan" / "frontend" / "rf-fan-card.js"

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FALLBACK = re.compile(r"var\(\s*--[a-z0-9-]+\s*,\s*(?:var\([^)]*,\s*)?#[0-9a-fA-F]{3,8}\b")


def _chrome_lines() -> list[tuple[int, str]]:
    lines = CARD.read_text(encoding="utf-8").splitlines()
    return [(n, line) for n, line in enumerate(lines, 1) if "console.info" not in line]


def test_card_container_is_a_real_ha_card() -> None:
    assert 'document.createElement("ha-card")' in CARD.read_text(encoding="utf-8")


def test_every_colour_literal_is_a_variable_fallback() -> None:
    frozen = []
    for n, line in _chrome_lines():
        literals = HEX.findall(line)
        if literals and len(FALLBACK.findall(line)) < len(literals):
            frozen.append(f"{n}: {line.strip()[:100]}")
    assert not frozen, "hard-coded colours (not a var() fallback):\n" + "\n".join(frozen)


def test_no_coloured_rgb_literals() -> None:
    """rgba() literals are tolerated only for pure black shadows/scrims."""
    bad = []
    for n, line in _chrome_lines():
        for m in re.finditer(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", line):
            if m.groups() != ("0", "0", "0"):
                bad.append(f"{n}: {m.group(0)}")
    assert not bad, "coloured rgb() literals:\n" + "\n".join(bad)
