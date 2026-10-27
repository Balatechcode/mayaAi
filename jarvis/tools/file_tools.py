"""
Sandboxed file management tools for Jarvis.
All file reads, writes, and listings are strictly confined to the configured WORKSPACE_DIR.
Path traversal attempts outside the workspace are blocked with security errors.
Destructive operations (such as deleting or overwriting) mandate user confirmation.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from jarvis.tools import tool
from jarvis.config import WORKSPACE_DIR, validate_workspace_path, REQUIRE_CONFIRMATION


@tool
def list_files(subfolder: str = "") -> str:
    """
    Lists all files and subdirectories located inside Jarvis's safe workspace directory.
    
    Args:
        subfolder: Optional subfolder path inside the workspace to inspect.
    """
    try:
        target_dir = validate_workspace_path(subfolder)
        if not target_dir.exists():
            return f"Directory does not exist: '{subfolder}' inside workspace."
        if not target_dir.is_dir():
            return f"'{subfolder}' is a file, not a directory."

        entries = list(target_dir.iterdir())
        if not entries:
            return f"The workspace directory ('{subfolder or '.'}') is currently empty."

        output = [f"Contents of workspace/{subfolder}:"]
        for entry in sorted(entries, key=lambda x: (not x.is_dir(), x.name.lower())):
            entry_type = "[DIR] " if entry.is_dir() else "[FILE]"
            size_str = ""
            if entry.is_file():
                size_kb = entry.stat().st_size / 1024
                size_str = f" ({size_kb:.1f} KB)"
            mtime = datetime.fromtimestamp(entry.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            output.append(f"  {entry_type} {entry.name:<25} {size_str:<12} [Modified: {mtime}]")

        return "\n".join(output)
    except PermissionError as pe:
        return str(pe)
    except Exception as e:
        return f"Error listing workspace files: {str(e)}"


@tool
def read_file(filename: str) -> str:
    """
    Reads the text content of a file located inside the safe workspace directory.
    
    Args:
        filename: Relative path/filename of the file to read from the workspace.
    """
    try:
        target_path = validate_workspace_path(filename)
        if not target_path.exists():
            return f"File not found: '{filename}' in workspace."
        if not target_path.is_file():
            return f"Target '{filename}' is a directory, not a readable file."

        # Safety check for file size (e.g. limit to 1MB text reading)
        if target_path.stat().st_size > 1024 * 1024:
            return f"File '{filename}' exceeds 1MB limit for direct reading."

        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        return f"--- Content of '{filename}' ({len(content)} characters) ---\n{content}"
    except PermissionError as pe:
        return str(pe)
    except Exception as e:
        return f"Error reading file '{filename}': {str(e)}"


@tool
def write_file(filename: str, content: str, overwrite: bool = False) -> str:
    """
    Creates or updates a file inside the safe workspace folder.
    
    Args:
        filename: Name/relative path of the file to save in the workspace.
        content: The text content to write into the file.
        overwrite: Set to True if you want to overwrite an already existing file.
    """
    try:
        target_path = validate_workspace_path(filename)

        # Check if file already exists
        if target_path.exists() and not overwrite:
            return (
                f"File '{filename}' already exists. "
                "To prevent accidental data loss, specify overwrite=True or choose a different name."
            )

        # If overwriting existing file and confirmation is enabled, prompt user
        if target_path.exists() and overwrite and REQUIRE_CONFIRMATION:
            print(f"\n⚠️  CONFIRMATION REQUIRED: Overwrite existing file '{filename}' in workspace?")
            confirm = input("Confirm overwrite? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                return f"Overwriting file '{filename}' was cancelled by the user."

        # Ensure parent directories inside workspace exist
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully saved {len(content)} characters to '{filename}' inside workspace."
    except PermissionError as pe:
        return str(pe)
    except Exception as e:
        return f"Error writing file '{filename}': {str(e)}"


@tool(requires_confirmation=True, confirmation_message="Permanently delete a file from the workspace")
def delete_file(filename: str) -> str:
    """
    Permanently deletes a file from the safe workspace directory.
    Always requires explicit user confirmation before executing.
    
    Args:
        filename: Name/relative path of the file inside the workspace to delete.
    """
    try:
        target_path = validate_workspace_path(filename)
        if not target_path.exists():
            return f"Cannot delete: File '{filename}' does not exist in workspace."
        if not target_path.is_file():
            return f"Cannot delete: '{filename}' is a directory, not a file."

        target_path.unlink()
        return f"File '{filename}' was permanently deleted from the workspace."
    except PermissionError as pe:
        return str(pe)
    except Exception as e:
        return f"Error deleting file '{filename}': {str(e)}"


@tool
def search_workspace(keyword: str) -> str:
    """
    Searches for files inside the workspace that match a keyword in their name or contents.
    
    Args:
        keyword: The keyword or phrase to search for.
    """
    try:
        matches = []
        kw = keyword.lower()
        for root, _, files in os.walk(WORKSPACE_DIR):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(WORKSPACE_DIR)
                
                # Check filename match
                if kw in file.lower():
                    matches.append(f"[Filename Match] {rel_path}")
                    continue
                
                # Check text content match for small files
                try:
                    if full_path.stat().st_size < 200 * 1024:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            text = f.read()
                            if kw in text.lower():
                                matches.append(f"[Content Match]  {rel_path}")
                except Exception:
                    pass

        if not matches:
            return f"No matches found for keyword '{keyword}' in workspace."

        return f"Found {len(matches)} match(es) for '{keyword}':\n" + "\n".join(matches)
    except Exception as e:
        return f"Error searching workspace: {str(e)}"
