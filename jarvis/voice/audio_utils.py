"""
Audio utility functions for Jarvis Phase 2 Voice.
Provides sound device enumeration, synthesized audio cues (beeps),
safe temp file cleanup, and microphone diagnostic testing.
"""

from __future__ import annotations

import os
import time
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

from jarvis.config import AUDIO_TEMP_DIR, SAMPLE_RATE, MIC_DEVICE_INDEX

# Try imports; handles missing packages gracefully during installation
try:
    import numpy as np
    import sounddevice as sd
    _AUDIO_DEPS_AVAILABLE = True
except ImportError:
    _AUDIO_DEPS_AVAILABLE = False


def list_audio_devices() -> None:
    """
    Prints all available host audio input and output devices.
    Used for `--list-devices` CLI flag.
    """
    if not _AUDIO_DEPS_AVAILABLE:
        print("Audio dependencies (sounddevice/numpy) are not installed.")
        return

    print("\n" + "=" * 65)
    print("AVAILABLE AUDIO DEVICES (sounddevice)")
    print("=" * 65)
    
    devices = sd.query_devices()
    default_in, default_out = sd.default.device

    print("\n[INPUT DEVICES / MICROPHONES]")
    for idx, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            is_default = " (Default Input)" if idx == default_in else ""
            is_selected = " [SELECTED IN CONFIG]" if idx == MIC_DEVICE_INDEX else ""
            print(f"  [{idx:2d}] {dev['name']} - In: {dev['max_input_channels']} ch, Host: {dev['hostapi']}{is_default}{is_selected}")

    print("\n[OUTPUT DEVICES / SPEAKERS]")
    for idx, dev in enumerate(devices):
        if dev['max_output_channels'] > 0:
            is_default = " (Default Output)" if idx == default_out else ""
            print(f"  [{idx:2d}] {dev['name']} - Out: {dev['max_output_channels']} ch, Host: {dev['hostapi']}{is_default}")

    print("=" * 65 + "\n")


def play_beep(freq: int = 950, duration: float = 0.12, volume: float = 0.25) -> None:
    """
    Plays a smooth synthesized audio cue (beep) using sounddevice and numpy.
    Avoids requiring any external sound asset files.
    """
    if not _AUDIO_DEPS_AVAILABLE:
        return

    try:
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
        # Sine wave tone
        wave = volume * np.sin(2 * np.pi * freq * t)
        
        # Smooth attack & release envelope to eliminate audio pops/clicks
        fade_samples = int(0.015 * SAMPLE_RATE)
        envelope = np.ones_like(wave)
        if len(wave) > fade_samples * 2:
            envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
            envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        
        audio = (wave * envelope).astype(np.float32)
        sd.play(audio, samplerate=SAMPLE_RATE)
        sd.wait()
    except Exception:
        # Fails silently if no audio output device is available
        pass


def play_wake_chime() -> None:
    """Two-tone ascending pleasant wake chime."""
    play_beep(freq=780, duration=0.08, volume=0.2)
    time.sleep(0.02)
    play_beep(freq=1040, duration=0.10, volume=0.25)


def play_dismiss_chime() -> None:
    """Two-tone descending subtle chime."""
    play_beep(freq=880, duration=0.07, volume=0.15)
    time.sleep(0.02)
    play_beep(freq=620, duration=0.09, volume=0.15)


def cleanup_temp_audio(max_age_seconds: int = 300) -> None:
    """
    Cleans up temporary synthesized audio files (.mp3/.wav) in AUDIO_TEMP_DIR.
    Deletes files older than max_age_seconds.
    """
    if not AUDIO_TEMP_DIR.exists():
        return

    now = time.time()
    for item in AUDIO_TEMP_DIR.iterdir():
        if item.is_file() and item.suffix.lower() in (".mp3", ".wav"):
            try:
                if now - item.stat().st_mtime > max_age_seconds:
                    item.unlink()
            except Exception:
                pass


def get_default_input_device() -> Optional[int]:
    """
    Returns the configured or best available audio input device index.
    Prevents PortAudio -1 device errors on Windows.
    """
    if not _AUDIO_DEPS_AVAILABLE:
        return None
    if MIC_DEVICE_INDEX is not None:
        return MIC_DEVICE_INDEX
    try:
        default_in = sd.default.device[0]
        if default_in >= 0:
            return default_in
    except Exception:
        pass

    # Search for first device with input channels
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get('max_input_channels', 0) > 0:
                return idx
    except Exception:
        pass
    return None


def test_microphone(duration: float = 3.0) -> Optional[Any]:
    """
    Records audio for `duration` seconds, plays it back, and returns the audio array.
    Used for `--test-mic` command.
    """
    if not _AUDIO_DEPS_AVAILABLE:
        print("Cannot test microphone: sounddevice or numpy not installed.")
        return None

    dev_id = get_default_input_device()
    try:
        if dev_id is not None:
            dev_info = sd.query_devices(dev_id, 'input')
            channels = min(max(int(dev_info.get('max_input_channels', 1)), 1), 2)
            dev_name = dev_info.get('name', f'Device {dev_id}')
        else:
            channels = 1
            dev_name = "Default"
    except Exception:
        channels = 1
        dev_name = "Default"

    print(f"\n[MIC TEST] Recording {duration:.1f} seconds of audio from device [{dev_id if dev_id is not None else 'Default'}]: {dev_name} ({channels} ch)...")
    print(">>> Speak clearly into your microphone now! <<<")
    
    try:
        recording = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=channels,
            dtype="float32",
            device=dev_id
        )
        sd.wait()
        print("[MIC TEST] Recording complete!")
        
        # Downmix to mono if stereo
        if channels > 1:
            mono_audio = np.mean(recording, axis=1)
        else:
            mono_audio = recording.flatten()

        # Calculate RMS energy level
        rms = float(np.sqrt(np.mean(np.square(mono_audio))))
        peak = float(np.max(np.abs(mono_audio)))
        print(f"[MIC TEST] Signal Analysis: Peak={peak:.4f}, RMS Energy={rms:.4f}")
        
        if peak < 0.005:
            print("⚠️  WARNING: Extremely low audio signal detected.")
            print("   Tips:")
            print("   1. Check if microphone is unmuted and volume is high in Windows Settings.")
            print("   2. Run 'python -m jarvis.main --list-devices' to find your specific microphone index.")
            print("   3. Add 'MIC_DEVICE_INDEX=<index>' to your .env file.")
        else:
            print("✓ Audio signal successfully captured.")

        print("[MIC TEST] Playing back recorded audio through speakers...")
        sd.play(mono_audio, samplerate=SAMPLE_RATE)
        sd.wait()
        print("[MIC TEST] Playback complete.\n")
        return mono_audio

    except Exception as e:
        print(f"❌ Microphone test failed: {e}")
        return None
