"""Pytest config: exposes the rf_fan module without triggering the Home Assistant import."""

import sys
from pathlib import Path

# The component directory is added to the path so `const` / `actions` can be imported
# as top-level modules, without going through the package (whose __init__ imports HA).
_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "rf_fan"
sys.path.insert(0, str(_COMPONENT_DIR))
