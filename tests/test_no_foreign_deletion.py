"""Nothing in the integration deletes files, least of all outside its own folder.

1.x lived in custom_components/rf_fan, the folder clevrdavid/rf_fan installs into.
2.0.0 deleted it once its manifest looked like ours; the HACS review asked for that
to go (hacs/default#10711): if the guess is ever wrong, a user loses a different
integration. The user removes the old version, and the flow waits for it.

A source scan, so a deletion cannot come back through a path the flow tests miss.
Pure: no Home Assistant needed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "esphome_rf_fan"
SOURCES = sorted(COMPONENT.rglob("*.py"))

# Modules whose import alone means the code can remove a tree.
_DELETING_MODULES = {"shutil", "send2trash"}
# Calls that remove a file or a directory, whatever object they are called on.
_DELETING_CALLS = {"rmtree", "unlink", "rmdir", "removedirs"}


def _deletions(code: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in _DELETING_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in _DELETING_MODULES:
                found.append(f"from {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name, owner = node.func.attr, node.func.value
            if name in _DELETING_CALLS or (
                name == "remove" and isinstance(owner, ast.Name) and owner.id == "os"
            ):
                found.append(f"{ast.unparse(node.func)}() line {node.lineno}")
    return found


def test_the_scan_sees_the_sources() -> None:
    assert COMPONENT / "legacy.py" in SOURCES


@pytest.mark.parametrize("source", SOURCES, ids=lambda p: p.relative_to(COMPONENT).as_posix())
def test_no_source_deletes_files(source: Path) -> None:
    assert _deletions(source.read_text(encoding="utf-8")) == []


def test_the_scan_catches_the_deletion_it_replaced() -> None:
    """The 2.0.0 code, as it was: the scan must flag it."""
    code = "import shutil\n\ndef remove(path):\n    shutil.rmtree(path)\n"
    assert len(_deletions(code)) == 2
