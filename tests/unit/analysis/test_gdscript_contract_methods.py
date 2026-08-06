"""Godot engine callbacks are dispatched by the engine, not by a call site.

Without this, an ordinary Godot project reads as if almost every file in it
were dead: ``_ready`` / ``_process`` / ``_input`` are frequently a script's
entire content, they carry GDScript's private-by-underscore spelling, and no
other script ever calls them.
"""

from __future__ import annotations

import pytest

from repowise.core.analysis.dead_code.contract_methods import is_contract_method


class TestEngineCallbacks:
    @pytest.mark.parametrize(
        "name",
        [
            "_ready",
            "_process",
            "_physics_process",
            "_input",
            "_draw",
            "_enter_tree",
            "_notification",
        ],
    )
    def test_lifecycle_callbacks_are_contract_methods(self, name: str) -> None:
        assert is_contract_method(name, "function", "gdscript")

    def test_signal_handler_prefix(self) -> None:
        """``connect()`` with a Callable is not a call edge the graph can follow."""
        assert is_contract_method("_on_button_pressed", "function", "gdscript")

    def test_methods_count_as_well_as_functions(self) -> None:
        assert is_contract_method("_ready", "method", "gdscript")


class TestScoping:
    def test_an_ordinary_private_helper_is_not_exempt(self) -> None:
        assert not is_contract_method("_compute_path", "function", "gdscript")

    def test_a_public_method_is_not_exempt(self) -> None:
        assert not is_contract_method("take_damage", "function", "gdscript")

    def test_other_languages_are_untouched(self) -> None:
        """``_ready`` in Python is an ordinary private helper."""
        assert not is_contract_method("_ready", "function", "python")
        assert not is_contract_method("_on_click", "method", "typescript")

    def test_non_callable_kinds_are_not_exempt(self) -> None:
        assert not is_contract_method("_ready", "variable", "gdscript")
