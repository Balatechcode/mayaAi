"""
LLM abstraction and tool-calling orchestration engine for Jarvis.
Provides an abstract base provider interface for multi-vendor support (Gemini, Claude, etc.)
and a robust, secure implementation for Google Gemini with custom tool loop interception.
"""

import abc
import json
import logging
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from jarvis.config import GEMINI_API_KEY, DEFAULT_MODEL, LOG_FILE
from jarvis.tools import ToolRegistry, registry as default_registry
from jarvis.brain.prompts import JARVIS_SYSTEM_PROMPT

# Configure brain logger
logger = logging.getLogger("JarvisBrain")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [Brain] %(message)s"))
    logger.addHandler(fh)


class BaseLLMProvider(abc.ABC):
    """
    Abstract interface for LLM providers.
    Enables swapping Google Gemini with Anthropic Claude, OpenAI, or local models.
    """

    @abc.abstractmethod
    def chat(self, user_message: str) -> str:
        """
        Sends a user message, runs the tool-calling loop if needed,
        and returns the assistant's final response string.
        """
        pass

    @abc.abstractmethod
    def reset_conversation(self) -> None:
        """Resets the active conversation context."""
        pass


class GeminiLLMProvider(BaseLLMProvider):
    """
    Google Gemini implementation of the LLM provider using the modern google-genai SDK.
    Features:
    - Custom tool-calling interception loop (disables SDK black-box execution for safety)
    - Interactive user confirmation for sensitive/destructive operations
    - Detailed audit logging to logs/jarvis.log
    - Resilient fallback handling for model rate-limits / 503 service spikes
    - Preserves multi-turn conversation memory within the session
    """

    FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.8-flash"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None,
        system_prompt: str = JARVIS_SYSTEM_PROMPT,
        max_tool_iterations: int = 5,
    ):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not found! Please add your key to the .env file in the project root."
            )

        self.model_name = model_name or DEFAULT_MODEL
        self.tool_registry = tool_registry or default_registry
        self.system_prompt = system_prompt
        self.max_tool_iterations = max_tool_iterations

        # Initialize the GenAI Client
        self.client = genai.Client(api_key=self.api_key)

        # In-memory conversation history: list of types.Content objects
        self.history: List[types.Content] = []

    def reset_conversation(self) -> None:
        """Clears the session history."""
        self.history.clear()
        logger.info("Conversation history reset.")

    def _build_generation_config(self) -> types.GenerateContentConfig:
        """Prepares tools, system instructions, and disables internal AFC for manual safety interception."""
        callables = self.tool_registry.get_callables()

        return types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=callables if callables else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )

    def _call_model_with_fallback(self, contents: List[Any], config: types.GenerateContentConfig):
        """
        Calls Gemini generate_content with automatic fallback if the primary model is busy (503/429).
        """
        models_to_try = [self.model_name] + [m for m in self.FALLBACK_MODELS if m != self.model_name]

        last_error = None
        for model in models_to_try:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                return resp
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Model '{model}' failed: {err_str[:120]}. Trying fallback if available...")
                last_error = e
                # If it's a quota or 503 issue, try the next model
                if any(code in err_str for code in ["503", "429", "RESOURCE_EXHAUSTED", "NOT_FOUND"]):
                    time.sleep(1)
                    continue
                # For invalid input or auth errors, do not retry
                raise e

        # If all candidates exhausted, raise last error
        raise last_error or RuntimeError("All model endpoints failed to respond.")

    def chat(self, user_message: str) -> str:
        """
        Main chat execution loop.
        Sends user message, executes tool calls iteratively with security confirmation,
        and returns the final synthesized natural language response.
        """
        if not user_message or not user_message.strip():
            return "Sir, I didn't receive any input. How may I assist you?"

        clean_input = user_message.strip()
        logger.info(f"User input: {clean_input}")

        # Add user turn to conversation history
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=clean_input)],
        )
        self.history.append(user_content)

        config = self._build_generation_config()

        # Tool-calling loop
        iteration = 0
        while iteration < self.max_tool_iterations:
            iteration += 1

            try:
                # Call Gemini with entire current history
                response = self._call_model_with_fallback(
                    contents=self.history,
                    config=config,
                )
            except Exception as e:
                logger.exception(f"Gemini API generation failed: {e}")
                err_msg = (
                    f"Apologies, Sir. I encountered an issue communicating with my neural core: {type(e).__name__}: {str(e)[:150]}.\n"
                    "Please verify your API key or network connection."
                )
                return err_msg

            # Verify if response contains function calls
            function_calls = response.function_calls

            if not function_calls:
                # Model provided final text response
                model_text = response.text or ""
                # Append model response to conversation history
                if response.candidates and response.candidates[0].content:
                    self.history.append(response.candidates[0].content)
                logger.info(f"Jarvis response: {model_text[:150]}")
                return model_text

            # Model requested one or more tool calls
            # 1. Append the model's function_call turn to history
            if response.candidates and response.candidates[0].content:
                self.history.append(response.candidates[0].content)

            # 2. Execute each requested tool and collect function responses
            tool_response_parts = []
            for fc in function_calls:
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}

                print(f"\n[Jarvis is using tool: \033[1;36m{tool_name}\033[0m]")
                logger.info(f"LLM requested tool '{tool_name}' with args: {tool_args}")

                # Execute through registry (handles safety confirmation, logging, error handling)
                tool_result = self.tool_registry.execute(tool_name, **tool_args)

                # Format response for Gemini
                if not isinstance(tool_result, dict):
                    resp_dict = {"result": str(tool_result)}
                else:
                    resp_dict = tool_result

                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response=resp_dict,
                    )
                )

            # 3. Append the tool responses turn to history
            tool_response_content = types.Content(
                role="user",
                parts=tool_response_parts,
            )
            self.history.append(tool_response_content)

        # If loop limit exceeded
        warning_msg = (
            "Sir, I have reached the maximum tool execution limit for this request. "
            "Here is the progress so far. Please let me know how you would like to proceed."
        )
        logger.warning("Tool calling iteration limit reached.")
        return warning_msg


class ClaudeLLMProvider(BaseLLMProvider):
    """
    Architecture placeholder for Anthropic Claude.
    Ready for seamless drop-in replacement in future iterations.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model_name = model_name

    def chat(self, user_message: str) -> str:
        raise NotImplementedError(
            "Claude provider is staged for future phases. Currently active provider is Gemini."
        )

    def reset_conversation(self) -> None:
        pass
