# Nalana – Dev Notes (Source of Truth)

## What this project is
Blender-first addon with room to expand to other DCCs (Unity/Unreal/SolidWorks).
Core principles: one prefs class at top-level; lazy imports; never auto-disable.

## Folder roles (today)
Nalana/            # Blender addon entrypoint (only prefs class lives here)
  __init__.py               # safe stub, register/unregister, minimal ops/panels
  nalana_core/                 # current implementation details (providers, async pump)
    providers/
      meshy.py              # MeshyProvider and generate_from_prompt wrapper

## Non-negotiables
- Only one AddonPreferences class: NALANA_AddonPreferences, bl_idname="Nalana".
- Heavy imports only inside register()/execute()/draw() or background threads.
- UI must not crash on missing dependencies; log errors, keep addon enabled.

## Extensibility hooks (future)
- core/ (host-agnostic) will hold tiny interfaces + registry when needed.
- hosts/ will add adapters (blender_addon first, later unity/unreal/solidworks).
- providers/ will hold API clients (meshy first, later others).

## Reload snippet (pin in Blender console)
import bpy, importlib, sys
try: bpy.ops.preferences.addon_disable(module="Nalana")
except: pass
mod = sys.modules.get("Nalana")
if mod:
    for n in ("NALANA_PT_MeshyStatus","NALANA_PT_MeshyTools","NALANA_OT_MeshyGenerate","NALANA_AddonPreferences"):
        c = getattr(mod, n, None)
        if c:
            try: bpy.utils.unregister_class(c)
            except: pass
    try:
        if hasattr(bpy.types.WindowManager,"nalana_meshy_prompt"):
            del bpy.types.WindowManager.nalana_meshy_prompt
    except: pass
if "Nalana" in sys.modules:
    importlib.invalidate_caches(); mod = importlib.reload(sys.modules["Nalana"])
else:
    import Nalana as mod
bpy.ops.preferences.addon_enable(module="Nalana")
print("Enabled:", "Nalana" in bpy.context.preferences.addons)
