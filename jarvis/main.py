"""
Jarvis AI Assistant - Main Entry Point
Supports both Text Mode (CLI chat) and Voice Mode (Wake word, STT, TTS, VAD, and Voice Confirmation).
"""

import sys
import os
import argparse
import time

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    if sys.platform != "win32":
        import readline
except ImportError:
    pass

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from jarvis.config import (
    GEMINI_API_KEY,
    DEFAULT_MODEL,
    WORKSPACE_DIR,
    LOG_FILE,
    FOLLOW_UP_TIMEOUT,
    WAKE_WORD_MODEL,
)
from jarvis.brain import GeminiLLMProvider, get_system_prompt
from jarvis.tools import registry

# Import tools for auto-registration
import jarvis.tools.system_tools
import jarvis.tools.web_tools
import jarvis.tools.file_tools

# Voice imports (Phase 2)
from jarvis.voice import (
    speak,
    stop_speaking,
    record_command,
    transcribe,
    wait_for_wake_word,
    play_wake_chime,
    play_dismiss_chime,
    list_audio_devices,
    test_microphone,
)
from jarvis.voice.confirmation import voice_confirmation_handler

# ANSI Color codes
CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[1;34m"
MAGENTA = "\033[1;35m"
RED = "\033[1;31m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(mode: str = "text"):
    mode_display = f"{GREEN}Voice Interactive Mode{RESET}" if mode == "voice" else f"{CYAN}Text CLI Mode{RESET}"
    banner = f"""{CYAN}
   ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
   ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
   ██║███████║██████╔╝██║   ██║██║███████╗
   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
█████║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
╚════╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝{RESET}
{BOLD}Personal AI Assistant (Phase 1 & Phase 2 Active){RESET}
--------------------------------------------------
{BLUE}• Operating Mode :{RESET} {mode_display}
{BLUE}• Active Model   :{RESET} {DEFAULT_MODEL}
{BLUE}• Safe Workspace :{RESET} {WORKSPACE_DIR}
{BLUE}• System Logs    :{RESET} {LOG_FILE}
{BLUE}• Loaded Tools   :{RESET} {len(registry.get_all_tools())} tools registered
"""
    if mode == "voice":
        banner += f"""{BLUE}• Wake Word      :{RESET} "Hey Jarvis" (openwakeword)
{BLUE}• Follow-Up Window:{RESET} {FOLLOW_UP_TIMEOUT} seconds
--------------------------------------------------
{YELLOW}Voice Tips:{RESET}
  Say {BOLD}"Hey Jarvis"{RESET} to activate.
  Say {BOLD}"stop"{RESET} or {BOLD}"ruko"{RESET} while Jarvis is speaking to barge in.
  Press {BOLD}Ctrl+C{RESET} at any time to exit voice mode.
--------------------------------------------------
"""
    else:
        banner += f"""--------------------------------------------------
{YELLOW}Special Commands:{RESET}
  {BOLD}exit{RESET} / {BOLD}quit{RESET}   - Shut down Jarvis
  {BOLD}tools{RESET}         - View all available tool capabilities
  {BOLD}reset{RESET}         - Clear conversation context
  {BOLD}clear{RESET}         - Clear terminal screen
  {BOLD}help{RESET}          - Show this help summary
--------------------------------------------------
"""
    print(banner)


def show_tools():
    """Lists all registered tools and their descriptions."""
    print(f"\n{BOLD}Available Tools in Registry:{RESET}")
    print("-" * 60)
    for tool_obj in registry.get_all_tools():
        confirm_badge = f"{YELLOW}[Requires Confirmation]{RESET}" if tool_obj.requires_confirmation else ""
        print(f"{CYAN}• {tool_obj.name}{RESET} {confirm_badge}")
        doc = (tool_obj.description or "").split("\n")[0].strip()
        print(f"  {doc}\n")
    print("-" * 60)


def run_text_mode(provider: GeminiLLMProvider):
    """Executes the Phase 1 text CLI chat loop."""
    print(f"{GREEN}Jarvis is online and ready, Sir. How may I assist you today?{RESET}\n")

    while True:
        try:
            user_input = input(f"{BOLD}{BLUE}You:{RESET} ").strip()

            if not user_input:
                continue

            cmd_lower = user_input.lower()
            if cmd_lower in ("exit", "quit", "q"):
                print(f"\n{CYAN}Jarvis:{RESET} At your service, Sir. Powering down systems. Have a wonderful day!")
                break

            elif cmd_lower in ("clear", "cls"):
                os.system("cls" if os.name == "nt" else "clear")
                print_banner("text")
                continue

            elif cmd_lower in ("tools", "tool-list"):
                show_tools()
                continue

            elif cmd_lower in ("reset", "new"):
                provider.reset_conversation()
                print(f"{YELLOW}Conversation context has been cleared, Sir.{RESET}\n")
                continue

            elif cmd_lower in ("help", "?"):
                print_banner("text")
                continue

            response = provider.chat(user_input)
            print(f"\n{BOLD}{CYAN}Jarvis:{RESET} {response}\n")

        except KeyboardInterrupt:
            print(f"\n\n{YELLOW}Session interrupted.{RESET}")
            print(f"{CYAN}Jarvis:{RESET} Standing by, Sir. Type 'exit' to quit or enter a command.")
        except EOFError:
            print(f"\n{CYAN}Jarvis:{RESET} Session terminated. Goodbye Sir.")
            break
        except Exception as e:
            print(f"\n{RED}An unexpected error occurred: {e}{RESET}\n")


def run_voice_mode(provider: GeminiLLMProvider):
    """
    Executes the Phase 2 Voice Interaction Loop:
    Idle (Wake word) -> Beep -> Record -> Transcribe -> LLM+Tools -> Speak -> Follow-up Window (6s)
    """
    # Configure voice confirmation handler for sensitive tools
    registry.confirmation_handler = voice_confirmation_handler

    # Greet user out loud
    welcome_text = "Jarvis is online and listening for your command, Sir."
    print(f"{GREEN}{welcome_text}{RESET}\n")
    speak(welcome_text)

    while True:
        try:
            # 1. Wait for wake word "Hey Jarvis"
            activated = wait_for_wake_word()
            if not activated:
                break

            # 2. Wake-up audio cue
            play_wake_chime()

            # 3. Follow-up conversational loop
            in_conversation = True
            while in_conversation:
                # Record command with VAD
                audio_data = record_command()

                if audio_data is None:
                    # No speech detected within window
                    print("[No speech detected.]")
                    in_conversation = False
                    play_dismiss_chime()
                    break

                # Transcribe with local faster-whisper
                print("⚡ Transcribing audio...")
                transcription, detected_lang = transcribe(audio_data)

                if not transcription:
                    print("[No intelligible command detected.]")
                    in_conversation = False
                    play_dismiss_chime()
                    break

                # Print recognized speech
                print(f"\n{BOLD}{BLUE}You (Spoken [{detected_lang}]):{RESET} {transcription}")

                # Check for verbal exit / cancellation
                lower_trans = transcription.lower().strip(".,!?")
                if lower_trans in ("stop", "ruko", "cancel", "bye", "goodbye", "exit", "quit"):
                    reply = "Standing down, Sir. Have a pleasant day."
                    print(f"\n{BOLD}{CYAN}Jarvis:{RESET} {reply}\n")
                    speak(reply)
                    in_conversation = False
                    play_dismiss_chime()
                    break

                # Process through Gemini Brain + Tool Calling Loop
                response = provider.chat(transcription)
                print(f"\n{BOLD}{CYAN}Jarvis:{RESET} {response}\n")

                # Speak response with interruptible barge-in support
                speak(response)

                # 4. Follow-up window: listen for 6 seconds without requiring wake word again
                print(f"\n⏱️  Follow-up window open ({FOLLOW_UP_TIMEOUT}s)... (speak to continue or stay silent to sleep)")
                # Next loop iteration immediately calls record_command with initial listen window

        except KeyboardInterrupt:
            print(f"\n\n{YELLOW}Voice mode paused.{RESET}")
            choice = input("Do you wish to exit Jarvis? [y/N]: ").strip().lower()
            if choice in ("y", "yes"):
                print(f"{CYAN}Jarvis:{RESET} Systems powered down. Goodbye Sir.")
                break
            else:
                print("Resuming voice mode...")
        except Exception as e:
            print(f"\n{RED}Voice interaction error: {e}{RESET}\n")
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Jarvis Personal AI Assistant")
    parser.add_argument(
        "--mode",
        choices=["text", "voice"],
        default="text",
        help="Operating mode: 'text' (default CLI chat) or 'voice' (wake word + speech I/O)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List all available audio input and output devices and exit",
    )
    parser.add_argument(
        "--test-mic",
        action="store_true",
        help="Record a 3-second audio sample, play it back, and test local transcription",
    )

    args = parser.parse_args()

    # Diagnostic flag: list devices
    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    # Diagnostic flag: test microphone
    if args.test_mic:
        print_banner("text")
        audio = test_microphone(duration=3.0)
        if audio is not None:
            print("[Testing faster-whisper transcription on recorded sample...]")
            text, lang = transcribe(audio)
            print(f"[Transcript Result]: {text or '(Silence / No speech detected)'} [Lang: {lang}]")
        sys.exit(0)

    # Verify Gemini API Key
    if not GEMINI_API_KEY:
        print(f"{RED}Error: GEMINI_API_KEY is not set.{RESET}")
        print("Please add your Google Gemini API key to the .env file in the project root:")
        print("  GEMINI_API_KEY=your_actual_key_here\n")
        sys.exit(1)

    is_voice = (args.mode == "voice")
    print_banner(args.mode)

    # Initialize Gemini LLM Provider with mode-specific system prompt
    try:
        provider = GeminiLLMProvider(
            api_key=GEMINI_API_KEY,
            model_name=DEFAULT_MODEL,
            tool_registry=registry,
            system_prompt=get_system_prompt(is_voice_mode=is_voice),
        )
    except Exception as e:
        print(f"{RED}Failed to initialize Jarvis brain: {e}{RESET}")
        sys.exit(1)

    if is_voice:
        run_voice_mode(provider)
    else:
        run_text_mode(provider)


if __name__ == "__main__":
    main()
