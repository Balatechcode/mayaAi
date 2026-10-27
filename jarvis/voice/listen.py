"""
Speech-to-Text (STT) and Voice Activity Detection (VAD) module for Jarvis.
Captures microphone audio at 16kHz mono via sounddevice.
Detects speech onset and stops automatically after ~1.5s of silence (or 20s max).
Transcribes using local faster-whisper with automatic language detection (hi / en)
and aggressive filtering of silence hallucinations.
"""

from __future__ import annotations

import time
import re
import logging
from typing import Optional, Tuple, List, Any
from pathlib import Path

from jarvis.config import (
    SAMPLE_RATE,
    MIC_DEVICE_INDEX,
    VAD_SILENCE_TIMEOUT,
    MAX_RECORD_SECONDS,
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    LOG_FILE,
)
from jarvis.voice.audio_utils import get_default_input_device

logger = logging.getLogger("JarvisVoice")

# Optional imports
try:
    import numpy as np
    import sounddevice as sd
    _HAS_SD = True
except ImportError:
    _HAS_SD = False

try:
    from faster_whisper import WhisperModel
    _HAS_WHISPER = True
except ImportError:
    _HAS_WHISPER = False


# Hinglish prompt to guide Whisper tokenizer
HINGLISH_INITIAL_PROMPT = (
    "Jarvis, what time is it, aaj ka weather, open application, notepad, calculator, "
    "chrome, website, search, read file, write file, list files, delete file, "
    "haan, nahi, yes, no, ruko, kar do, theek hai, Namaste."
)

# Known common Whisper hallucinations on ambient noise / silence
HALLUCINATION_PHRASES = {
    "thank you", "thank you.", "thank you very much.", "thanks for watching",
    "thanks for watching.", "please subscribe", "subtitles by", "bye.", "bye",
    "you", "...", ".", "the end", "so", "oh", "um", "ah"
}


