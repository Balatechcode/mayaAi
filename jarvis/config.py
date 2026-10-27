"""
Configuration module for Jarvis AI Assistant.
Loads environment variables and sets up core system paths, security policies, and application settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project (parent of jarvis folder)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file in base directory
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
else:
    load_dotenv()

# --- API Keys & LLM Settings ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

# --- System Paths ---
WORKSPACE_DIR = Path(os.getenv("JARVIS_WORKSPACE", str(BASE_DIR / "workspace"))).resolve()
LOGS_DIR = Path(os.getenv("JARVIS_LOGS", str(BASE_DIR / "logs"))).resolve()
LOG_FILE = LOGS_DIR / "jarvis.log"

# Ensure essential directories exist
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# --- Safety & Confirmation Settings ---
# When True, sensitive actions (overwriting files, launching apps not in allowlist, etc.) require CLI confirmation
REQUIRE_CONFIRMATION = os.getenv("REQUIRE_CONFIRMATION", "true").lower() in ("true", "1", "yes")

# Allowed safe applications for Windows (can be expanded via env or config)
SAFE_APPLICATION_MAP = {
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "taskmgr": "taskmgr.exe",
    "task manager": "taskmgr.exe",
    "chrome": "chrome",
    "edge": "msedge",
    "code": "code",
    "vscode": "code",
}

def validate_workspace_path(filename: str) -> Path:
    """
    Validates and resolves a path within the safe WORKSPACE_DIR sandbox.
    Prevents path traversal attacks (e.g. '../../windows/system32').
    Raises PermissionError if path resolves outside the workspace.
    """
    # Normalize path relative to workspace
    target_path = (WORKSPACE_DIR / filename).resolve()
    
    # Check if target_path is within WORKSPACE_DIR
    try:
        target_path.relative_to(WORKSPACE_DIR)
    except ValueError:
        raise PermissionError(
            f"Security Violation: Access denied to '{filename}'. "
            f"File operations are strictly sandboxed inside '{WORKSPACE_DIR}'."
        )
    return target_path


# --- Voice Settings (Phase 2) ---
MIC_DEVICE_INDEX = int(os.getenv("MIC_DEVICE_INDEX")) if os.getenv("MIC_DEVICE_INDEX") else None
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "hey_jarvis").strip()
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

# STT (faster-whisper)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small").strip()
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip()
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip()

# TTS (edge-tts)
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-IN-NeerjaNeural").strip()
TTS_VOICE_HI = os.getenv("TTS_VOICE_HI", "hi-IN-SwaraNeural").strip()

# Audio capture & VAD
SAMPLE_RATE = 16000
VAD_SILENCE_TIMEOUT = float(os.getenv("VAD_SILENCE_TIMEOUT", "1.5"))
MAX_RECORD_SECONDS = float(os.getenv("MAX_RECORD_SECONDS", "20.0"))
FOLLOW_UP_TIMEOUT = float(os.getenv("FOLLOW_UP_TIMEOUT", "6.0"))

# Temp audio directory for synthesized speech
AUDIO_TEMP_DIR = Path(os.getenv("AUDIO_TEMP_DIR", str(BASE_DIR / "temp_audio"))).resolve()
AUDIO_TEMP_DIR.mkdir(parents=True, exist_ok=True)
