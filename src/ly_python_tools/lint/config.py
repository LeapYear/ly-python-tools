from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Mapping, Pattern, Sequence

import toml

from ..config import NoProjectFile, get_pyproject
from .linter import DEFAULT_LINTERS, Linter

__all__ = ["LintConfiguration", "NoProjectFile"]


@dataclass
class LintConfiguration:
    """Configuration for running all of the linters."""

    name: str
    linters: Sequence[Linter]
    include: Pattern[str]
    _config_file: ClassVar[Path] = Path("pyproject.toml")

    @classmethod
    def get_config(cls) -> LintConfiguration:
        pyproject = cls.get_configfile()
        lint_config: Mapping[str, Any] = toml.load(pyproject).get("tool", {}).get("lint", {})
        include = re.compile(lint_config.get("include", r"\.py$"))
        linters = [
            linter.update(lint_config.get(linter_name, {}))
            for linter_name, linter in DEFAULT_LINTERS.items()
        ]
        return LintConfiguration(linters=linters, name=pyproject.parent.name, include=include)

    @classmethod
    def get_configfile(cls) -> Path:
        return get_pyproject(cls._config_file)
