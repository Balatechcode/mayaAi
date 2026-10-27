"""
Voice input and output package for Jarvis (Phase 2).
Provides:
- Wake word detection via openwakeword ('Hey Jarvis')
- Speech-to-Text via faster-whisper with VAD
- Text-to-Speech via edge-tts with barge-in support
- Audio utilities and device diagnostics
"""

from jarvis.voice.speak import speak, stop_speaking, speaker, clean_text_for_speech, detect_language
from jarvis.voice.listen import record_command, transcribe, listener
from jarvis.voice.wakeword import wait_for_wake_word, wakeword_listener
from jarvis.voice.audio_utils import (
    play_wake_chime,
    play_dismiss_chime,
    list_audio_devices,
    test_microphone,
    cleanup_temp_audio,
)

__all__ = [
    "speak",
    "stop_speaking",
    "speaker",
    "clean_text_for_speech",
    "detect_language",
    "record_command",
    "transcribe",
    "listener",
    "wait_for_wake_word",
    "wakeword_listener",
    "play_wake_chime",
    "play_dismiss_chime",
    "list_audio_devices",
    "test_microphone",
    "cleanup_temp_audio",
]
