"""Unit tests for GDScript and Godot resource-format parsing.

Tests parse inline byte strings so no filesystem I/O is needed.

The Godot grammars ship in the optional ``godot`` extra (neither is on PyPI —
see pyproject.toml), so these skip rather than fail on a venv installed
without it. The parser degrades the same way at runtime: an absent grammar
means empty symbols, never a crash.
"""

from __future__ import annotations

import pytest

from repowise.core.ingestion.parser import ASTParser
from tests.unit.ingestion.parser._helpers import _make_file_info

pytest.importorskip("tree_sitter_gdscript", reason="run `uv pip install '.[godot]'`")
pytest.importorskip("tree_sitter_godot_resource", reason="run `uv pip install '.[godot]'`")


ENEMY_SOURCE = b"""class_name Enemy
extends CharacterBody2D
## An enemy that chases the player.

const Bullet := preload("res://src/enemies/bullet.gd")
const MAX_HP: int = 100

signal died(who: Node)

enum State { IDLE, CHASE }

@export var speed: float = 200.0
var _hp := MAX_HP

class Inner extends RefCounted:
\tfunc helper() -> void:
\t\tpass

func _ready() -> void:
\tGameState.add_score(1)
\tvar cfg = load("res://data/config.tres")

func take_damage(n: int) -> void:
\t_hp -= n
\tif _hp <= 0:
\t\tdied.emit(self)
\t\tvar local_only := 1
"""

SCENE_SOURCE = b"""[gd_scene load_steps=2 format=3 uid="uid://bxyz"]

[ext_resource type="Script" path="res://src/enemies/enemy.gd" id="1_abc"]
[ext_resource type="PackedScene" uid="uid://c8q" path="res://scenes/hit.tscn" id="2_def"]

[sub_resource type="CircleShape2D" id="CircleShape2D_1"]
radius = 12.0

[node name="Enemy" type="CharacterBody2D"]
script = ExtResource("1_abc")
speed = 240.0

[connection signal="died" from="." to="." method="_on_died"]
"""

PROJECT_SOURCE = b"""config_version=5

[application]

config/name="Test Game"
run/main_scene="res://scenes/main.tscn"

[autoload]

GameState="*res://src/autoload/game_state.gd"
"""


