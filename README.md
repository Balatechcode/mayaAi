# Jarvis - Personal AI Assistant 🤖

Jarvis is a modular, extensible personal AI assistant built in Python for Windows (cross-platform compatible). Inspired by J.A.R.V.I.S., it features a polite, witty persona with bilingual English/Hindi/Hinglish language intelligence, native LLM tool calling, sandboxed workspace security, and hands-free voice interaction.

---

## 🚀 Key Features

### Phase 1: Text-Based Core & Tools
- **CLI Chat Loop**: Fast interactive text mode.
- **Provider-Agnostic LLM Layer**: Google Gemini via `google-genai` SDK behind `BaseLLMProvider` (swappable to Claude/OpenAI).
- **Decorator-Driven Tool Registry**: Adding a tool is as simple as `@tool` on any Python function with docstrings and type hints.
- **Initial Core Tools**:
  - `get_time`: Current time, date, day, timezone.
  - `open_application`: Launch safe applications (`notepad`, `calc`, `chrome`, `edge`, `code`, etc.).
  - `open_website`: Open URLs in the default browser.
  - `web_search`: Live search queries via DuckDuckGo.
  - `get_weather`: Real-time weather lookup.
  - `read_file`, `write_file`, `list_files`, `delete_file`: Strictly sandboxed in `./workspace` with path-traversal protection.
- **Safety Guardrails**: Sensitive operations (e.g. deleting files, overwrites) require explicit confirmation.
- **Audit Logging**: Every tool execution, duration, and arguments recorded in `logs/jarvis.log`.

### Phase 2: Voice I/O & Wake Word
- **Wake Word**: Hands-free activation saying **"Hey Jarvis"** via `openwakeword`.
- **Local Speech-to-Text (STT)**: High-accuracy offline transcription using `faster-whisper` (small model, int8, CPU) with automatic language detection (`hi` / `en`) and Hinglish initial prompt.
- **Natural Text-to-Speech (TTS)**: Realistic speech via `edge-tts` with Indian voices (`en-IN-NeerjaNeural` for English, `hi-IN-SwaraNeural` for Hindi/Hinglish).
- **Voice Activity Detection (VAD)**: Automatically detects when you stop speaking (~1.5s silence) with up to 20s recording.
- **Follow-Up Window**: Stays listening for 6 seconds after answering without requiring the wake word again.
- **Barge-In**: Interrupt Jarvis while speaking by saying *"stop"*, *"ruko"*, or *"Hey Jarvis"*.
- **Voice Confirmation**: Destructive tools prompt aloud and accept spoken confirmation (*"haan"*, *"yes"*, *"kar do"* vs *"nahi"*, *"no"*).

---

## 📁 Project Structure

```
jarvis/
├── main.py                  # Entry point (text & voice modes)
├── config.py                # System settings & environment loading
├── brain/
│   ├── llm.py               # BaseLLMProvider & Gemini tool loop
│   └── prompts.py           # Persona prompts (Hinglish & Voice rules)
├── tools/
│   ├── __init__.py          # ToolRegistry & @tool decorator
│   ├── system_tools.py      # Apps, time, system status
│   ├── web_tools.py         # Search, websites, weather
│   └── file_tools.py        # Sandboxed safe file management
├── voice/
│   ├── wakeword.py          # openwakeword listener ('Hey Jarvis')
│   ├── listen.py            # faster-whisper STT + VAD
│   ├── speak.py             # edge-tts + pygame audio & barge-in
│   ├── audio_utils.py       # Audio devices, beeps, diagnostics
│   └── confirmation.py      # Spoken confirmation handler
├── memory/                  # Phase 3 Foundation (SQLite)
│   └── store.py
workspace/                   # Safe sandboxed directory for files
logs/                        # Audit logs (jarvis.log)
requirements.txt             # Project dependencies
.env.example                 # Environment template
```

---

## 🛠️ Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd "maya ai"
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up API Key**:
   Copy `.env.example` to `.env` and insert your Gemini API Key:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   GEMINI_MODEL=gemini-3.5-flash
   ```

---

## 🎮 How to Run

### 1. Text Mode (Default)
```bash
python -m jarvis.main
# or
python -m jarvis.main --mode text
```

### 2. Voice Interactive Mode
```bash
python -m jarvis.main --mode voice
```
- Say **"Hey Jarvis"** to wake up.
- Speak your command (English, Hindi, or Hinglish).
- Jarvis speaks back and keeps a 6-second follow-up window open for follow-up requests!

### 3. Audio Diagnostics
- **List audio devices**:
  ```bash
  python -m jarvis.main --list-devices
  ```
- **Test microphone & transcription**:
  ```bash
  python -m jarvis.main --test-mic
  ```

---

## 🔒 Security Principles
- **No Cloud STT**: Audio transcription runs 100% locally on your machine.
- **Sandboxed Workspace**: File operations cannot escape `./workspace/`.
- **Sensitive Operations Gate**: Deletion or unknown executables require explicit user confirmation.
- **Never Commit Secrets**: `.env` is strictly ignored by `.gitignore`.

---

## 🗺️ Roadmap
- [x] **Phase 1**: Text CLI Core, Tool Registry, Sandboxing, Gemini Function Calling.
- [x] **Phase 2**: Voice Input/Output, Wake Word ("Hey Jarvis"), STT, TTS, Barge-in.
- [ ] **Phase 3**: Persistent Memory (SQLite, conversation history, user preferences).
- [ ] **Phase 4**: Integrations (Gmail, Calendar, WhatsApp).
- [ ] **Phase 5**: Desktop GUI / System Tray.
- [ ] **Phase 6**: Multi-step Autonomous Planning Agent.
