"""Dynamic-hint extractor for Godot's two implicit-global mechanisms.

GDScript has no import statement, and a great deal of a Godot project's
coupling travels through names that appear in a file with nothing in that
file pointing anywhere. Two mechanisms do it, and between them they account
for most cross-file references in a real game:

**Autoloads.** ``project.godot`` names a script::

    [autoload]
    GameState="*res://autoload/game_state.gd"

and from that point every script can write ``GameState.score`` — no preload,
no import, nothing in its own source referring to ``game_state.gd``.

**class_name registration.** A script declaring::

    class_name ArmorDef
    extends Resource

registers ``ArmorDef`` in Godot's global class table, so any other script can
write ``ArmorDef.new()`` or type a variable ``: ArmorDef`` without loading the
file. This is the idiomatic way GDScript files refer to each other; the
``preload("res://…")`` form is the exception, not the rule.

To an import-only view both mechanisms produce the same illusion: the most
depended-on files in the project look like orphans. This extractor closes
that by indexing both name tables and emitting a ``dynamic_uses`` edge from
every file naming a global to the script that defines it.

Matching is a word-boundary match on the exact identifier, never the
declaring file itself. Both name spaces are PascalCase project-specific
identifiers, so a false positive needs a local of the same name — which would
shadow the global in real code anyway. What the word boundary buys is that
``AudioStreamPlayer`` never matches an ``Audio`` autoload.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import DynamicEdge, DynamicHintExtractor

_SKIP_DIRS = {".git", ".godot", ".import"}

# GameState="*res://autoload/game_state.gd" — the leading ``*`` marks the
# singleton enabled; a disabled one is still declared and still referenced.
_AUTOLOAD_RE = re.compile(r'^\s*([A-Za-z_]\w*)\s*=\s*"\*?res://([^"]+)"', re.MULTILINE)
_AUTOLOAD_SECTION_RE = re.compile(r"^\[autoload\]\s*$(.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL)

# ``class_name Foo`` at file scope, optionally with the Godot 3 comma form
# (``class_name Foo, "res://icon.png"``). Only the first declaration in a file
# counts — GDScript permits exactly one.
_CLASS_NAME_RE = re.compile(r"^\s*class_name\s+([A-Za-z_]\w*)", re.MULTILINE)

_SOURCE_SUFFIXES = (".gd", ".tscn", ".tres")


class GodotDynamicHints(DynamicHintExtractor):
    """Link every file naming a Godot global to the script that defines it."""

    name = "godot"

    def extract(self, repo_root: Path) -> list[DynamicEdge]:
        root_resolved = repo_root.resolve()
        sources = list(self._read_sources(repo_root, root_resolved))
        if not sources:
            return []

        edges: list[DynamicEdge] = []
        edges.extend(self._autoload_edges(repo_root, root_resolved, sources))
        edges.extend(self._class_name_edges(sources))
        return edges

    # -- source snapshot --------------------------------------------------

    def _read_sources(self, repo_root: Path, root_resolved: Path) -> list[tuple[str, str]]:
        """``(repo-relative posix path, text)`` for every Godot source file.

        Read once and shared by both passes — each would otherwise walk and
        decode the same tree.
        """
        out: list[tuple[str, str]] = []
        for suffix in _SOURCE_SUFFIXES:
            for src in self._rglob(repo_root, f"*{suffix}"):
                try:
                    rel = src.resolve().relative_to(root_resolved)
                except ValueError:
                    continue
                if any(part in _SKIP_DIRS for part in rel.parts):
                    continue
                try:
                    out.append((rel.as_posix(), src.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    continue
        return out

    # -- autoloads --------------------------------------------------------

    def _autoload_edges(
        self,
        repo_root: Path,
        root_resolved: Path,
        sources: list[tuple[str, str]],
    ) -> list[DynamicEdge]:
        edges: list[DynamicEdge] = []

        for project_file in self._rglob(repo_root, "project.godot"):
            try:
                project_rel = project_file.resolve().relative_to(root_resolved)
            except ValueError:
                continue
            if any(part in _SKIP_DIRS for part in project_rel.parts):
                continue
            try:
                text = project_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            autoloads = self._parse_autoloads(text)
            if not autoloads:
                continue

            # ``res://`` is relative to the directory holding project.godot,
            # which is not necessarily the repo root.
            project_dir = project_rel.parent
            targets = {
                name: (project_dir / res_path).as_posix() for name, res_path in autoloads.items()
            }
            # A sibling project's scripts do not see this project's autoloads.
            prefix = project_dir.as_posix()
            scoped = [
                (rel, text)
                for rel, text in sources
                if prefix in ("", ".") or rel.startswith(prefix + "/")
            ]
            edges.extend(self._link(targets, scoped, "autoload"))

        return edges

    @staticmethod
    def _parse_autoloads(text: str) -> dict[str, str]:
        section = _AUTOLOAD_SECTION_RE.search(text)
        if section is None:
            return {}
        return {m.group(1): m.group(2) for m in _AUTOLOAD_RE.finditer(section.group(1))}

    # -- class_name globals ------------------------------------------------

    def _class_name_edges(self, sources: list[tuple[str, str]]) -> list[DynamicEdge]:
        targets: dict[str, str] = {}
        for rel, text in sources:
            if not rel.endswith(".gd"):
                continue
            match = _CLASS_NAME_RE.search(text)
            if match is None:
                continue
            # A duplicate class_name is a Godot error the project would not
            # load with; if one is checked in anyway, the first path wins
            # deterministically rather than by walk order.
            name = match.group(1)
            existing = targets.get(name)
            if existing is None or rel < existing:
                targets[name] = rel
        if not targets:
            return []
        return self._link(targets, sources, "class_name")

    # -- shared linking ----------------------------------------------------

    def _link(
        self,
        targets: dict[str, str],
        sources: list[tuple[str, str]],
        kind: str,
    ) -> list[DynamicEdge]:
        patterns = {name: re.compile(rf"\b{re.escape(name)}\b") for name in targets}
        edges: list[DynamicEdge] = []
        for rel, text in sources:
            for name, target in targets.items():
                if target == rel:
                    continue  # a global does not use itself
                if patterns[name].search(text):
                    edges.append(
                        DynamicEdge(
                            source=rel,
                            target=target,
                            edge_type="dynamic_uses",
                            hint_source=f"{self.name}:{kind}",
                        )
                    )
        return edges
