"""
Voice confirmation handler for sensitive and destructive operations in Jarvis.
Speaks the confirmation prompt aloud and listens for affirmative ('haan' / 'yes' / 'kar do')
vs negative ('nahi' / 'no' / 'ruko'). Anything ambiguous or silent strictly defaults to False.
"""

import re
import logging
from typing import Dict, Any

from jarvis.voice.speak import speak
from jarvis.voice.listen import record_command, transcribe
from jarvis.config import LOG_FILE

logger = logging.getLogger("JarvisVoice")

AFFIRMATIVE_TERMS = {
    "yes", "yeah", "yep", "sure", "ok", "okay", "haan", "ha", "kar", "kardo",
    "kar do", "theek", "theek hai", "proceed", "confirm", "allow", "authorize"
}

NEGATIVE_TERMS = {
    "no", "nope", "nahi", "nahin", "ruko", "cancel", "stop", "mat", "mat karo",
    "abort", "deny", "disallow", "dont", "don't"
}


def voice_confirmation_handler(tool_name: str, kwargs: Dict[str, Any]) -> bool:
    """
    Asks for confirmation out loud, records the user's voice response,
    and returns True only if explicit positive consent is confirmed.
    """
    logger.info(f"Voice confirmation requested for sensitive action '{tool_name}' with args {kwargs}")

    prompt_spoken = f"Sir, I require confirmation to execute {tool_name}. Do you authorize this action?"
    print(f"\n" + "=" * 50)
    print(f"⚠️  VOICE CONFIRMATION REQUIRED FOR: {tool_name}")
    print(f"Action: Jarvis is requesting permission to execute '{tool_name}'.")
    print("=" * 50)

    # Speak question aloud
    speak(prompt_spoken)

    # Listen for spoken authorization
    print("🎙️  Listening for confirmation ('haan / yes / kar do' or 'nahi / no / ruko')...")
    audio = record_command(max_duration=6.0, silence_timeout=1.2)

    if audio is None:
        logger.warning(f"Voice confirmation for '{tool_name}' timed out without audio.")
        print("❌ No voice response detected. Action cancelled.")
        speak("I didn't hear a confirmation, Sir. Action cancelled.")
        return False

    transcript, lang = transcribe(audio)
    if not transcript:
        logger.warning(f"Voice confirmation for '{tool_name}' produced empty/unclear transcript.")
        print("❌ Unclear voice response. Action cancelled.")
        speak("I could not clearly verify your response, Sir. Action cancelled.")
        return False

    print(f"User voice response: '\033[1;33m{transcript}\033[0m'")
    logger.info(f"User voice response: '{transcript}'")

    words = set(re.findall(r"\w+", transcript.lower()))
    raw_lower = transcript.lower()

    # Check for presence of affirmative or negative phrases
    is_positive = any(term in raw_lower for term in AFFIRMATIVE_TERMS) or any(w in words for w in AFFIRMATIVE_TERMS)
    is_negative = any(term in raw_lower for term in NEGATIVE_TERMS) or any(w in words for w in NEGATIVE_TERMS)

    if is_positive and not is_negative:
        print("✓ Action authorized via voice confirmation.")
        speak("Authorization confirmed, Sir.")
        return True
    else:
        print("❌ Action not authorized or denied. Safe default applied.")
        speak("Action cancelled, Sir.")
        return False
