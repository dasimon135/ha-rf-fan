"""Pytest config: exposes the rf_fan module without triggering the Home Assistant import."""

import sys
from pathlib import Path

# The component directory is added to the path so `const` / `actions` can be imported
# as top-level modules, without going through the package (whose __init__ imports HA).
# Appended (not inserted first) so component modules such as select.py can never
# shadow their stdlib namesakes (`select` is imported lazily by `selectors`).
_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "rf_fan"
sys.path.append(str(_COMPONENT_DIR))
