"""Unit tests for the Godot ``res://`` import resolver.

Parser contract
---------------
``parser.py`` strips surrounding quotes from the captured ``@import.module``
text before calling a resolver, so every path here is passed unquoted —
``preload("res://a.gd")`` reaches the resolver as ``res://a.gd``. The
``[autoload]`` marker (``*``) is NOT a quote and does survive to the
resolver, so those tests keep it.
"""

from __future__ import annotations

import networkx as nx

from repowise.core.ingestion.resolvers.context import ResolverContext
from repowise.core.ingestion.resolvers.godot import resolve_godot_import


def _ctx(paths: set[str]) -> ResolverContext:
    stem_map: dict[str, list[str]] = {}
    for p in paths:
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        stem_map.setdefault(stem, []).append(p)
    return ResolverContext(path_set=paths, stem_map=stem_map, graph=nx.DiGraph())


class TestResAbsolute:
    def test_preload_from_project_root(self) -> None:
        ctx = _ctx({"project.godot", "src/enemies/enemy.gd", "src/main.gd"})
        got = resolve_godot_import("res://src/enemies/enemy.gd", "src/main.gd", ctx)
        assert got == "src/enemies/enemy.gd"

    def test_scene_ext_resource(self) -> None:
        ctx = _ctx({"project.godot", "scenes/main.tscn", "src/player.gd"})
        got = resolve_godot_import("res://src/player.gd", "scenes/main.tscn", ctx)
        assert got == "src/player.gd"

    def test_unindexed_target_becomes_external(self) -> None:
        """An asset the traverser skipped is recorded, never dropped."""
        ctx = _ctx({"project.godot", "scenes/main.tscn"})
        got = resolve_godot_import("res://art/player.png", "scenes/main.tscn", ctx)
        assert got == "external:res://art/player.png"


class TestProjectRoot:
    def test_project_below_repo_root(self) -> None:
        """``res://`` is the project root, which need not be the repo root."""
        ctx = _ctx({"game/project.godot", "game/src/enemy.gd", "game/scenes/main.tscn"})
        got = resolve_godot_import("res://src/enemy.gd", "game/scenes/main.tscn", ctx)
        assert got == "game/src/enemy.gd"

    def test_sibling_projects_do_not_cross(self) -> None:
        ctx = _ctx(
            {
                "alpha/project.godot",
                "alpha/src/thing.gd",
                "beta/project.godot",
                "beta/src/thing.gd",
                "beta/main.tscn",
            }
        )
        got = resolve_godot_import("res://src/thing.gd", "beta/main.tscn", ctx)
        assert got == "beta/src/thing.gd"

    def test_nested_project_wins_over_enclosing(self) -> None:
        """Deepest project.godot governs — an addon demo inside a game."""
        ctx = _ctx(
            {
                "project.godot",
                "src/thing.gd",
                "addons/plugin/demo/project.godot",
                "addons/plugin/demo/src/thing.gd",
                "addons/plugin/demo/demo.tscn",
            }
        )
        got = resolve_godot_import("res://src/thing.gd", "addons/plugin/demo/demo.tscn", ctx)
        assert got == "addons/plugin/demo/src/thing.gd"

    def test_no_project_file_falls_back_to_repo_root(self) -> None:
        """A standalone addon repo has no project.godot of its own."""
        ctx = _ctx({"addons/thing/thing.gd", "addons/thing/panel.tscn"})
        got = resolve_godot_import("res://addons/thing/thing.gd", "addons/thing/panel.tscn", ctx)
        assert got == "addons/thing/thing.gd"


class TestAutoload:
    def test_enabled_marker_is_stripped(self) -> None:
        ctx = _ctx({"project.godot", "src/autoload/game_state.gd"})
        got = resolve_godot_import("*res://src/autoload/game_state.gd", "project.godot", ctx)
        assert got == "src/autoload/game_state.gd"

    def test_disabled_autoload_still_resolves(self) -> None:
        ctx = _ctx({"project.godot", "src/autoload/debug.gd"})
        got = resolve_godot_import("res://src/autoload/debug.gd", "project.godot", ctx)
        assert got == "src/autoload/debug.gd"


class TestRelative:
    def test_relative_preload(self) -> None:
        ctx = _ctx({"project.godot", "src/shared/util.gd", "src/enemies/enemy.gd"})
        got = resolve_godot_import("../shared/util.gd", "src/enemies/enemy.gd", ctx)
        assert got == "src/shared/util.gd"

    def test_sibling_preload(self) -> None:
        ctx = _ctx({"project.godot", "src/enemies/bullet.gd", "src/enemies/enemy.gd"})
        got = resolve_godot_import("bullet.gd", "src/enemies/enemy.gd", ctx)
        assert got == "src/enemies/bullet.gd"


class TestUnresolvable:
    def test_uid_is_never_guessed(self) -> None:
        """A UID is an opaque handle; the same [ext_resource] carries the path."""
        ctx = _ctx({"project.godot", "scenes/main.tscn", "src/enemy.gd"})
        got = resolve_godot_import("uid://bxyz123abc", "scenes/main.tscn", ctx)
        assert got == "external:uid://bxyz123abc"

    def test_user_path_is_external(self) -> None:
        ctx = _ctx({"project.godot", "src/save.gd"})
        got = resolve_godot_import("user://save.dat", "src/save.gd", ctx)
        assert got == "external:user://save.dat"

    def test_empty_path(self) -> None:
        ctx = _ctx({"project.godot"})
        assert resolve_godot_import("", "project.godot", ctx) is None