class TestGDScriptSymbols:
    def test_class_name_becomes_the_script_class(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        classes = [s.name for s in result.symbols if s.kind == "class"]
        assert "Enemy" in classes

    def test_inner_class_and_its_method(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        by_name = {s.name: s for s in result.symbols}
        assert by_name["Inner"].kind == "class"
        assert by_name["helper"].kind == "method"
        assert by_name["helper"].parent_name == "Inner"

    def test_signal_is_callable_so_emit_can_reach_it(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        died = next(s for s in result.symbols if s.name == "died")
        assert died.kind == "function"

    def test_enum_const_and_exported_var(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        kinds = {s.name: s.kind for s in result.symbols}
        assert kinds["State"] == "enum"
        assert kinds["MAX_HP"] == "constant"
        assert kinds["speed"] == "variable"

    def test_function_local_var_is_not_a_symbol(self, parser: ASTParser) -> None:
        """The var/const patterns are container-anchored, as in python.scm."""
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        assert "local_only" not in {s.name for s in result.symbols}
        assert "cfg" not in {s.name for s in result.symbols}

    def test_leading_underscore_is_private(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        by_name = {s.name: s for s in result.symbols}
        assert by_name["_hp"].visibility == "private"
        assert by_name["_ready"].visibility == "private"
        assert by_name["take_damage"].visibility == "public"

    def test_script_without_class_name_gets_a_synthetic_class(self, parser: ASTParser) -> None:
        source = b"extends Node\n\nfunc go() -> void:\n\tpass\n"
        result = parser.parse_file(_make_file_info("src/enemy_spawner.gd", "gdscript"), source)
        classes = [s for s in result.symbols if s.kind == "class"]
        assert [c.name for c in classes] == ["EnemySpawner"]
        assert classes[0].signature == "extends Node"

    def test_class_name_script_gets_no_synthetic_duplicate(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        assert [s.name for s in result.symbols if s.kind == "class"].count("Enemy") == 1


class TestGDScriptDocComments:
    def test_double_hash_after_header_is_the_script_docstring(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        assert result.docstring == "An enemy that chases the player."

    def test_blank_line_hands_the_comment_to_the_member(self, parser: ASTParser) -> None:
        source = b"class_name Mini\nextends Enemy\n\n## Doc for a member.\nvar rage := 3\n"
        result = parser.parse_file(_make_file_info("src/mini.gd", "gdscript"), source)
        assert result.docstring is None
        rage = next(s for s in result.symbols if s.name == "rage")
        assert rage.docstring == "Doc for a member."

    def test_single_hash_is_not_documentation(self, parser: ASTParser) -> None:
        source = b"extends Node\n# Just a note.\n\nfunc go() -> void:\n\tpass\n"
        result = parser.parse_file(_make_file_info("src/thing.gd", "gdscript"), source)
        assert result.docstring is None


class TestGDScriptImports:
    def test_preload_and_load_paths(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        modules = {i.module_path for i in result.imports}
        # Quotes are stripped by the parser before the resolver sees them.
        assert "res://src/enemies/bullet.gd" in modules
        assert "res://data/config.tres" in modules

    def test_extends_by_path(self, parser: ASTParser) -> None:
        source = b'extends "res://src/base_thing.gd"\n\nfunc go() -> void:\n\tpass\n'
        result = parser.parse_file(_make_file_info("src/boss.gd", "gdscript"), source)
        assert "res://src/base_thing.gd" in {i.module_path for i in result.imports}

    def test_scene_change_is_a_dependency(self, parser: ASTParser) -> None:
        source = b'extends Node\n\nfunc go():\n\tget_tree().change_scene_to_file("res://scenes/next.tscn")\n'
        result = parser.parse_file(_make_file_info("src/menu.gd", "gdscript"), source)
        assert "res://scenes/next.tscn" in {i.module_path for i in result.imports}


class TestGDScriptHeritage:
    def test_file_scope_extends_reaches_the_class_name(self, parser: ASTParser) -> None:
        source = b"class_name Mini\nextends Enemy\n\nfunc go() -> void:\n\tpass\n"
        result = parser.parse_file(_make_file_info("src/mini.gd", "gdscript"), source)
        assert [(h.child_name, h.parent_name) for h in result.heritage] == [("Mini", "Enemy")]

    def test_extends_before_class_name_still_matches(self, parser: ASTParser) -> None:
        """Godot accepts either order at file scope."""
        source = b"extends Enemy\nclass_name Mini\n\nfunc go() -> void:\n\tpass\n"
        result = parser.parse_file(_make_file_info("src/mini.gd", "gdscript"), source)
        assert [(h.child_name, h.parent_name) for h in result.heritage] == [("Mini", "Enemy")]

    def test_engine_base_class_is_not_an_edge(self, parser: ASTParser) -> None:
        """``extends CharacterBody2D`` names an engine type, never a repo file."""
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        assert [h.parent_name for h in result.heritage if h.child_name == "Enemy"] == []

    def test_path_form_extends_reduces_to_the_base_stem(self, parser: ASTParser) -> None:
        source = b'class_name Boss\nextends "res://src/base_thing.gd"\n\nfunc go():\n\tpass\n'
        result = parser.parse_file(_make_file_info("src/boss.gd", "gdscript"), source)
        assert [(h.child_name, h.parent_name) for h in result.heritage] == [("Boss", "base_thing")]


class TestGDScriptCalls:
    def test_autoload_method_call_keeps_its_receiver(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        calls = {(c.target_name, c.receiver_name) for c in result.calls}
        assert ("add_score", "GameState") in calls

    def test_signal_emit_names_the_signal_as_receiver(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        assert ("emit", "died") in {(c.target_name, c.receiver_name) for c in result.calls}

    def test_method_calls_are_not_double_counted(self, parser: ASTParser) -> None:
        """One receiver-less pattern used to fire alongside every method call."""
        result = parser.parse_file(
            _make_file_info("src/enemies/enemy.gd", "gdscript"), ENEMY_SOURCE
        )
        targets = [c.target_name for c in result.calls]
        assert targets.count("add_score") == 1

    def test_builtins_are_not_calls(self, parser: ASTParser) -> None:
        source = b"extends Node\n\nfunc go():\n\tprint(1)\n\tmy_helper()\n"
        result = parser.parse_file(_make_file_info("src/thing.gd", "gdscript"), source)
        targets = [c.target_name for c in result.calls]
        assert "print" not in targets
        assert "my_helper" in targets


class TestGodotResourceFormat:
    def test_scene_ext_resources_become_imports(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("scenes/main.tscn", "godot_resource"), SCENE_SOURCE
        )
        modules = {i.module_path for i in result.imports}
        assert "res://src/enemies/enemy.gd" in modules
        assert "res://scenes/hit.tscn" in modules

    def test_uid_and_type_attributes_are_not_imports(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("scenes/main.tscn", "godot_resource"), SCENE_SOURCE
        )
        modules = {i.module_path for i in result.imports}
        assert not any(m.startswith("uid://") for m in modules)
        assert "Script" not in modules

    def test_connection_method_is_a_call(self, parser: ASTParser) -> None:
        """The only thing standing between a wired handler and a dead-code report."""
        result = parser.parse_file(
            _make_file_info("scenes/main.tscn", "godot_resource"), SCENE_SOURCE
        )
        assert "_on_died" in {c.target_name for c in result.calls}

    def test_scene_node_properties_are_not_symbols(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("scenes/main.tscn", "godot_resource"), SCENE_SOURCE
        )
        assert [s.name for s in result.symbols] == []

    def test_autoload_is_a_symbol_and_an_import(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("project.godot", "godot_resource"), PROJECT_SOURCE
        )
        assert [(s.name, s.kind) for s in result.symbols] == [("GameState", "constant")]
        assert "*res://src/autoload/game_state.gd" in {i.module_path for i in result.imports}

    def test_main_scene_is_an_import(self, parser: ASTParser) -> None:
        """Nothing else references the boot scene; without this it has no anchor."""
        result = parser.parse_file(
            _make_file_info("project.godot", "godot_resource"), PROJECT_SOURCE
        )
        assert "res://scenes/main.tscn" in {i.module_path for i in result.imports}

    def test_ordinary_application_settings_are_not_imports(self, parser: ASTParser) -> None:
        result = parser.parse_file(
            _make_file_info("project.godot", "godot_resource"), PROJECT_SOURCE
        )
        assert "Test Game" not in {i.module_path for i in result.imports}
