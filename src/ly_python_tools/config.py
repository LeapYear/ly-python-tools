from __future__ import annotations

from pathlib import Path
from typing import Sequence


def get_pyproject(config_name: Path | str = "pyproject.toml") -> Path:
    cwd = Path.cwd().absolute()
    paths = [cwd] + list(cwd.parents)
    for path in paths:
        pyproject = path / config_name
        if pyproject.exists() and pyproject.is_file():
            return pyproject
    raise NoProjectFile(config_name, search_paths=paths)


class NoProjectFile(Exception):
    """No project file could be found."""

    def __init__(self, proj_filename: Path | str, search_paths: Sequence[Path]):
        self.proj_filename = str(proj_filename)
        self.search_paths = [path.as_posix() for path in search_paths]
