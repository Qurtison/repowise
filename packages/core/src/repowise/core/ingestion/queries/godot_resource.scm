; =============================================================================
; repowise — Godot resource-format queries (.tscn / .tres / project.godot)
; tree-sitter-godot-resource
;
; These files are data, not code, so almost everything here is an *edge*
; rather than a symbol. A Godot script is attached to a node by a scene's
; [ext_resource], and a scene nests another scene the same way — without
; these captures every script in the project reads as an orphan.
;
; The one symbol kind that belongs here is an autoload: project.godot's
; [autoload] section defines a global identifier that every .gd file in the
; project can name with no import at all.
; =============================================================================

; ---------------------------------------------------------------------------
; Symbols — autoload singletons only
;
; Anchored on the section identifier, so an ordinary scene property
; (radius = 12.0) never matches.
; ---------------------------------------------------------------------------

(section
  (identifier) @_section
  (property
    (path) @symbol.name
  ) @symbol.def
  (#eq? @_section "autoload")
)

; ---------------------------------------------------------------------------
; Imports
; ---------------------------------------------------------------------------

; [ext_resource type="Script" path="res://src/enemy.gd" id="1_abc"]
;
; The section repeats this pattern once per attribute; the path predicate is
; what keeps type=/uid=/id= out. ``uid://`` references are deliberately not
; captured — the same section always carries the literal path beside them.
(section
  (identifier) @_section
  (attribute
    (identifier) @_key
    (string) @import.module
  )
  (#eq? @_section "ext_resource")
  (#eq? @_key "path")
) @import.statement

; project.godot [autoload]: GameState="*res://src/autoload/game_state.gd"
; The leading ``*`` marks the singleton as enabled; the resolver strips it.
(section
  (identifier) @_section
  (property
    (path)
    (string) @import.module
  )
  (#eq? @_section "autoload")
) @import.statement

; project.godot [application]: run/main_scene="res://scenes/main.tscn"
;
; The scene the game boots into. Nothing references it, so without this edge
; the entire reachable scene tree hangs off nothing.
(section
  (identifier) @_section
  (property
    (path) @_key
    (string) @import.module
  )
  (#eq? @_section "application")
  (#eq? @_key "run/main_scene")
) @import.statement

; ---------------------------------------------------------------------------
; Calls
;
; [connection signal="died" from="." to="." method="_on_died"] wires a
; signal to a method that no GDScript source ever calls. This capture is the
; only thing standing between those handlers and a dead-code report.
; ---------------------------------------------------------------------------

(section
  (identifier) @_section
  (attribute
    (identifier) @_key
    (string) @call.target
  )
  (#eq? @_section "connection")
  (#eq? @_key "method")
) @call.site
