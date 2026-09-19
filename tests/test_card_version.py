"""The card's own version constant must match the manifest.

The integration cache-busts the card URL with the manifest version, and the card
prints its `VERSION` in the console banner. When a release bumps one and not the
other, the banner names a build the browser did not load -- at the exact moment
somebody is reading it to chase a stale copy (#29).

Pure: no Home Assistant needed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "rf_fan"


def test_card_version_matches_the_manifest() -> None:
    manifest = json.loads((_COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    card = (_COMPONENT / "frontend" / "rf-fan-card.js").read_text(encoding="utf-8")

    declared = re.search(r'^const VERSION = "([^"]+)";', card, flags=re.MULTILINE)

    assert declared is not None, "the card no longer declares `const VERSION`"
    assert declared.group(1) == manifest["version"]
