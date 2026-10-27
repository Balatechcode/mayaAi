"""
Tool registry and decorator system for Jarvis.
Allows any Python function with type hints and a docstring to be exposed to LLMs.
Includes safety guards, user confirmation for sensitive actions, and structured logging.
"""

import functools
import inspect
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from jarvis.config import LOG_FILE, REQUIRE_CONFIRMATION

# Set up logging for tool executions
logger = logging.getLogger("JarvisTools")
logger.setLevel(logging.INFO)

# Ensure file handler exists
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [Tool: %(name)s] %(message)s"))
    logger.addHandler(fh)


class Tool:
    """Represents a registered tool callable with metadata."""

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        requires_confirmation: bool = False,
        confirmation_message: Optional[str] = None,
    ):
        self.func = func
        self.name = name or func.__name__
        self.description = description or (func.__doc__ or "").strip()
        self.requires_confirmation = requires_confirmation
        self.confirmation_message = confirmation_message
        self.signature = inspect.signature(func)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def get_schema(self) -> Dict[str, Any]:
        """
        Returns JSON-schema compatible parameter descriptions
        derived from Python type hints and signature.
        """
        parameters: Dict[str, Any] = {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        }

        type_map = {
            str: "STRING",
            int: "INTEGER",
            float: "NUMBER",
            bool: "BOOLEAN",
            list: "ARRAY",
            dict: "OBJECT",
        }

        for param_name, param in self.signature.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = type_map.get(param.annotation, "STRING")
            parameters["properties"][param_name] = {
                "type": param_type,
                "description": f"Parameter: {param_name}",
            }

            if param.default is inspect.Parameter.empty:
                parameters["required"].append(param_name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
        }


class ToolRegistry:
    """Central registry of tools available to Jarvis."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self.confirmation_handler: Optional[Callable[[str, Dict[str, Any]], bool]] = None

    def register(
        self,
        func: Optional[Callable] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        requires_confirmation: bool = False,
        confirmation_message: Optional[str] = None,
    ):
        """
        Decorator to register a function as a tool.
        Usage:
            @registry.register
            def my_tool(x: int) -> str:
                ...
        or:
            @registry.register(requires_confirmation=True)
            def delete_something(...):
                ...
        """
        def decorator(f: Callable) -> Callable:
            tool_obj = Tool(
                func=f,
                name=name,
                description=description,
                requires_confirmation=requires_confirmation,
                confirmation_message=confirmation_message,
            )
            self._tools[tool_obj.name] = tool_obj
            f._jarvis_tool = tool_obj  # type: ignore
            return f

        if func is not None and callable(func):
            return decorator(func)
        return decorator

    def get(self, name: str) -> Optional[Tool]:
        """Retrieve tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> List[Tool]:
        """Return list of all registered Tool objects."""
        return list(self._tools.values())

    def get_callables(self) -> List[Callable]:
        """Return list of the raw callable functions for SDK direct binding."""
        return [t.func for t in self._tools.values()]

    def ask_user_confirmation(self, tool: Tool, kwargs: Dict[str, Any]) -> bool:
        """
        Interactive confirmation prompt for sensitive actions.
        Can be overridden via custom confirmation_handler.
        """
        if self.confirmation_handler:
            return self.confirmation_handler(tool.name, kwargs)

        print("\n" + "=" * 50)
        print(f"⚠️  SECURITY CONFIRMATION REQUIRED FOR: {tool.name}")
        msg = tool.confirmation_message or f"Jarvis is requesting permission to execute '{tool.name}'."
        print(f"Action: {msg}")
        print(f"Arguments: {json.dumps(kwargs, default=str, indent=2)}")
        print("=" * 50)

        try:
            choice = input("Do you authorize this action? [y/N]: ").strip().lower()
            return choice in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            return False

    def execute(self, tool_name: str, **kwargs) -> Any:
        """
        Executes a registered tool by name with safety checks and logging.
        """
        tool = self.get(tool_name)
        if not tool:
            err_msg = f"Error: Tool '{tool_name}' is not registered."
            logger.error(err_msg)
            return {"error": err_msg}

        # Safety confirmation check
        if REQUIRE_CONFIRMATION and tool.requires_confirmation:
            confirmed = self.ask_user_confirmation(tool, kwargs)
            if not confirmed:
                logger.warning(f"Action '{tool_name}' was aborted by user.")
                return {
                    "aborted": True,
                    "message": f"Action '{tool_name}' was denied/aborted by the user.",
                }

        start_time = time.time()
        logger.info(f"Executing '{tool_name}' with args: {kwargs}")

        try:
            result = tool(**kwargs)
            duration = round((time.time() - start_time) * 1000, 2)
            logger.info(f"Tool '{tool_name}' completed in {duration}ms. Result: {str(result)[:200]}")
            return result
        except Exception as e:
            duration = round((time.time() - start_time) * 1000, 2)
            err = f"Execution failed for '{tool_name}' after {duration}ms: {type(e).__name__}: {str(e)}"
            logger.exception(err)
            return {"error": err}


# Global tool registry instance
registry = ToolRegistry()
tool = registry.register
