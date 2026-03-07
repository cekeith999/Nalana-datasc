import sys
import os
import math

# Add the parent directory to sys.path to import voice_to_blender
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from voice_to_blender import try_local_rules
except ImportError as e:
    print(f"Error importing try_local_rules: {e}")
    sys.exit(1)

def test_local_rules():
    test_cases = [
        # Subsurf
        ("make it smooth", {"op": "object.modifier_add", "kwargs": {"type": "SUBSURF"}}),
        ("subdivide it", {"op": "object.modifier_add", "kwargs": {"type": "SUBSURF"}}),
        ("smooth shading modifier", {"op": "object.modifier_add", "kwargs": {"type": "SUBSURF"}}),
        
        # Bevel
        ("round the edges", {"op": "object.modifier_add", "kwargs": {"type": "BEVEL"}}),
        ("bevel corners", {"op": "object.modifier_add", "kwargs": {"type": "BEVEL"}}),
        
        # Extrude
        ("extrude this", {"op": "mesh.extrude_region_move", "kwargs": {}}),
        ("pull it out", {"op": "mesh.extrude_region_move", "kwargs": {}}),
        
        # Shade Smooth
        ("shade smooth", {"op": "object.shade_smooth", "kwargs": {}}),
        ("make it look organic", {"op": "object.shade_smooth", "kwargs": {}}),
        
        # Join
        ("join objects", {"op": "object.join", "kwargs": {}}),
        ("combine selection", {"op": "object.join", "kwargs": {}}),
        
        # Parent
        ("parent this to that", {"op": "object.parent_set", "kwargs": {}}),
        
        # Mirror
        ("mirror it", {"op": "object.modifier_add", "kwargs": {"type": "MIRROR"}}),
        ("symmetry", {"op": "object.modifier_add", "kwargs": {"type": "MIRROR"}}),
        
        # Inset
        ("inset faces", {"op": "mesh.inset_faces", "kwargs": {}}),
        
        # Loop Cut
        ("add loop cut", {"op": "mesh.loopcut_slide", "kwargs": {}}),
        
        # X-Ray
        ("see through", {"op": "view3d.toggle_xray", "kwargs": {}}),
        ("toggle xray", {"op": "view3d.toggle_xray", "kwargs": {}}),
    ]

    passed = 0
    failed = 0

    for text, expected in test_cases:
        result = try_local_rules(text)
        if result == expected:
            print(f"✅ PASSED: '{text}' -> {result}")
            passed += 1
        else:
            print(f"❌ FAILED: '{text}'")
            print(f"   Expected: {expected}")
            print(f"   Got:      {result}")
            failed += 1

    print(f"\nSummary: {passed} passed, {failed} failed.")
    
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    test_local_rules()
