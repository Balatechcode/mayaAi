"""
Wake Word detection engine for Jarvis Phase 2.
Uses openwakeword to continuously listen for the wake phrase 'Hey Jarvis'.
Runs at 16kHz mono via sounddevice.
Also provides barge-in interruption detection to halt speech playback immediately.
"""

from __future__ import annotations

import time
import logging
from typing import Optional, Callable, Any

from jarvis.config import (
    SAMPLE_RATE,
    MIC_DEVICE_INDEX,
    WAKE_WORD_MODEL,
    WAKE_WORD_THRESHOLD,
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
    import openwakeword
    from openwakeword.model import Model
    _HAS_OWW = True
except ImportError:
    _HAS_OWW = False


class WakeWordListener:
    """
    Continuous listener for 'Hey Jarvis' wake word.
    Stream chunks into openwakeword model and triggers callback upon detection.
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
                # Attempt loading model directly
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

        # openwakeword processes audio in 1280-sample chunks (80ms at 16kHz)
        chunk_size = 1280
        self._is_listening = True

        if status_callback:
            status_callback("idle")

        print(f"\n💤 Standing by. Say \033[1;36m'Hey Jarvis'\033[0m to activate...")
        logger.info("Entering wake word standby loop...")

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
                dtype="int16",
                device=dev_id,
                blocksize=chunk_size,
            ) as stream:
                while self._is_listening:
                    chunk, overflowed = stream.read(chunk_size)
                    if channels > 1:
                        audio_data = np.mean(chunk, axis=1).astype(np.int16)
                    else:
                        audio_data = chunk.flatten()

                    # Feed 1280 int16 samples into openwakeword
                    prediction = model.predict(audio_data)

                    # Get prediction score for wake word
                    score = prediction.get(self.model_name, 0.0)

                    if score >= self.threshold:
                        logger.info(f"Wake word '{self.model_name}' detected! Score: {score:.3f}")
                        print(f"\n✨ \033[1;32mWake word detected!\033[0m (Score: {score:.2f})")
                        time.sleep(0.3)  # brief debounce
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
