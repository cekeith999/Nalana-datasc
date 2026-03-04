"""
Gemini Live runner for SpeechToBlender.

This script is executed by the bundled runtime (stb_runtime/python/python.exe)
as a separate process. It:

- Streams microphone audio to Gemini Live API
- Receives TEXT responses as Python code
- Optionally triggers instant primitives for simple keywords (God Mode)
- Sends all actions to Blender via XML-RPC `execute` calls

Environment variables (set by the Blender add-on):
- STB_GEMINI_API_KEY : Gemini API key
- STB_LIVE_CONTEXT   : System prompt / scene context (optional)
- STB_RPC_URL        : XML-RPC endpoint (default: http://127.0.0.1:8765/RPC2)
"""

import asyncio
import os
import queue
import sys
from xmlrpc.client import ServerProxy

import google.genai as genai
import pyaudio


# Phase 5: keywords that trigger instant PREDICT (must match intent of UI)
PREDICT_KEYWORDS = ("cube", "sphere", "cylinder", "plane", "cone", "torus", "camera", "light", "iphone")

PREDICT_CODE_MAP = {
    "cube": "bpy.ops.mesh.primitive_cube_add()",
    "sphere": "bpy.ops.mesh.primitive_uv_sphere_add()",
    "cylinder": "bpy.ops.mesh.primitive_cylinder_add()",
    "plane": "bpy.ops.mesh.primitive_plane_add()",
    "cone": "bpy.ops.mesh.primitive_cone_add()",
    "torus": "bpy.ops.mesh.primitive_torus_add()",
    "camera": "bpy.ops.object.camera_add()",
    "light": "bpy.ops.object.light_add(type='POINT')",
    "iphone": "bpy.ops.mesh.primitive_cube_add(); bpy.context.object.scale = (0.036, 0.074, 0.004)",
}

# Basic safety: block obviously dangerous patterns before sending to Blender
CODE_BLACKLIST = (
    "import os",
    "import sys",
    "os.",
    "sys.",
    "shutil",
    "sys.exit",
    "quit_blender",
    "quit(",
    "exit(",
    "open(",
    "__import__",
    "eval(",
    "exec(",
    "compile(",
    "subprocess",
    "remove(",
)


