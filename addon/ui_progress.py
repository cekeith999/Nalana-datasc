# addon/ui_progress.py
import os, sys, json, bpy

# --- find repo root (folder containing 'nalana_core' and 'addon') ---
HERE = os.path.abspath(os.path.dirname(__file__))
def _find_repo_root(start_dir: str, target: str = "nalana_core", max_up: int = 6):
    cur = start_dir
    for _ in range(max_up):
        if os.path.isdir(os.path.join(cur, target)): return cur
        parent = os.path.dirname(cur)
        if parent == cur: break
        cur = parent
    return None

REPO_ROOT = _find_repo_root(HERE) or HERE
PROGRESS_PATH = os.path.join(REPO_ROOT, "logs", "progress.json")

# --- timer plumbing ---
_TIMER_RUNNING = False

def _tag_redraw():
    # force 3D view & UI to repaint
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {"VIEW_3D", "PROPERTIES", "PREFERENCES"}:
                for region in area.regions:
                    if region.type == 'WINDOW':
                        area.tag_redraw()

def _progress_timer():
    wm = bpy.context.window_manager
    # read JSON if present
    try:
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        wm.nalana_job_id = str(data.get("job_id", ""))
        wm.nalana_state = str(data.get("state", "unknown"))
        p = int(data.get("progress", 0))
        wm.nalana_progress = max(0, min(100, p))
    except FileNotFoundError:
        # nothing to show yet; leave values as-is
        pass
    except Exception as e:
        wm.nalana_state = f"error: {e!s}"[:128]

    _tag_redraw()
    return 0.5  # call again in 0.5s

def start_monitor():
    global _TIMER_RUNNING
    if not _TIMER_RUNNING:
        bpy.app.timers.register(_progress_timer, first_interval=0.1, persistent=True)
        _TIMER_RUNNING = True
    return {'FINISHED'}

def stop_monitor():
    global _TIMER_RUNNING
    if _TIMER_RUNNING:
        try:
            bpy.app.timers.unregister(_progress_timer)
        except Exception:
            pass
        _TIMER_RUNNING = False
    return {'FINISHED'}

# --- props, operators, panel ---
def _ensure_props():
    wm = bpy.types.WindowManager
    if not hasattr(wm, "nalana_progress"):
        wm.nalana_progress = bpy.props.IntProperty(
            name="Progress", min=0, max=100, default=0
        )
    if not hasattr(wm, "nalana_job_id"):
        wm.nalana_job_id = bpy.props.StringProperty(name="Job ID", default="")
    if not hasattr(wm, "nalana_state"):
        wm.nalana_state = bpy.props.StringProperty(name="State", default="idle")

class NALANA_OT_StartMonitor(bpy.types.Operator):
    bl_idname = "nalana.start_monitor"
    bl_label  = "Start Monitor"
    bl_description = "Start reading logs/progress.json periodically"
    def execute(self, ctx): return start_monitor()

class NALANA_OT_StopMonitor(bpy.types.Operator):
    bl_idname = "nalana.stop_monitor"
    bl_label  = "Stop Monitor"
    bl_description = "Stop reading progress"
    def execute(self, ctx): return stop_monitor()

class NALANA_PT_Progress(bpy.types.Panel):
    bl_label = "Nalana • Progress"
    bl_idname = "NALANA_PT_Progress"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Nalana"   # <- change from "Nalana" to "Nalana"


    def draw(self, context):
        wm = context.window_manager
        col = self.layout.column(align=True)
        col.label(text=f"Job: {wm.nalana_job_id or '—'}")
        col.label(text=f"State: {wm.nalana_state or '—'}")
        row = col.row(align=True)
        row.prop(wm, "nalana_progress", text="Progress")
        col = self.layout.column(align=True)
        if not _TIMER_RUNNING:
            col.operator("nalana.start_monitor", icon="PLAY")
        else:
            col.operator("nalana.stop_monitor", icon="PAUSE")

_CLASSES = (NALANA_OT_StartMonitor, NALANA_OT_StopMonitor, NALANA_PT_Progress)

def register():
    _ensure_props()
    for c in _CLASSES: bpy.utils.register_class(c)

def unregister():
    stop_monitor()
    for c in reversed(_CLASSES): 
        try: bpy.utils.unregister_class(c)
        except Exception: pass
