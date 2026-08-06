; =============================================================================
; repowise — GDScript symbol and import queries
; tree-sitter-gdscript (Godot 4 syntax; Godot 3 scripts parse as a subset)
;
; A .gd file IS a class. ``class_name`` names it and ``extends`` sits beside
; that at file scope rather than inside a class node — see
; extractors/heritage/gdscript.py for how the two are joined, and
; synthetic_symbols/gdscript_script.py for the class symbol minted when a
; script declares no ``class_name`` at all.
;
; Capture name conventions are shared across all query files; see python.scm.
; =============================================================================

; ---------------------------------------------------------------------------
; Symbols
; ---------------------------------------------------------------------------

; class_name Enemy
(class_name_statement
  name: (name) @symbol.name
) @symbol.def

; Inner class: class Inner extends RefCounted:
(class_definition
  name: (name) @symbol.name
) @symbol.def

; func foo(a, b) -> void:  — at file scope a function, inside a
; class_definition a method (parent_extraction="nesting" decides).
(function_definition
  name: (name) @symbol.name
  parameters: (parameters) @symbol.params
) @symbol.def

; signal died(who: Node)
;
; A signal is a declared, named member that other files reach by name —
; ``died.emit()`` from GDScript and ``[connection signal="died" …]`` from a
; scene file. Recording it as a callable is what lets both of those land on
; it; the signature keeps it readable as a signal in the docs.
(signal_statement
  name: (name) @symbol.name
) @symbol.def

; enum State { IDLE, CHASE }
(enum_definition
  name: (name) @symbol.name
) @symbol.def

; Script-scoped const / var, and the same at class scope. Both are anchored
; to their container so a function-local ``var i := 0`` never becomes a
; symbol — the same guard python.scm applies to module-level assignments.
;
; The optional (annotations) capture carries @export / @onready / @rpc so
; the dead-code pass can see that the engine, not a call site, drives them.
(source
  (const_statement
    name: (name) @symbol.name
  ) @symbol.def
)

(source
  (variable_statement
    (annotations)? @symbol.modifiers
    name: (name) @symbol.name
  ) @symbol.def
)

(class_body
  (const_statement
    name: (name) @symbol.name
  ) @symbol.def
)

(class_body
  (variable_statement
    (annotations)? @symbol.modifiers
    name: (name) @symbol.name
  ) @symbol.def
)

; ---------------------------------------------------------------------------
; Imports
;
; GDScript has no import statement. A script reaches another file by loading
; a ``res://`` path (project-root absolute) or a relative path, which the
; resolver maps to a repo file. Captured as the raw string; the parser strips
; the quotes before the resolver sees it.
; ---------------------------------------------------------------------------

; const Bullet = preload("res://src/weapons/bullet.gd")
(call
  (identifier) @_load_fn
  (arguments (string) @import.module)
  (#eq? @_load_fn "preload")
) @import.statement

; var cfg = load("res://data/config.tres")
(call
  (identifier) @_load_fn
  (arguments (string) @import.module)
  (#eq? @_load_fn "load")
) @import.statement

; ResourceLoader.load("res://…") / ResourceLoader.load_threaded_request("res://…")
(attribute
  (identifier) @_loader
  (attribute_call
    (identifier) @_load_fn
    (arguments (string) @import.module))
  (#eq? @_loader "ResourceLoader")
) @import.statement

; get_tree().change_scene_to_file("res://scenes/next.tscn") — a scene swap is
; a real dependency on that scene, and nothing else in the file references it.
(attribute
  (attribute_call
    (identifier) @_scene_fn
    (arguments (string) @import.module))
  (#eq? @_scene_fn "change_scene_to_file")
) @import.statement

; extends "res://src/base_thing.gd" — path-form inheritance, used when the
; base script declares no class_name.
(extends_statement
  (string) @import.module
) @import.statement

; ---------------------------------------------------------------------------
; Calls
; ---------------------------------------------------------------------------

; foo(a, b) — also covers constructor-ish ``MyClass.new()`` receivers below.
(call
  (identifier) @call.target
  (arguments) @call.arguments
) @call.site

; obj.method(a, b) / Autoload.method(a, b)
;
; This also covers signal emission — ``died.emit(self)`` reads as a call to
; ``emit`` on receiver ``died``, which is exactly the edge that keeps a
; connected signal from looking dead.
;
; Receivers that are themselves calls (``get_tree().change_scene_to_file(…)``)
; are deliberately not matched: a second, receiver-less pattern would fire on
; every match above as well, doubling each ordinary method call. The one such
; form that carries a real dependency — change_scene_to_file — is captured as
; an import instead.
(attribute
  (identifier) @call.receiver
  (attribute_call
    (identifier) @call.target
    (arguments) @call.arguments)
) @call.site
