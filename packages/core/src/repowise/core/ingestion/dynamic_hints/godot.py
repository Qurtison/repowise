"""Dynamic-hint extractor for Godot autoload singletons.

An autoload is Godot's dependency injection. ``project.godot`` names a script::

    [autoload]
    GameState="*res://src/autoload/game_state.gd"

and from that point every script in the project can write ``GameState.score``
with no ``preload``, no import, and nothing at all in its own source pointing
at ``game_state.gd``. The static graph sees a bare identifier.

That makes autoloads simultaneously the most-depended-on files in a Godot
project and, to an import-only view, the least — they look reachable from
project.godot alone while the dozens of scripts actually using them look
unrelated. This extractor closes that gap: it reads the autoload table, then
emits a ``dynamic_uses`` edge from every file naming one of those globals to
the script behind it.

The name match is deliberately strict — a word-boundary match on the exact
autoload identifier, and never the declaring file itself. Autoload names are
PascalCase project-specific identifiers (``GameState``, ``AudioManager``), so
a false positive would need a local variable of the same name, which would
shadow the singleton in real code anyway.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import DynamicEdge, DynamicHintExtractor

_SKIP_DIRS = {".git", ".godot", ".import", "addons"}

# GameState="*res://src/autoload/game_state.gd" — the leading ``*`` marks the
# singleton enabled; a disabled one is still declared and still referenced.
_AUTOLOAD_RE = re.compile(r'^\s*([A-Za-z_]\w*)\s*=\s*"\*?res://([^"]+)"', re.MULTILINE)
_AUTOLOAD_SECTION_RE = re.compile(r"^\[autoload\]\s*$(.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL)

_SOURCE_SUFFIXES = (".gd", ".tscn", ".tres")


class GodotDynamicHints(DynamicHintExtractor):
    """Link every script that names an autoload to the script behind it."""

    name = "godot"

    def extract(self, repo_root: Path) -> list[DynamicEdge]:
        edges: list[DynamicEdge] = []
        root_resolved = repo_root.resolve()

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
            edges.extend(self._link_references(repo_root, root_resolved, project_dir, targets))

        return edges

    @staticmethod
    def _parse_autoloads(text: str) -> dict[str, str]:
        section = _AUTOLOAD_SECTION_RE.search(text)
        if section is None:
            return {}
        return {m.group(1): m.group(2) for m in _AUTOLOAD_RE.finditer(section.group(1))}

    def _link_references(
        self,
        repo_root: Path,
        root_resolved: Path,
        project_dir: Path,
        targets: dict[str, str],
    ) -> list[DynamicEdge]:
        patterns = {name: re.compile(rf"\b{re.escape(name)}\b") for name in targets}
        edges: list[DynamicEdge] = []

        for suffix in _SOURCE_SUFFIXES:
            for src in self._rglob(repo_root, f"*{suffix}"):
                try:
                    rel = src.resolve().relative_to(root_resolved)
                except ValueError:
                    continue
                if any(part in _SKIP_DIRS for part in rel.parts):
                    continue
                # A sibling project's scripts do not see this project's
                # autoloads, so scope the scan to the project's own tree.
                rel_posix = rel.as_posix()
                prefix = project_dir.as_posix()
                if prefix not in ("", ".") and not rel_posix.startswith(prefix + "/"):
                    continue

                try:
                    text = src.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                for name, target in targets.items():
                    if target == rel_posix:
                        continue  # the singleton does not use itself
                    if patterns[name].search(text):
                        edges.append(
                            DynamicEdge(
                                source=rel_posix,
                                target=target,
                                edge_type="dynamic_uses",
                                hint_source=f"{self.name}:autoload",
                            )
                        )

        return edges
