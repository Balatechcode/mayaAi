"""
System management tools for Jarvis.
Provides time, application launching, system info, and Windows utility controls.
"""

import os
import sys
import subprocess
import platform
from datetime import datetime
from jarvis.tools import tool
from jarvis.config import SAFE_APPLICATION_MAP, REQUIRE_CONFIRMATION


@tool
def get_time() -> str:
    """
    Returns the current date, time, day of the week, and local timezone.
    Use this whenever the user asks for the current time or date.
    """
    now = datetime.now().astimezone()
    return now.strftime("Current time: %I:%M:%S %p (%Z) on %A, %B %d, %Y")


@tool
def open_application(app_name: str) -> str:
    """
    Opens an application on the user's computer.
    Examples of supported applications: notepad, calc, paint, explorer, chrome, edge, code, terminal.
    
    Args:
        app_name: Name of the application to launch (e.g. 'notepad', 'calc', 'chrome').
    """
    app_key = app_name.lower().strip()
    
    # Check if app is in safe allow-list
    if app_key in SAFE_APPLICATION_MAP:
        executable = SAFE_APPLICATION_MAP[app_key]
        try:
            if platform.system() == "Windows":
                # Use subprocess.Popen with safe direct executable path (no shell=True)
                subprocess.Popen([executable])
            else:
                subprocess.Popen([executable])
            return f"Successfully launched {app_name} ({executable})."
        except Exception as e:
            return f"Failed to open '{app_name}': {str(e)}"
    
    # If not in safe list, we check if confirmation is required
    if REQUIRE_CONFIRMATION:
        print(f"\n⚠️  Application '{app_name}' is not in the pre-approved safe list.")
        choice = input(f"Are you sure you want to launch '{app_name}'? [y/N]: ").strip().lower()
        if choice not in ("y", "yes"):
            return f"Launch of application '{app_name}' was cancelled by the user."

    # Try launching securely without shell
    try:
        subprocess.Popen([app_name])
        return f"Application '{app_name}' launched."
    except Exception as e:
        return f"Unable to launch '{app_name}'. Error: {str(e)}. Tip: Try standard apps like notepad, calc, paint, chrome."


@tool
def get_system_status() -> str:
    """
    Returns basic operating system information, platform, and python version.
    """
    return (
        f"OS: {platform.system()} {platform.release()} ({platform.version()})\n"
        f"Architecture: {platform.machine()}\n"
        f"Python: {platform.python_version()}\n"
        f"Node/Hostname: {platform.node()}"
    )
