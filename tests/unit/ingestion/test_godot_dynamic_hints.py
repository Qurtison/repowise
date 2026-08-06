"""Unit tests for the Godot implicit-global dynamic-hints extractor.

Covers both mechanisms it indexes: ``[autoload]`` singletons declared in
project.godot, and ``class_name`` registrations, which are how GDScript files
idiomatically refer to each other.
"""

from __future__ import annotations

from pathlib import Path

from repowise.core.ingestion.dynamic_hints.godot import GodotDynamicHints


def _extract(repo: Path):
    return GodotDynamicHints().extract(repo)


def _project(dirpath: Path, autoloads: str) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "project.godot").write_text(
        f'config_version=5\n\n[application]\n\nconfig/name="T"\n\n[autoload]\n\n{autoloads}\n'
    )


class TestAutoloadReferences:
    def test_script_naming_an_autoload_gets_an_edge(self, tmp_path: Path) -> None:
        _project(tmp_path, 'GameState="*res://src/game_state.gd"')
        (tmp_path / "src").mkdir()
        (tmp_path / "src/game_state.gd").write_text("extends Node\nvar score := 0\n")
        (tmp_path / "src/enemy.gd").write_text(
            "extends Node\n\nfunc go():\n\tGameState.score += 1\n"
        )

        edges = _extract(tmp_path)
        assert any(
            e.source == "src/enemy.gd"
            and e.target == "src/game_state.gd"
            and e.edge_type == "dynamic_uses"
            and e.hint_source == "godot:autoload"
            for e in edges
        )

    def test_scene_naming_an_autoload_gets_an_edge(self, tmp_path: Path) -> None:
        _project(tmp_path, 'Audio="*res://src/audio.gd"')
        (tmp_path / "src").mkdir()
        (tmp_path / "src/audio.gd").write_text("extends Node\n")
        (tmp_path / "src/hud.tscn").write_text('[gd_scene]\n\n[node name="Audio"]\n')

        edges = _extract(tmp_path)
        assert any(e.source == "src/hud.tscn" and e.target == "src/audio.gd" for e in edges)

    def test_the_singleton_does_not_use_itself(self, tmp_path: Path) -> None:
        _project(tmp_path, 'GameState="*res://src/game_state.gd"')
        (tmp_path / "src").mkdir()
        (tmp_path / "src/game_state.gd").write_text("extends Node\n## GameState holds the score.\n")

        assert [e for e in _extract(tmp_path) if e.source == e.target] == []
        assert [e for e in _extract(tmp_path) if e.source == "src/game_state.gd"] == []

    def test_disabled_autoload_is_still_linked(self, tmp_path: Path) -> None:
        """No leading ``*`` means disabled, not absent — references are real."""
        _project(tmp_path, 'Debug="res://src/debug.gd"')
        (tmp_path / "src").mkdir()
        (tmp_path / "src/debug.gd").write_text("extends Node\n")
        (tmp_path / "src/main.gd").write_text("extends Node\n\nfunc go():\n\tDebug.log('x')\n")

        assert any(e.target == "src/debug.gd" for e in _extract(tmp_path))

    def test_unrelated_script_gets_no_edge(self, tmp_path: Path) -> None:
        _project(tmp_path, 'GameState="*res://src/game_state.gd"')
        (tmp_path / "src").mkdir()
        (tmp_path / "src/game_state.gd").write_text("extends Node\n")
        (tmp_path / "src/quiet.gd").write_text("extends Node\n\nfunc go():\n\tpass\n")

        assert [e for e in _extract(tmp_path) if e.source == "src/quiet.gd"] == []

    def test_substring_of_a_longer_identifier_does_not_match(self, tmp_path: Path) -> None:
        _project(tmp_path, 'Audio="*res://src/audio.gd"')
        (tmp_path / "src").mkdir()
        (tmp_path / "src/audio.gd").write_text("extends Node\n")
        (tmp_path / "src/other.gd").write_text("extends Node\n\nvar AudioStreamThing := 1\n")

        assert [e for e in _extract(tmp_path) if e.source == "src/other.gd"] == []