async def _run_live_session(api_key: str, system_instruction: str, rpc_url: str):
    """Main async coroutine: handles mic + Gemini Live + XML-RPC back to Blender."""
    print("[LiveRunner] ========================================")
    print("[LiveRunner] SpeechToBlender - Gemini Live Runner")
    print("[LiveRunner] ========================================")
    print(f"[LiveRunner] RPC URL: {rpc_url}")
    print(f"[LiveRunner] System instruction length: {len(system_instruction)} chars")
    print("[LiveRunner] Initializing Gemini client...")
    
    client = genai.Client(api_key=api_key)
    
    # Define default models to try
    default_models = [
        # Try the exact model name from official docs first
        "gemini-2.5-flash-native-audio-preview-12-2025",
        # Try variations that might work
        "models/gemini-2.5-flash-native-audio-preview-12-2025",
        "gemini-2.5-flash-preview-native-audio",
        # Fallback to other potential models
        "gemini-2.0-flash-exp",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]
    
    # First, try to list available models to see what's actually available for Live API
    print("[LiveRunner] Checking available Live API models...")
    live_models = []
    all_models = []
    try:
        # List all models
        models_list = client.models.list()
        print(f"[LiveRunner] Fetching model list from API...")
        for m in models_list:
            model_name = getattr(m, 'name', '') or str(m)
            all_models.append(model_name)
            # Look for Live API compatible models - check various patterns
            model_lower = model_name.lower()
            if any(keyword in model_lower for keyword in ["live", "2.5-flash-native-audio", "native-audio", "2.5-flash"]):
                live_models.append(model_name)
                print(f"[LiveRunner]   ✓ Found Live API candidate: {model_name}")
        
        print(f"[LiveRunner] Found {len(all_models)} total models")
        if live_models:
            print(f"[LiveRunner] Found {len(live_models)} Live API compatible models")
        else:
            print("[LiveRunner] ⚠️ No obvious Live API models found in list")
            print("[LiveRunner] Showing all available models (may help identify correct names):")
            for m in all_models:
                print(f"[LiveRunner]   - {m}")
    except Exception as e:
        print(f"[LiveRunner] ⚠️ Could not list models: {e}")
        import traceback
        traceback.print_exc()
        print("[LiveRunner] Will proceed with known model names")
    
    # Build the final model list - prioritize discovered live models, then defaults
    if live_models:
        models_to_try = live_models + default_models
        print(f"[LiveRunner] Will try {len(models_to_try)} models total ({len(live_models)} Live models first, then {len(default_models)} defaults)")
    else:
        models_to_try = default_models
        print(f"[LiveRunner] Will try {len(models_to_try)} known model names")
    config_text = {
        "response_modalities": ["TEXT"],
        "system_instruction": system_instruction or "You are a Blender assistant. Respond with only executable Blender Python code (bpy.ops... or bpy.context...). No explanations.",
    }
    
    config_audio = {
        "response_modalities": ["AUDIO"],
        "system_instruction": system_instruction or "You are a Blender assistant. Respond with only executable Blender Python code (bpy.ops... or bpy.context...). No explanations. Speak the code clearly.",
    }
    
    # Also try both TEXT and AUDIO together - some models might support both
    config_both = {
        "response_modalities": ["TEXT", "AUDIO"],
        "system_instruction": system_instruction or "You are a Blender assistant. Respond with only executable Blender Python code (bpy.ops... or bpy.context...). No explanations.",
    }

    # XML-RPC client for Blender
    print(f"[LiveRunner] Connecting to Blender XML-RPC at {rpc_url}...")
    rpc = ServerProxy(rpc_url, allow_none=True)
    try:
        # Test RPC connection
        rpc.ping()
        print("[LiveRunner] ✅ Connected to Blender RPC server")
    except Exception as e:
        print(f"[LiveRunner] ⚠️ RPC connection test failed: {e}")
        print("[LiveRunner] Will continue anyway - RPC may start later")

    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    SEND_SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024

    pya = pyaudio.PyAudio()
    audio_stream = None
    audio_queue_mic: "asyncio.Queue[dict]" = asyncio.Queue(maxsize=5)

    async def listen_audio():
        nonlocal audio_stream
        try:
            print("[LiveRunner] Opening microphone...")
            mic_info = pya.get_default_input_device_info()
            print(f"[LiveRunner] Using mic: {mic_info.get('name', 'default')} (index {mic_info.get('index', '?')})")
            audio_stream = await asyncio.to_thread(
                pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=SEND_SAMPLE_RATE,
                input=True,
                input_device_index=mic_info["index"],
                frames_per_buffer=CHUNK_SIZE,
            )
            print(f"[LiveRunner] ✅ Microphone opened: {SEND_SAMPLE_RATE}Hz, {CHANNELS} channel(s), {CHUNK_SIZE} frames/buffer")
            kwargs = {"exception_on_overflow": False} if not __debug__ else {}
            chunk_count = 0
            while True:
                data = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE, **kwargs)
                await audio_queue_mic.put({"data": data, "mime_type": "audio/pcm"})
                chunk_count += 1
                if chunk_count % 50 == 0:  # Log every ~1 second (50 chunks * 0.02s)
                    print(f"[LiveRunner] 📡 Streaming audio... ({chunk_count} chunks sent)")
        except asyncio.CancelledError:
            print("[LiveRunner] Audio listening cancelled")
        except Exception as e:
            print(f"[LiveRunner] ❌ Mic error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

    async def send_realtime(session):
        try:
            print("[LiveRunner] Starting audio send loop...")
            while True:
                msg = await asyncio.wait_for(audio_queue_mic.get(), timeout=0.5)
                await session.send_realtime_input(audio=msg)
        except asyncio.TimeoutError:
            # Just loop back and wait again
            await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            print("[LiveRunner] Audio send cancelled")
        except Exception as e:
            print(f"[LiveRunner] ❌ Send error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _send_code_to_blender(code: str, source: str = "Gemini"):
        """Send a CODE string to Blender via XML-RPC with basic safety checks."""
        if not code or not isinstance(code, str):
            return
        code_preview = code[:80] + "..." if len(code) > 80 else code
        for forbidden in CODE_BLACKLIST:
            if forbidden in code:
                print(f"[LiveRunner] 🚫 BLOCKED CODE from {source} (forbidden: {forbidden!r})")
                print(f"[LiveRunner]    Code preview: {code_preview}")
                return
        try:
            print(f"[LiveRunner] ➡️  Sending code to Blender ({source}): {code_preview}")
            payload = {"op": "execute", "kwargs": {"code": code}}
            result = rpc.execute(payload)
            if result and result.get("ok"):
                print(f"[LiveRunner] ✅ Code executed successfully")
            else:
                error_msg = result.get("error", "Unknown error") if result else "No response"
                print(f"[LiveRunner] ⚠️ Code execution returned: {error_msg}")
        except Exception as e:
            print(f"[LiveRunner] ❌ RPC execute error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

    async def receive_and_forward(session):
        try:
            print("[LiveRunner] Starting receive loop...")
            print("[LiveRunner] Waiting for Gemini responses...")
            turn = session.receive()
            response_count = 0
            async for response in turn:
                response_count += 1
                sc = getattr(response, "server_content", None)
                if not sc:
                    continue
                mt = getattr(sc, "model_turn", None)
                if not mt:
                    continue
                
                # Check for both TEXT and AUDIO responses
                for part in getattr(mt, "parts", []) or []:
                    # Try to extract text first
                    text_obj = getattr(part, "text", None)
                    text = getattr(text_obj, "text", None) if text_obj else (getattr(part, "text", None) or "")
                    
                    # If no text, check for inline_data (audio) - some models return text transcripts with audio
                    if not text or not isinstance(text, str) or not text.strip():
                        inline_data = getattr(part, "inline_data", None)
                        if inline_data:
                            # Check if there's a text transcript in the audio metadata
                            mime_type = getattr(inline_data, "mime_type", "")
                            if "audio" in mime_type.lower():
                                # Audio response - we can't extract text from this easily
                                print(f"[LiveRunner] 📢 Received audio response #{response_count} (cannot extract text)")
                                continue
                    
                    if isinstance(text, str):
                        t = text.strip()
                    else:
                        t = ""
                    if not t:
                        continue

                    print(f"[LiveRunner] 📥 Received text from Gemini (response #{response_count}): {t[:100]}...")
                    text_lower = t.lower()
                    # God Mode: instant primitives
                    triggered_predict = False
                    for kw in PREDICT_KEYWORDS:
                        if kw in text_lower and kw in PREDICT_CODE_MAP:
                            print(f"[LiveRunner] ⚡ God Mode triggered: '{kw}' -> instant primitive")
                            _send_code_to_blender(PREDICT_CODE_MAP[kw], source=f"GodMode({kw})")
                            triggered_predict = True
                            break

                    # Main code stream back to Blender
                    _send_code_to_blender(t, source="Gemini")
        except asyncio.CancelledError:
            print("[LiveRunner] Receive loop cancelled")
        except Exception as e:
            print(f"[LiveRunner] ❌ Receive error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

    # Try each model until one works
    # Native-audio models require AUDIO, others might support TEXT
    successful_model = None
    successful_config = None
    last_error = None
    
    try:
        for model in models_to_try:
            # Determine which configs to try based on model name
            is_native_audio = "native-audio" in model.lower()
            
            configs_to_try = []
            if is_native_audio:
                # Native-audio models require AUDIO, but try both first in case they support TEXT too
                configs_to_try = [
                    ("TEXT+AUDIO", config_both),
                    ("AUDIO", config_audio),
                ]
            else:
                # Regular models: try TEXT first, then both
                configs_to_try = [
                    ("TEXT", config_text),
                    ("TEXT+AUDIO", config_both),
                ]
            
            for config_name, config in configs_to_try:
                try:
                    print(f"[LiveRunner] Attempting to connect with model: {model} ({config_name} responses)...")
                    async with client.aio.live.connect(model=model, config=config) as live_session:
                        successful_model = model
                        successful_config = config_name
                        print(f"[LiveRunner] ✅ Connected to Gemini Live with model: {model} ({config_name})!")
                        print("[LiveRunner] 🎤 Listening... Speak to generate Blender code")
                        print("[LiveRunner] Press Ctrl+C in this window to stop")
                        print("")
                        await asyncio.gather(
                            send_realtime(live_session),
                            listen_audio(),
                            receive_and_forward(live_session),
                        )
                    # If we get here, the session completed successfully
                    break
                except KeyboardInterrupt:
                    print("\n[LiveRunner] Interrupted by user (Ctrl+C)")
                    break
                except Exception as e:
                    last_error = e
                    error_msg = str(e)
                    if len(error_msg) > 200:
                        error_msg = error_msg[:200] + "..."
                    print(f"[LiveRunner] ⚠️ Model {model} with {config_name} failed: {error_msg}")
                    # Continue to next config
                    continue
            
            # If we found a working model, stop trying others
            if successful_model:
                break
        
        # If TEXT failed, try AUDIO responses for native-audio model
        # The native-audio model requires AUDIO responses, but we can't easily extract text from audio
        # So we'll skip this for now and show a helpful error message
        if not successful_model:
            print("[LiveRunner] ⚠️ TEXT responses failed for all models")
            print("[LiveRunner]")
            print("[LiveRunner] ========================================")
            print("[LiveRunner] TROUBLESHOOTING:")
            print("[LiveRunner] ========================================")
            print("[LiveRunner] 1. Check if Live API is enabled:")
            print("[LiveRunner]    - Go to https://aistudio.google.com/")
            print("[LiveRunner]    - Check if 'Live API' is available in your account")
            print("[LiveRunner]    - Some features require approval/enablement")
            print("[LiveRunner]")
            print("[LiveRunner] 2. Verify your API key:")
            print("[LiveRunner]    - Ensure it's a valid Gemini API key")
            print("[LiveRunner]    - Check it has Live API permissions")
            print("[LiveRunner]")
            print("[LiveRunner] 3. Model availability:")
            print("[LiveRunner]    - Live API models may not be available in all regions")
            print("[LiveRunner]    - Some models require specific API versions")
            print("[LiveRunner]")
            print("[LiveRunner] 4. Alternative approach:")
            print("[LiveRunner]    - Use the classic voice pipeline (Start RPC)")
            print("[LiveRunner]    - It uses standard Gemini API with text responses")
            print("[LiveRunner] ========================================")
        
        if not successful_model:
            error_msg = f"All models failed. Last error: {last_error}"
            print(f"[LiveRunner] ❌ {error_msg}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            # Raise exception so the script exits with error code
            raise Exception(error_msg)
    finally:
        if audio_stream:
            try:
                audio_stream.stop_stream()
                audio_stream.close()
            except Exception:
                pass
        pya.terminate()


def main():
    print("[LiveRunner] Starting SpeechToBlender Live Runner...")
    print(f"[LiveRunner] Python: {sys.executable}")
    print(f"[LiveRunner] Script: {__file__}")
    
    api_key = os.environ.get("STB_GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[LiveRunner] ❌ Missing STB_GEMINI_API_KEY in environment", file=sys.stderr)
        print("[LiveRunner] Set this environment variable before running", file=sys.stderr)
        input("\nPress Enter to exit...")
        sys.exit(1)

    system_instruction = os.environ.get("STB_LIVE_CONTEXT", "").strip()
    rpc_url = os.environ.get("STB_RPC_URL", "http://127.0.0.1:8765/RPC2").strip()
    
    print(f"[LiveRunner] API key: {'*' * min(len(api_key), 20)}... ({len(api_key)} chars)")
    print(f"[LiveRunner] Context: {len(system_instruction)} chars")
    print("")

    try:
        asyncio.run(_run_live_session(api_key, system_instruction, rpc_url))
        exit_code = 0
    except KeyboardInterrupt:
        print("\n[LiveRunner] Interrupted by user (Ctrl+C)")
        exit_code = 130
    except Exception as e:
        print(f"[LiveRunner] ❌ Unhandled error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        exit_code = 1
    finally:
        print("\n[LiveRunner] Shutting down...")
        print("[LiveRunner] Goodbye!")
        input("\nPress Enter to close this window...")
        sys.exit(exit_code if 'exit_code' in locals() else 1)


if __name__ == "__main__":
    main()
