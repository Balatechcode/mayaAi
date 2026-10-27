"""
Text-to-Speech (TTS) module for Jarvis Phase 2.
Uses edge-tts with Indian English (en-IN-NeerjaNeural) and Hindi (hi-IN-SwaraNeural) voices.
Plays audio via pygame.mixer with barge-in support (stop_speaking).
Cleans markdown, emojis, and code formatting for natural voice output.
"""

import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import asyncio
import re
import time
import logging
import uuid
from pathlib import Path
from typing import Optional, Tuple

from jarvis.config import (
    TTS_VOICE_EN,
    TTS_VOICE_HI,
    AUDIO_TEMP_DIR,
    LOG_FILE,
)
from jarvis.voice.audio_utils import cleanup_temp_audio

# Set up logging for voice
logger = logging.getLogger("JarvisVoice")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [Voice] %(message)s"))
    logger.addHandler(fh)

# Optional packages
try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

try:
    import pygame
    _HAS_PYGAME = True
    pygame.mixer.init()
except Exception:
    _HAS_PYGAME = False


# Common Hindi / Hinglish keywords in Roman script
_HINGLISH_KEYWORDS = {
    "haan", "nahi", "nahin", "theek", "accha", "samay", "kaisa", "kaise",
    "kya", "kyun", "hai", "hain", "karta", "karo", "kardo", "diya", "padhna",
    "batao", "bhai", "namaste", "dhanyawad", "shukriya", "filhal", "maujood"
}


def clean_text_for_speech(raw_text: str) -> str:
    """
    Strips markdown symbols, emojis, raw code blocks, and URLs
    to produce clean, natural spoken speech.
    """
    text = raw_text

    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", " Code snippet. ", text)
    text = re.sub(r"`.*?`", "", text)

    # Remove URLs
    text = re.sub(r"https?://\S+|www\.\S+", "a web link", text)

    # Remove Markdown headers, bold, italics, strikethrough
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)

    # Remove bullet markers and numbering
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Remove emojis (Unicode range)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA70-\U0001FAFF"
        "]+",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub("", text)

    # Collapse multiple whitespaces/newlines into a single space
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_language(text: str) -> str:
    """
    Detects whether text is primarily Hindi / Hinglish or English.
    Returns 'hi' or 'en'.
    """
    # Check for Devanagari unicode range (0x0900 - 0x097F)
    has_devanagari = any("\u0900" <= char <= "\u097f" for char in text)
    if has_devanagari:
        return "hi"

    # Check for Hinglish keywords
    words = [w.lower().strip(".,!?:;\"'") for w in text.split()]
    hinglish_count = sum(1 for w in words if w in _HINGLISH_KEYWORDS)

    if len(words) > 0 and (hinglish_count / len(words)) >= 0.15:
        return "hi"

    return "en"


class Speaker:
    """
    Speech synthesizer and audio controller.
    Supports asynchronous edge-tts synthesis, audio playback,
    and instantaneous barge-in stopping.
    """

    def __init__(
        self,
        voice_en: str = TTS_VOICE_EN,
        voice_hi: str = TTS_VOICE_HI,
        temp_dir: Path = AUDIO_TEMP_DIR,
    ):
        self.voice_en = voice_en
        self.voice_hi = voice_hi
        self.temp_dir = temp_dir
        self.is_speaking = False
        self._interrupted = False

    def stop_speaking(self) -> None:
        """Immediately halts current audio playback (barge-in)."""
        self._interrupted = True
        self.is_speaking = False
        if _HAS_PYGAME:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
                    pygame.mixer.music.unload()
            except Exception:
                pass
        logger.info("Speaker playback stopped immediately (Barge-in).")

    async def _synthesize_edge_tts(self, text: str, voice: str, output_file: Path) -> None:
        """Calls edge-tts asynchronously to generate audio MP3 file."""
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(str(output_file))

    def speak(self, text: str, lang: Optional[str] = None) -> bool:
        """
        Synthesizes and speaks text using the appropriate voice.
        Returns True if spoken successfully, False otherwise.
        """
        if not text or not text.strip():
            return False

        clean_text = clean_text_for_speech(text)
        if not clean_text:
            return False

        # Select language and voice
        detected_lang = lang or detect_language(clean_text)
        voice = self.voice_hi if detected_lang == "hi" else self.voice_en

        logger.info(f"Synthesizing TTS ({detected_lang}) with voice '{voice}': {clean_text[:100]}...")

        # If edge-tts or pygame is not available, log and return
        if not _HAS_EDGE_TTS or not _HAS_PYGAME:
            logger.warning("edge-tts or pygame not available. Skipping audio playback.")
            return False

        output_filename = self.temp_dir / f"tts_{uuid.uuid4().hex[:8]}.mp3"

        try:
            # Generate MP3 file
            t0 = time.time()
            asyncio.run(self._synthesize_edge_tts(clean_text, voice, output_filename))
            gen_time = round((time.time() - t0) * 1000, 2)
            logger.info(f"TTS generated in {gen_time}ms: {output_filename.name}")

            # Reset flags
            self._interrupted = False
            self.is_speaking = True

            # Play audio via pygame.mixer
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            pygame.mixer.music.load(str(output_filename))
            pygame.mixer.music.play()

            # Wait while audio is playing, allowing stop_speaking() to abort immediately
            while pygame.mixer.music.get_busy() and not self._interrupted:
                time.sleep(0.05)

            # Unload audio to free file handle
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass

            self.is_speaking = False
            cleanup_temp_audio(max_age_seconds=60)
            return not self._interrupted

        except Exception as e:
            self.is_speaking = False
            logger.exception(f"TTS synthesis/playback error: {e}")
            print(f"\n[TTS Notice: Speech synthesis unavailable ({e}). Continuing with text display.]")
            return False


# Global speaker instance
speaker = Speaker()
speak = speaker.speak
stop_speaking = speaker.stop_speaking