class TestProjectScoping:
    def test_res_paths_resolve_against_the_project_dir(self, tmp_path: Path) -> None:
        _project(tmp_path / "game", 'GameState="*res://src/game_state.gd"')
        (tmp_path / "game/src").mkdir(parents=True)
        (tmp_path / "game/src/game_state.gd").write_text("extends Node\n")
        (tmp_path / "game/src/enemy.gd").write_text("extends Node\n\nfunc go():\n\tGameState.x\n")

        edges = _extract(tmp_path)
        assert any(
            e.source == "game/src/enemy.gd" and e.target == "game/src/game_state.gd" for e in edges
        )

    def test_sibling_project_does_not_see_the_autoload(self, tmp_path: Path) -> None:
        _project(tmp_path / "alpha", 'GameState="*res://src/game_state.gd"')
        (tmp_path / "alpha/src").mkdir(parents=True)
        (tmp_path / "alpha/src/game_state.gd").write_text("extends Node\n")
        (tmp_path / "beta").mkdir()
        (tmp_path / "beta/thing.gd").write_text("extends Node\n\nfunc go():\n\tGameState.x\n")

        assert [e for e in _extract(tmp_path) if e.source == "beta/thing.gd"] == []

    def test_no_autoload_section_emits_nothing(self, tmp_path: Path) -> None:
        (tmp_path / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="T"\n'
        )
        (tmp_path / "main.gd").write_text("extends Node\n")

        assert _extract(tmp_path) == []


class TestClassNameGlobals:
    def test_a_class_name_reference_links_without_any_import(self, tmp_path: Path) -> None:
        """The idiomatic GDScript cross-file reference carries no path at all."""
        _project(tmp_path, 'GameState="*res://src/game_state.gd"')
        (tmp_path / "src").mkdir()
        (tmp_path / "src/game_state.gd").write_text("extends Node\n")
        (tmp_path / "src/armor_def.gd").write_text("class_name ArmorDef\nextends Resource\n")
        (tmp_path / "src/loadout.gd").write_text(
            "extends Node\n\nfunc make() -> ArmorDef:\n\treturn ArmorDef.new()\n"
        )

        edges = _extract(tmp_path)
        assert any(
            e.source == "src/loadout.gd"
            and e.target == "src/armor_def.gd"
            and e.hint_source == "godot:class_name"
            for e in edges
        )

    def test_the_declaring_script_is_not_its_own_user(self, tmp_path: Path) -> None:
        (tmp_path / "armor_def.gd").write_text(
            "class_name ArmorDef\nextends Resource\n\nfunc copy() -> ArmorDef:\n\treturn null\n"
        )
        assert [e for e in _extract(tmp_path) if e.source == e.target] == []

    def test_a_scene_naming_the_class_links_too(self, tmp_path: Path) -> None:
        (tmp_path / "armor_def.gd").write_text("class_name ArmorDef\nextends Resource\n")
        (tmp_path / "loadout.tres").write_text('[gd_resource]\n\n[resource]\nkind = "ArmorDef"\n')

        edges = _extract(tmp_path)
        assert any(e.source == "loadout.tres" and e.target == "armor_def.gd" for e in edges)

    def test_a_longer_identifier_is_not_a_match(self, tmp_path: Path) -> None:
        (tmp_path / "armor.gd").write_text("class_name Armor\nextends Resource\n")
        (tmp_path / "other.gd").write_text("extends Node\n\nvar ArmorDefinition := 1\n")

        assert [e for e in _extract(tmp_path) if e.source == "other.gd"] == []

    def test_a_script_without_class_name_registers_nothing(self, tmp_path: Path) -> None:
        (tmp_path / "helper.gd").write_text("extends Node\n\nfunc go():\n\tpass\n")
        (tmp_path / "user.gd").write_text("extends Node\n\nfunc go():\n\thelper()\n")

        assert _extract(tmp_path) == []

    def test_a_commented_class_name_does_not_register(self, tmp_path: Path) -> None:
        (tmp_path / "old.gd").write_text("extends Node\n#class_name Legacy\n")
        (tmp_path / "user.gd").write_text("extends Node\n\nvar x = Legacy\n")

        assert _extract(tmp_path) == []


class TestAutoloadTableCompleteness:
    def test_every_autoload_is_linked_not_just_the_first(self, tmp_path: Path) -> None:
        """All autoloads share one [autoload] section — an early version of
        the scene-file query collapsed them to whichever came first."""
        _project(
            tmp_path,
            'GameState="*res://a.gd"\nAudioDirector="*res://b.gd"\nSpawnDirector="*res://c.gd"',
        )
        for stem in ("a", "b", "c"):
            (tmp_path / f"{stem}.gd").write_text("extends Node\n")
        (tmp_path / "user.gd").write_text(
            "extends Node\n\nfunc go():\n\tGameState.x\n\tAudioDirector.y\n\tSpawnDirector.z\n"
        )

        targets = {e.target for e in _extract(tmp_path) if e.source == "user.gd"}
        assert targets == {"a.gd", "b.gd", "c.gd"}
