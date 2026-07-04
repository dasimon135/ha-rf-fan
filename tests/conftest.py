"""Config pytest : expose le module rf_fan sans déclencher l'import Home Assistant."""

import sys
from pathlib import Path

# Le dossier du composant est ajouté au path pour importer `const` / `actions`
# en modules top-level, sans passer par le package (dont __init__ importe HA).
_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "rf_fan"
sys.path.insert(0, str(_COMPONENT_DIR))
