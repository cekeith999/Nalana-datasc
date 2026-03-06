# Nalana — Voice-Controlled 3D Creation for Blender

> **DataSC Collaboration Repo — Spring 2026**

Nalana translates natural language voice commands into Blender operations in real time. This repo contains the working codebase for the DataSC team to build on.

---

## Quick Setup (Do This Before Wednesday)

### Prerequisites

- **Blender 5.x** — Download from [blender.org](https://www.blender.org/download/)
- **Python 3.10+** — [python.org](https://www.python.org/downloads/) or Anaconda/Miniconda
- **Git** — [git-scm.com](https://git-scm.com/downloads)
- **VS Code** (recommended) — [code.visualstudio.com](https://code.visualstudio.com/)
- **Windows** — Current setup is Windows-focused. Mac/Linux support is WIP.

### Step 1: Clone the Repo

```bash
git clone https://github.com/cekeith999/Nalana-datasc.git
cd Nalana-datasc
```

### Step 2: Install the Blender Add-on

1. Open **Blender 5.x**
2. Go to **Edit → Preferences → Add-ons**
3. Click **"Install from Disk..."**
4. Navigate to the repo and select the `Nalana-datasc/` folder (or the ZIP if provided)
5. Enable the add-on by checking the box next to **"Blender STB Tool"**

### Step 3: Set Up API Keys

The add-on needs an AI API key to handle complex voice commands. **You don't need to create your own — Clarence will provide the team with shared API keys at the first meeting.** Once you have a key:

1. In Blender: **Preferences → Add-ons → Speech To Blender → Voice & AI Settings**
2. Paste the key Clarence provides
3. Select the AI model (Clarence will tell you which one to use)

### Step 4: Test It

1. In Blender, open the **STB** panel (press `N` to open the right sidebar, click the **"STB"** tab)
2. Click **"Start RPC"** — a console window will open
3. Wait for **"Voice: Running"** status
4. Press **Alt+F** to toggle voice listening
5. Say **"add a cube"** — you should see a cube appear in your scene

If that works, you're set up. If not, check the console window for error messages and reach out in the group chat.

---

## How the Codebase Works

```
Voice Input
    │
    ▼
┌──────────────┐
│ faster-whisper│  ← Local speech-to-text (~200-500ms)
│ (local STT)  │     No cloud, no API cost
└──────┬───────┘
       │ transcript
       ▼
┌──────────────┐     ┌──────────────────┐
│ Local Rules  │────→│ Match found?     │──YES──→ Execute immediately (~5ms)
│ (regex)      │     │ "add cube", etc. │
└──────────────┘     └──────┬───────────┘
                            │ NO
                            ▼
                   ┌──────────────────┐
                   │ LLM Fallback     │  ← Gemini Pro 3 / GPT-4o
                   │ + Scene Context  │     (~250-600ms)
                   └──────┬───────────┘
                          │ JSON commands
                          ▼
                   ┌──────────────────┐
                   │ Safety Gate      │  ← Whitelist check
                   │ + XML-RPC Bridge │     Undo grouping
                   └──────┬───────────┘
                          │
                          ▼
                   ┌──────────────────┐
                   │ Blender executes │  ← bpy.ops.* calls
                   │ the operation    │     on main thread
                   └──────────────────┘
```

### Key Files You'll Work With

| File | What It Does |
|------|-------------|
| `voice_to_blender.py` | Main voice pipeline — handles STT, command parsing, LLM calls, scene context extraction |
| `addon/__init__.py` | Blender add-on entry point — RPC server, UI panels, voice launcher |
| `addon/command_exec.py` | Executes commands in Blender — safety validation, operator dispatch |
| `stb_core/commands/safety.py` | Safety gate — whitelist/blacklist for allowed operations |
| `stb_core/commands/schema.py` | Command schema definitions and type validation |
| `stb_core/config.py` | Configuration management |
| `config/config.json` | Provider settings and configuration |

### Scene Context (Already Built)

Nalana already captures rich scene state before sending commands to the LLM:

- **Scene graph** — all objects, types, names, parent-child relationships
- **Mesh analysis** — vertex/edge/face counts, bounding box, shape classification, face topology
- **Spatial info** — object positions, dimensions, largest/smallest objects
- **Viewport screenshots** — captured and sent to vision-capable models
- **Post-execution diffing** — compares scene state before and after commands

This context is in `voice_to_blender.py` (search for `_fetch_context_for_gpt` and `analyze_scene`).

---

## Git Workflow

**Golden rule: never push directly to `main`.**

### Creating a Branch

```bash
# Make sure you're on main and up to date
git checkout main
git pull origin main

# Create your branch
git checkout -b your-name/what-youre-working-on
# Example: git checkout -b caleb/youtube-transcript-pipeline
```

### Doing Your Work

```bash
# Make changes, then stage and commit
git add .
git commit -m "Brief description of what you did"

# Push your branch
git push origin your-name/what-youre-working-on
```

### Opening a Pull Request

1. Go to the repo on GitHub
2. You'll see a banner saying your branch was recently pushed — click **"Compare & pull request"**
3. Write a brief description of what you built
4. Click **"Create pull request"**
5. Clarence reviews and merges

### Staying Up to Date

```bash
# When main gets updated (after someone's PR is merged)
git checkout main
git pull origin main
git checkout your-branch-name
git merge main
```

---

## Your Workstreams

### Workstream 1: Data Collection Pipeline

Build infrastructure to collect training data from multiple sources:

- **YouTube tutorials** → extract transcripts + pair with on-screen Blender actions
- **Existing command patterns** → audit local rules, generate natural language variations
- **Scene-contextualized pairs** → include scene state with each training example
- **User session logging** → capture real interaction data when beta users come online

Output format: JSONL with `(intent, scene_context, blender_command, result)` tuples.

### Workstream 2: Evaluation Framework

Build a benchmark to measure command translation quality:

- **Test suite** — 100-200 test cases across difficulty levels and command categories
- **Automated scoring** — compare model output to ground truth
- **Gemini baseline** — run the benchmark against the current backend

### Stretch: Model Fine-Tuning

If the data pipeline produces enough quality pairs by weeks 5-6, attempt fine-tuning a small open-source model for Blender command generation.

---

## Resources

- **Compute**: 18x NVIDIA A6000 GPUs (48GB VRAM each) + $25K Azure credits
- **Reference paper**: VideoCAD (NeurIPS 2025) — search "VideoCAD NeurIPS" for background on learning 3D operations from video
- **Blender Python API docs**: [docs.blender.org/api/current](https://docs.blender.org/api/current/)

---

## Questions?

Reach out to Clarence in the group chat. No question is too basic.
