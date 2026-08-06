"""LanguageSpec for Godot's resource format — scenes, resources, project file.

``.tscn`` (scene), ``.tres`` (resource), ``.escn`` (Blender-exported scene)
and ``project.godot`` all share one INI-like grammar, so one spec and one
grammar cover all of them.

These files are not code, but they are the wiring of a Godot project: a
scene's ``[ext_resource]`` entries are what attach scripts to nodes and
nest scenes inside each other, and ``project.godot``'s ``[autoload]``
section is what makes a script a global singleton. Skipping them leaves
every script in the repo looking like an orphan, which is why this is a
parsed language rather than a passthrough one.
"""

from ..spec import LanguageSpec

SPEC = LanguageSpec(
    tag="godot_resource",
    display_name="Godot Resource",
    # ext_resource paths are literal ``res://`` strings — exact resolution.
    import_support="full",
    extensions=frozenset({".tscn", ".tres", ".escn"}),
    special_filenames=frozenset({"project.godot"}),
    # Data, not code: excluded from code-line counts and complexity, but
    # still parsed (is_passthrough stays False) for its resource edges.
    is_code=False,
    grammar_package="tree_sitter_godot_resource",
    scm_file="godot_resource.scm",
    manifest_files=("project.godot",),
    blocked_dirs=(".godot", ".import"),
    blocked_extensions=(".import",),
    color_hex="#478CBF",
)
