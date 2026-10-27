"""
Audio utility functions for Jarvis Phase 2 Voice.
Provides sound device enumeration, synthesized audio cues (beeps),
safe temp file cleanup, and microphone diagnostic testing with robust
Windows driver compatibility (native sample rate detection, callback streaming, resampling).
"""

from __future__ import annotations

import os
import time
import math
import queue
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


def get_default_input_device() -> Optional[int]:
    """
    Returns the configured or best available audio input device index.
    Prefers active microphones over disconnected Line-In/Stereo-Mix.
    """
    if not _AUDIO_DEPS_AVAILABLE:
        return None
    if MIC_DEVICE_INDEX is not None:
        return MIC_DEVICE_INDEX

    try:
        devices = sd.query_devices()
        # 1. Search for a device with 'microphone' or 'mic' in name
        for idx, dev in enumerate(devices):
            if dev.get('max_input_channels', 0) > 0:
                name = dev.get('name', '').lower()
                if 'microphone' in name or 'mic' in name:
                    return idx

        # 2. Check default device
        def_in = sd.default.device[0]
        if def_in >= 0 and devices[def_in].get('max_input_channels', 0) > 0:
            return def_in

        # 3. Fallback to any input device
        for idx, dev in enumerate(devices):
            if dev.get('max_input_channels', 0) > 0:
                return idx
    except Exception:
        pass
    return None


def get_device_native_sr(device_id: Optional[int]) -> int:
    """Returns the hardware native samplerate for a device, defaulting to 16000."""
    if not _AUDIO_DEPS_AVAILABLE or device_id is None:
        return SAMPLE_RATE
    try:
        info = sd.query_devices(device_id, 'input')
        sr = int(info.get('default_samplerate', SAMPLE_RATE))
        return sr if sr > 0 else SAMPLE_RATE
    except Exception:
        return SAMPLE_RATE


def resample_to_16k(audio: np.ndarray, orig_sr: int) -> np.ndarray:
    """Resamples mono audio from orig_sr to 16000 Hz using linear interpolation."""
    if orig_sr == SAMPLE_RATE or len(audio) == 0:
        return audio
    target_len = int(len(audio) * SAMPLE_RATE / orig_sr)
    if target_len <= 0:
        return audio
    resampled = np.interp(
        np.linspace(0, len(audio), target_len, endpoint=False),
        np.arange(len(audio)),
        audio,
    ).astype(audio.dtype)
    return resampled


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
    selected_in = get_default_input_device()

    print("\n[INPUT DEVICES / MICROPHONES]")
    for idx, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            is_default = " (Default Input)" if idx == default_in else ""
            is_active = " [AUTO-DETECTED MIC]" if idx == selected_in else ""
            print(f"  [{idx:2d}] {dev['name']} - In: {dev['max_input_channels']} ch, Native SR: {int(dev['default_samplerate'])} Hz{is_default}{is_active}")

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
        wave = volume * np.sin(2 * np.pi * freq * t)
        
        fade_samples = int(0.015 * SAMPLE_RATE)
        envelope = np.ones_like(wave)
        if len(wave) > fade_samples * 2:
            envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
            envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        
        audio = (wave * envelope).astype(np.float32)
        sd.play(audio, samplerate=SAMPLE_RATE)
        sd.wait()
    except Exception:
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
    """Cleans up temporary synthesized audio files (.mp3/.wav) in AUDIO_TEMP_DIR."""
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


def test_microphone(duration: float = 3.0) -> Optional[Any]:
    """
    Records audio for `duration` seconds via non-blocking callback, plays it back,
    and returns 16kHz mono audio array. Used for `--test-mic` command.
    """
    if not _AUDIO_DEPS_AVAILABLE:
        print("Cannot test microphone: sounddevice or numpy not installed.")
        return None

    dev_id = get_default_input_device()
    try:
        if dev_id is not None:
            dev_info = sd.query_devices(dev_id, 'input')
            channels = min(max(int(dev_info.get('max_input_channels', 1)), 1), 2)
            native_sr = int(dev_info.get('default_samplerate', SAMPLE_RATE))
            dev_name = dev_info.get('name', f'Device {dev_id}')
        else:
            channels = 1
            native_sr = SAMPLE_RATE
            dev_name = "Default"
    except Exception:
        channels = 1
        native_sr = SAMPLE_RATE
        dev_name = "Default"

    print(f"\n[MIC TEST] Recording {duration:.1f} seconds of audio from [{dev_id}]: {dev_name} ({channels} ch @ {native_sr} Hz)...")
    print(">>> Speak clearly into your microphone now! <<<")
    
    audio_queue: queue.Queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_queue.put(indata.copy())

    try:
        with sd.InputStream(
            device=dev_id,
            samplerate=native_sr,
            channels=channels,
            dtype="float32",
            callback=callback,
        ):
            time.sleep(duration)

        # Collect chunks
        chunks = []
        while not audio_queue.empty():
            chunks.append(audio_queue.get())

        if not chunks:
            print("❌ No audio frames captured from stream.")
            return None

        raw_audio = np.concatenate(chunks, axis=0)
        
        # Downmix to mono if stereo
        if channels > 1:
            mono_audio = np.mean(raw_audio, axis=1)
        else:
            mono_audio = raw_audio.flatten()

        # Resample to 16kHz
        audio_16k = resample_to_16k(mono_audio, native_sr)

        # Calculate RMS energy level
        rms = float(np.sqrt(np.mean(np.square(audio_16k))))
        peak = float(np.max(np.abs(audio_16k)))
        print(f"[MIC TEST] Signal Analysis: Peak={peak:.4f}, RMS Energy={rms:.4f}")
        
        if peak < 0.005:
            print("⚠️  WARNING: Extremely low audio signal detected.")
            print("   Tips:")
            print("   1. Check microphone unmute button and volume in Windows Settings.")
            print("   2. Run 'python -m jarvis.main --list-devices' to check index.")
        else:
            print("✓ Audio signal successfully captured.")

        print("[MIC TEST] Playing back recorded audio through speakers...")
        sd.play(audio_16k, samplerate=SAMPLE_RATE)
        sd.wait()
        print("[MIC TEST] Playback complete.\n")
        return audio_16k

    except Exception as e:
        print(f"❌ Microphone test failed: {e}")
        return None
