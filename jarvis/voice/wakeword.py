"""
Wake Word detection engine for Jarvis Phase 2.
Uses openwakeword to continuously listen for the wake phrase 'Hey Jarvis'.
Runs via non-blocking callback streams compatible with all Windows audio drivers.
"""

from __future__ import annotations

import time
import queue
import logging
from typing import Optional, Callable, Any

from jarvis.config import (
    SAMPLE_RATE,
    WAKE_WORD_MODEL,
    WAKE_WORD_THRESHOLD,
    LOG_FILE,
)
from jarvis.voice.audio_utils import get_default_input_device, get_device_native_sr, resample_to_16k

logger = logging.getLogger("JarvisVoice")

# Optional imports
try:
    import numpy as np
    import sounddevice as sd
    _HAS_SD = True
except ImportError:
    _HAS_SD = False

try:
    import openwakeword
    from openwakeword.model import Model
    _HAS_OWW = True
except ImportError:
    _HAS_OWW = False


class WakeWordListener:
    """
    Continuous listener for 'Hey Jarvis' wake word.
    Buffers audio via callback stream, resamples to 16kHz, and feeds openwakeword.
    """

    def __init__(
        self,
        model_name: str = WAKE_WORD_MODEL,
        threshold: float = WAKE_WORD_THRESHOLD,
    ):
        self.model_name = model_name
        self.threshold = threshold
        self._model: Optional[Model] = None
        self._is_listening = False

    def _load_model(self) -> Model:
        """Loads the openwakeword model, downloading pretrained weights if necessary."""
        if self._model is None:
            if not _HAS_OWW:
                raise RuntimeError("openwakeword is not installed. Run 'pip install openwakeword'.")

            try:
                self._model = Model(wakeword_models=[self.model_name], inference_framework="onnx")
            except Exception as e:
                logger.info(f"Downloading openwakeword models ({e})...")
                print("[Downloading openwakeword pretrained models...]")
                try:
                    openwakeword.utils.download_models()
                    self._model = Model(wakeword_models=[self.model_name], inference_framework="onnx")
                except Exception as dl_err:
                    logger.exception(f"Failed to initialize openwakeword model: {dl_err}")
                    raise dl_err

            logger.info(f"openwakeword model '{self.model_name}' loaded successfully.")
        return self._model

    def wait_for_wake_word(self, status_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Blocks and continuously monitors microphone audio until 'Hey Jarvis' is detected.
        Returns True when wake word is detected, False if stopped.
        """
        if not _HAS_SD or not _HAS_OWW:
            print("Sounddevice or openwakeword not available. Cannot listen for wake word.")
            return False

        model = self._load_model()
        model.reset()

        dev_id = get_default_input_device()
        native_sr = get_device_native_sr(dev_id)

        try:
            if dev_id is not None:
                dev_info = sd.query_devices(dev_id, 'input')
                channels = min(max(int(dev_info.get('max_input_channels', 1)), 1), 2)
            else:
                channels = 1
        except Exception:
            channels = 1

        audio_queue: queue.Queue = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            if channels > 1:
                mono = np.mean(indata, axis=1)
            else:
                mono = indata.flatten()
            audio_queue.put(mono.copy())

        self._is_listening = True
        chunk_16k_size = 1280  # openwakeword requires 1280 samples at 16kHz
        accumulator = np.zeros(0, dtype=np.float32)

        if status_callback:
            status_callback("idle")

        print(f"\n💤 Standing by. Say \033[1;36m'Hey Jarvis'\033[0m to activate...")
        logger.info(f"Entering wake word standby loop on device [{dev_id}] @ {native_sr}Hz...")

        try:
            with sd.InputStream(
                device=dev_id,
                samplerate=native_sr,
                channels=channels,
                dtype="float32",
                callback=audio_callback,
            ):
                while self._is_listening:
                    try:
                        chunk = audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    # Resample to 16kHz if needed
                    chunk_16k = resample_to_16k(chunk, native_sr)
                    accumulator = np.append(accumulator, chunk_16k)

                    # Feed chunks of 1280 samples into openwakeword
                    while len(accumulator) >= chunk_16k_size:
                        sub_chunk = accumulator[:chunk_16k_size]
                        accumulator = accumulator[chunk_16k_size:]

                        # Convert float32 [-1.0, 1.0] to int16 [-32768, 32767]
                        audio_int16 = (sub_chunk * 32767).clip(-32768, 32767).astype(np.int16)
                        prediction = model.predict(audio_int16)

                        score = prediction.get(self.model_name, 0.0)

                        if score >= self.threshold:
                            logger.info(f"Wake word '{self.model_name}' detected! Score: {score:.3f}")
                            print(f"\n✨ \033[1;32mWake word detected!\033[0m (Score: {score:.2f})")
                            time.sleep(0.3)
                            return True

            return False

        except KeyboardInterrupt:
            self._is_listening = False
            return False
        except Exception as e:
            logger.exception(f"Error in wake word listener: {e}")
            print(f"Wake word listener error: {e}")
            return False

    def stop(self) -> None:
        """Stops the active wake word loop."""
        self._is_listening = False


# Global wake word listener
wakeword_listener = WakeWordListener()
wait_for_wake_word = wakeword_listener.wait_for_wake_word
