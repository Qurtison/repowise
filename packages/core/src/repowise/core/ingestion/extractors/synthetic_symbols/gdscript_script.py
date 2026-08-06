"""The class a ``class_name``-less GDScript file declares.

Every .gd file is a class, but declaring ``class_name`` is optional and most
scripts skip it — the script is attached to a node in a scene and reached by
path, never by name. Such a file has no declaration for the symbol pass to
find, so its methods hang off nothing and a ``preload("res://enemy.gd")`` in
another script resolves to a file with no class in it.

This provider mints that symbol, the same way ``sfc_component`` does for a
Svelte or Vue file: one class-kind ``Symbol`` named after the file, spanning
it. Godot itself uses exactly this naming when it shows a script-less-of-
class_name resource in the editor, so ``enemy_spawner.gd`` reads as
``EnemySpawner``.

Files that DO declare ``class_name`` already have a real symbol at a real
line number, and get nothing from here.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ...models import FileInfo, Symbol
from ..helpers import node_text
from ._helpers import build_synthetic_symbol

if TYPE_CHECKING:
    from tree_sitter import Node


def _pascal_case(stem: str) -> str:
    """``enemy_spawner`` → ``EnemySpawner``; Godot's own script-name rule."""
    parts = [p for p in stem.replace("-", "_").split("_") if p]
    if not parts:
        return ""
    return "".join(p[:1].upper() + p[1:] for p in parts)


def gdscript_script_symbols(root: Node, src: str, file_info: FileInfo) -> list[Symbol]:
    """Return the implicit class symbol for a ``class_name``-less .gd file."""
    extends: str | None = None
    for child in root.children:
        if child.type == "class_name_statement":
            return []  # a real symbol already covers this script
        if child.type == "extends_statement" and extends is None:
            extends = node_text(child, src).strip()

    name = _pascal_case(PurePosixPath(file_info.path).stem)
    if not name or not (name[0].isalpha() or name[0] == "_"):
        return []

    return [
        build_synthetic_symbol(
            name=name,
            kind="class",
            signature=extends or f"class {name}",
            start_line=1,
            end_line=root.end_point[0] + 1,
            file_info=file_info,
            parent_name=None,
        )
    ]
