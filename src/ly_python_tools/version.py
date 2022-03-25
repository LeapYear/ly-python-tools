from __future__ import annotations

import os
import re
import shutil
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Pattern, Sequence

import click
import pep440
import toml
from poetry.core.version.version import Version

from .config import get_pyproject


@click.command("version")
@click.option(
    "--repo/--no-repo",
    default=False,
    help="Print the repo name to publish to instead of applying the version.",
)
def main(repo: bool):
    """
    Application for managing python versions via pyproject.toml file.

    \b
    This application enables:
    * Setting the version and which repo to publish to based on CI environment variables.
    * Validating that the version conforms to canonical pep440.
    * Checking that tags match the version listed in the poetry file.
    * Writing the version to the file containing `__version__ = "..."`
    """
    app = VersionApp.from_pyproject(get_pyproject())
    if not repo:
        app.apply_version()
    if repo and app.repo:
        click.echo(os.path.expandvars(app.repo))


@dataclass(frozen=True)
class VersionApp:
    """
    Version application.

    Arguments
    ---------
    config:
        The config for running the app.
    project_version:
        The original `tool.poetry.version` field.
    """

    config: VersionConfig
    project_version: str

    def __post_init__(self):
        version = self.handler.get_version()
        if self.handler.validate and version and version != self.full_version:
            raise ValueError(
                f"pyproject version {self.full_version} "
                f"does not match environment version {version}"
            )
        if self.config.pep440_check and not pep440.is_canonical(self.full_version.split("+")[0]):
            raise ValueError(f"pyproject version {self.full_version} does not conform to pep-440")

    @property
    def handler(self) -> VersionHandler:
        """Return the handler."""
        return self.config.get_handler()

    @property
    def full_version(self) -> str:
        """Return the version including all of the extra environment tags."""
        base_version = str(Version(self.project_version).base_version)  # type: ignore
        return base_version + os.path.expandvars(self.handler.extra)

    @property
    def repo(self) -> str | None:
        """Return the repo this version should be published to."""
        return self.handler.repo

    @classmethod
    def from_pyproject(cls, pyproject: Path) -> VersionApp:
        """Load the application from a pyproject.toml file."""
        tool_root = toml.load(pyproject)["tool"]
        return cls(
            config=VersionConfig.from_dict(dict(tool_root.get("version", {}))),
            project_version=str(tool_root.get("poetry", {}).get("version")),
        )

    def apply_version(self) -> VersionApp:
        """Change the version according to the environment."""
        self._apply_version()
        self._write_version_file()
        return self

    def _apply_version(self):
        # Use poetry to set the version
        click.echo(f"Setting version to {self.full_version}")
        run(["poetry", "version", self.full_version], check=True, capture_output=True)

    def _write_version_file(self):
        # Rewrite the version file
        matcher = re.compile(r"^__version__ = \"[^\"]*\"$")
        version_string = f'__version__ = "{self.full_version}"'

        if self.config.version_path:
            with TemporaryDirectory() as outdir:
                outfile = Path(outdir) / "out.py"
                with self.config.version_path.open(encoding="utf-8") as read, outfile.open(
                    "w"
                ) as out:
                    for token in tokenize.generate_tokens(read.readline):
                        if token.type == tokenize.NEWLINE:
                            out.write(matcher.sub(version_string, token.line))
                shutil.copy(outfile, self.config.version_path)


@dataclass(frozen=True)
class VersionConfig:
    """
    Configuration for version tools.

    Arguments
    ---------
    pep440_check:
        If True, ensure the version (up to the first "+") is a valid pep440 version.
    handlers:
        Handlers ordered in which they are checked.
    version_path:
        If provided, the version tool will update this file's `__version__ = "..."` line.
    """

    pep440_check: bool = True
    handlers: Sequence[VersionHandler] = field(default_factory=list)
    version_path: Path | None = None

    def get_handler(self) -> VersionHandler:
        """Return the first activated handler."""
        for handler in self.handlers:
            if handler.match_env():
                return handler
        raise ValueError("No matching handlers found for this build")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VersionConfig:
        """Load an object from a dict."""
        data_copy = dict(data)
        handlers = [VersionHandler.from_dict(handler) for handler in data_copy.pop("handlers", [])]
        version_path = data_copy.pop("version_path", None)
        return cls(
            **data_copy,
            handlers=handlers,
            version_path=Path(version_path) if version_path else None,
        )


@dataclass(frozen=True)
class VersionHandler:
    """
    Rule for configuration and environment based version handler.

    This rule triggers if both `env` and `match` are set or neither are set. If both are set,
    then when the environment variable `env` matches the regex pattern `match`, this rule is
    activated.

    Arguments
    ---------
    env:
        Environment variable to match on
    match:
        Regex pattern to compare to env
    repo:
        Repository location to publish to when this rule is triggered. This can contain
        environment variables.
    extra:
        Additional text to add to the version when this rule is triggered. This can contain
        environment variables.
    validate:
        If True, use the first group in the match to confirm that the final version matches
        exactly.

    Examples
    --------

    * `env, match, extra = "CIRCLE_BRANCH", r"^main$", "a${CIRCLE_BUILD_NUM}"`
        This rule is applied in CircleCI branch jobs on the main branch, and the job number is
        appended to the version.
    * `env, match, extra, validate = "CIRCLE_TAG", r"^v(.*)", "", True`
        This rule is applied on CircleCI tag jobs and the tag must match the version prependded by
        "v".
    """

    env: str | None = None
    match: Pattern[str] | None = None
    repo: str | None = None
    extra: str = ""
    validate: bool = False

    def __post_init__(self):
        if bool(self.env) != bool(self.match):
            raise ValueError('"env" and "match" must both be specified')

    def match_env(self) -> bool:
        """Returns True if this handler should be triggered."""
        if self.env and self.match:
            return bool(self.match.match(os.getenv(self.env) or ""))
        return True

    def get_version(self) -> str | None:
        """Return the group match from the matcher."""
        if self.env and self.match and self.validate:
            match = self.match.match(os.getenv(self.env) or "")
            if match:
                return match.groups()[0]
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> VersionHandler:
        """Load an object from a dict."""
        data_copy = dict(data)
        match = data_copy.pop("match", None)
        validate = bool(data_copy.pop("validate", False))
        return cls(
            **data_copy, validate=validate, match=None if match is None else re.compile(match)
        )