class SpeechToText:
    """
    Local speech transcription engine using faster-whisper.
    Performs Voice Activity Detection (VAD) to record speech accurately
    and transcribes with auto-detected language.
    """

    def __init__(
        self,
        model_size: str = WHISPER_MODEL_SIZE,
        device: str = WHISPER_DEVICE,
        compute_type: str = WHISPER_COMPUTE_TYPE,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def _load_model(self) -> WhisperModel:
        """Loads or returns the cached local faster-whisper model."""
        if self._model is None:
            if not _HAS_WHISPER:
                raise RuntimeError("faster-whisper is not installed. Run 'pip install faster-whisper'.")
            
            print(f"[Loading local Whisper model: '{self.model_size}' on {self.device} ({self.compute_type})...]")
            logger.info(f"Loading faster-whisper model '{self.model_size}'...")
            t0 = time.time()
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info(f"Whisper model loaded in {time.time()-t0:.2f}s")
            print("[Whisper model ready.]")
        return self._model

    def record_command(
        self,
        max_duration: float = MAX_RECORD_SECONDS,
        silence_timeout: float = VAD_SILENCE_TIMEOUT,
        energy_threshold: Optional[float] = None,
    ) -> Optional[np.ndarray]:
        """
        Records audio from microphone using Voice Activity Detection (VAD).
        - Listens for speech to start.
        - Automatically terminates when silence is detected for >= silence_timeout seconds.
        - Caps recording at max_duration.
        """
        if not _HAS_SD:
            print("Sounddevice/numpy not installed. Cannot record.")
            return None

        chunk_duration = 0.1  # 100ms chunks
        chunk_samples = int(SAMPLE_RATE * chunk_duration)
        recorded_chunks: List[np.ndarray] = []

        # Stream recording with sounddevice
        speech_started = False
        silence_start_time: Optional[float] = None
        start_time = time.time()
        initial_listen_timeout = 6.0  # seconds to wait for user to start speaking

        # Compute dynamic noise floor if energy_threshold not specified
        noise_samples: List[float] = []

        # Detect input device and channels
        dev_id = get_default_input_device()
        try:
            if dev_id is not None:
                dev_info = sd.query_devices(dev_id, 'input')
                channels = min(max(int(dev_info.get('max_input_channels', 1)), 1), 2)
            else:
                channels = 1
        except Exception:
            channels = 1

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=channels,
                dtype="float32",
                device=dev_id,
                blocksize=chunk_samples,
            ) as stream:
                print("🎙️  Listening... (speak your command)")

                while True:
                    chunk, overflowed = stream.read(chunk_samples)
                    if channels > 1:
                        chunk_flat = np.mean(chunk, axis=1)
                    else:
                        chunk_flat = chunk.flatten()
                    recorded_chunks.append(chunk_flat)

                    # Calculate RMS energy of current chunk
                    rms = float(np.sqrt(np.mean(np.square(chunk_flat))))
                    elapsed = time.time() - start_time

                    # First 300ms: sample background noise floor
                    if elapsed < 0.3:
                        noise_samples.append(rms)
                        continue

                    # Establish dynamic threshold
                    if energy_threshold is None:
                        bg_noise = float(np.mean(noise_samples)) if noise_samples else 0.005
                        thresh = max(bg_noise * 2.5, 0.012)
                    else:
                        thresh = energy_threshold

                    # Check for speech onset
                    if rms > thresh:
                        if not speech_started:
                            speech_started = True
                            logger.info(f"Speech detected (RMS: {rms:.4f} > {thresh:.4f})")
                        silence_start_time = None  # reset silence timer
                    else:
                        # Below threshold
                        if speech_started:
                            if silence_start_time is None:
                                silence_start_time = time.time()
                            elif (time.time() - silence_start_time) >= silence_timeout:
                                # Silence threshold reached after speech
                                logger.info(f"Silence detected ({silence_timeout}s). Ending recording.")
                                break

                    # Timeout if user didn't speak
                    if not speech_started and elapsed >= initial_listen_timeout:
                        logger.info("No speech detected within initial listen window.")
                        return None

                    # Max duration limit
                    if elapsed >= max_duration:
                        logger.info(f"Max recording limit ({max_duration}s) reached.")
                        break

            if not recorded_chunks:
                return None

            audio_data = np.concatenate(recorded_chunks, axis=0)
            return audio_data

        except Exception as e:
            logger.exception(f"Error recording audio: {e}")
            print(f"Recording error: {e}")
            return None

    def transcribe(self, audio_data: np.ndarray) -> Tuple[Optional[str], Optional[str]]:
        """
        Transcribes numpy audio array using faster-whisper.
        Returns (transcribed_text, detected_language).
        Filters out hallucinations and empty noise.
        """
        if audio_data is None or len(audio_data) == 0:
            return None, None

        # Check peak amplitude to discard pure silence
        peak = float(np.max(np.abs(audio_data)))
        if peak < 0.01:
            logger.info(f"Audio peak ({peak:.4f}) is below noise threshold. Skipping transcription.")
            return None, None

        try:
            model = self._load_model()
            t0 = time.time()

            # Transcribe with auto language detection (hi / en)
            segments, info = model.transcribe(
                audio_data,
                beam_size=5,
                language=None,  # auto-detect
                initial_prompt=HINGLISH_INITIAL_PROMPT,
                vad_filter=True,  # Built-in Silero-VAD filtering
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            # Collect segments
            text_segments = [s.text.strip() for s in segments if s.text]
            full_text = " ".join(text_segments).strip()
            detected_lang = info.language
            prob = round(info.language_probability, 2)
            duration = round(time.time() - t0, 2)

            logger.info(
                f"Whisper transcription in {duration}s: '{full_text}' "
                f"[Lang: {detected_lang} ({prob})]"
            )

            # Hallucination filter
            cleaned = full_text.lower().strip(".,!?:;\"'")
            if not cleaned or len(cleaned) <= 2:
                logger.info(f"Discarding short noise transcript: '{full_text}'")
                return None, None

            if cleaned in HALLUCINATION_PHRASES:
                logger.info(f"Discarding known Whisper hallucination: '{full_text}'")
                return None, None

            return full_text, detected_lang

        except Exception as e:
            logger.exception(f"Transcription failed: {e}")
            print(f"Transcription error: {e}")
            return None, None


# Global listener instance
listener = SpeechToText()
record_command = listener.record_command
transcribe = listener.transcribe
