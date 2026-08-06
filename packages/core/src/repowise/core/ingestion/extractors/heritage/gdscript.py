"""GDScript heritage extraction.

GDScript inherits in two places, and only one of them looks like the other
languages here:

* An inner ``class Inner extends RefCounted:`` carries its ``extends`` as a
  child of the class node — the ordinary shape.
* A script's *own* ``extends`` is a file-scope statement that sits beside
  ``class_name`` rather than inside anything::

      class_name Enemy
      extends CharacterBody2D

  So for the class_name_statement the parent is found by looking at the
  script's top level, not at the definition node's children. Order is not
  fixed either — ``extends`` may legally precede ``class_name``.

The parent may also be a path rather than a type name
(``extends "res://src/base_thing.gd"``). The file edge for that form comes
from the import query; here it is reduced to the base script's stem so the
heritage relation still names something a reader recognises.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from tree_sitter import Node

from ...models import HeritageRelation
from ..helpers import node_text


def _parent_name_from_extends(extends_node: Node, src: str) -> str | None:
    """The type name (or base-script stem) an extends_statement names."""
    for child in extends_node.children:
        if not child.is_named:
            continue
        text = node_text(child, src).strip()
        if not text:
            continue
        if child.type == "string":
            # extends "res://src/base_thing.gd" → BaseThing's file stem.
            path = text.strip("\"'")
            stem = PurePosixPath(path).stem
            return stem or None
        # extends Foo.Bar (an inner class of another script) — the bare
        # trailing name is what the graph indexes, as in python.py.
        return text.split(".")[-1]
    return None


def _extract_gdscript_heritage(
    def_node: Node, name: str, line: int, src: str, out: list[HeritageRelation]
) -> None:
    """GDScript: file-scope ``extends`` for the script, own child for inner classes."""
    if def_node.type == "class_name_statement":
        # The script's extends is a sibling at file scope, either side of us.
        container = def_node.parent
        if container is None:
            return
        candidates = [c for c in container.children if c.type == "extends_statement"]
    else:
        candidates = [c for c in def_node.children if c.type == "extends_statement"]

    for extends_node in candidates:
        parent = _parent_name_from_extends(extends_node, src)
        if parent:
            out.append(
                HeritageRelation(child_name=name, parent_name=parent, kind="extends", line=line)
            )
        # A GDScript class extends exactly one thing.
        return
