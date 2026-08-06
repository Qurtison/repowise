"""Godot ``res://`` import resolution — GDScript and scene/resource files.

Godot addresses every project file through one scheme::

    res://src/enemies/enemy.gd

``res://`` is the project root — the directory holding ``project.godot`` —
so resolution is a prefix swap and a path lookup, with none of the search-path
guesswork other languages need. That is why both ``gdscript`` and
``godot_resource`` declare ``import_support="full"``.

Four forms reach this resolver:

1. ``res://`` absolute paths, from ``preload()``, ``[ext_resource path=…]``,
   ``run/main_scene``, and ``extends "res://…"``.
2. ``*res://`` — project.godot's ``[autoload]`` writes a leading ``*`` to mark
   the singleton enabled. Stripped before resolution.
3. Relative paths (``../shared/util.gd``), which ``preload()`` also accepts,
   resolved against the importing file's directory.
4. ``uid://`` references, which Godot 4.4+ writes beside the literal path.
   A UID is an opaque handle stored in the target's ``.uid`` sidecar, so it
   is recorded as an external node rather than guessed at — the same
   ``[ext_resource]`` line always carries the real path, and that one resolves.

The project root is usually the repo root, but need not be: a repo can hold
the game under ``game/`` beside a ``tools/`` directory, or several projects
side by side. The root is therefore located from the indexed file set by
finding the ``project.godot`` nearest the importing file, and only falls back
to the repo root when the project file was not indexed.
"""

from __future__ import annotations

import posixpath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import ResolverContext

_RES_PREFIX = "res://"
_UID_PREFIX = "uid://"

# Godot rewrites some source extensions on export/import. A scene reference to
# ``icon.png`` may be stored pointing at the imported artefact; the source file
# is what the repo actually contains.
_CACHE_SUFFIX = ".import"


def _project_roots(ctx: ResolverContext) -> tuple[str, ...]:
    """Directories holding a ``project.godot``, deepest first (cached).

    Deepest-first so a nested project (``addons/…`` demos, a repo of several
    games) wins over an enclosing one for files that live inside it.
    """
    cached = getattr(ctx, "_godot_project_roots", None)
    if cached is not None:
        return cached

    roots = sorted(
        (
            posixpath.dirname(p)
            for p in ctx.sorted_paths
            if posixpath.basename(p) == "project.godot"
        ),
        key=lambda d: (-d.count("/"), d),
    )
    result = tuple(roots)
    ctx._godot_project_roots = result  # type: ignore[attr-defined]
    return result


def _root_for(importer_path: str, ctx: ResolverContext) -> str:
    """The project root governing *importer_path* (``""`` = repo root)."""
    importer_dir = posixpath.dirname(importer_path)
    for root in _project_roots(ctx):
        if root == "" or importer_dir == root or importer_dir.startswith(root + "/"):
            return root
    # No project.godot indexed (a single script pulled out of a project, or an
    # addon repo published on its own): res:// can only mean the repo root.
    return ""


def _lookup(candidate: str, ctx: ResolverContext) -> str | None:
    """Return *candidate* if the repo holds it, else None."""
    normalised = posixpath.normpath(candidate).lstrip("/")
    if normalised in ctx.path_set:
        return normalised
    return None


def resolve_godot_import(
    module_path: str,
    importer_path: str,
    ctx: ResolverContext,
) -> str | None:
    """Resolve a Godot resource path to a repo-relative file path."""
    raw = module_path.strip()
    if not raw:
        return None

    # [autoload] enabled marker.
    path = raw.lstrip("*").strip()

    if path.startswith(_UID_PREFIX):
        # Opaque handle — never guessed. See the module docstring.
        return ctx.add_external_node(path)

    if path.startswith(_RES_PREFIX):
        relative = path[len(_RES_PREFIX) :]
        root = _root_for(importer_path, ctx)
        candidate = posixpath.join(root, relative) if root else relative
        resolved = _lookup(candidate, ctx)
        if resolved is not None:
            return resolved
        # A path that is right but whose target is not indexed — an asset
        # excluded by the traverser, or a file Godot generates. Record the
        # reference rather than dropping it.
        return ctx.add_external_node(path)

    # ``user://`` is the writable data directory, never a repo file.
    if path.startswith("user://"):
        return ctx.add_external_node(path)

    # Relative form: preload("../shared/util.gd").
    resolved = _lookup(posixpath.join(posixpath.dirname(importer_path), path), ctx)
    if resolved is not None:
        return resolved

    # Godot's asset cache sidecar — the source file is what the repo holds.
    if path.endswith(_CACHE_SUFFIX):
        stripped = _lookup(
            posixpath.join(posixpath.dirname(importer_path), path[: -len(_CACHE_SUFFIX)]), ctx
        )
        if stripped is not None:
            return stripped

    return ctx.add_external_node(raw)
