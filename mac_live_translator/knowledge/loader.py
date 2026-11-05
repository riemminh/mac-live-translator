"""Safe directory scanner and file path collector with depth and symlink bounds."""

from __future__ import annotations

import os
from pathlib import Path

MAX_FOLDER_FILES = 100
MAX_FOLDER_DEPTH = 3
IGNORED_DIR_NAMES = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".idea", ".vscode"}
SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt"}


def collect_folder_files(root: Path) -> list[Path]:
    """Safely traverse folder up to MAX_FOLDER_DEPTH, capping total files and skipping symlink escapes."""
    results: list[Path] = []
    root_str = str(root)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_path = os.path.relpath(dirpath, root_str)
        depth = 0 if rel_path == "." else len(Path(rel_path).parts)
        if depth >= MAX_FOLDER_DEPTH:
            dirnames.clear()
            continue

        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_NAMES and not d.startswith(".")]

        for fname in sorted(filenames):
            if len(results) >= MAX_FOLDER_FILES:
                return results
            ext = Path(fname).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                file_path = Path(dirpath) / fname
                try:
                    resolved = file_path.resolve()
                    if not resolved.is_relative_to(root):
                        continue
                except (ValueError, RuntimeError):
                    continue
                results.append(file_path)

    return results

