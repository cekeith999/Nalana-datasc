# Cursor Rules — Nalana (Blender-first, future-friendly)

## Project context (short)
- Blender add-on today, with room to grow into other DCCs (Unity / Unreal / SolidWorks) later.
- Entry point: `Nalana/__init__.py` (the only AddonPreferences class lives here).
- Core logic currently lives in `Nalana/nalana_core/…` (providers, async pump).
- We value safety (addon never auto-disables), clarity, and incremental growth.

## Non-negotiables (do not violate)
1) **Single prefs class**: only `NALANA_AddonPreferences` in `Nalana/__init__.py` with `bl_idname="Nalana"`.
2) **Lazy heavy imports**: never import network/DCC-heavy modules at file top level. Import inside `register()`, operator `execute()`, or panel `draw()` in a `try/except` and **log** instead of raising.
3) **No network / disk I/O at import time**: no API calls or file ops outside functions.
4) **Keep addon enabled on errors**: top-level `register()` must catch and print errors; do not re-raise.
5) **Providers are Blender-lite**: provider modules should avoid `bpy` at top-level; any `bpy` usage must be inside functions.
6) **Do not restructure folders** unless the task explicitly requests it.

## “Lazy heavy imports” (what counts as heavy + how to do it)
- Heavy = big libs (requests, numpy, PIL), network clients, modules that touch env/prefs, or call Blender ops.
- Pattern:
  ```python
  # GOOD
  def register():
      import bpy
      try:
          from . import nalana_core  # lazy and guarded
      except Exception as e:
          print("[Nalana] STARTUP ERROR:", e)

  class NALANA_OT_MeshyGenerate(bpy.types.Operator):
      def execute(self, context):
          try:
              from .nalana_core.providers import meshy
              meshy.generate_from_prompt(context, prompt, cfg)
          except Exception as e:
              self.report({'ERROR'}, f"Meshy call failed: {e}")
              return {'CANCELLED'}
          return {'FINISHED'}
