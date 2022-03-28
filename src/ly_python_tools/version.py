"""Configure the package version using the CI environment."""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from subprocess import CalledProcessError  # nosec: B404
from subprocess import run  # nosec: B404
from tempfile import TemporaryDirectory
from typing import Any
from typing import ClassVar
from typing import Mapping
from typing import Match
from typing import Pattern
from typing import Sequence

import click
import toml
from expandvars import expandvars
from poetry.core.version.exceptions import InvalidVersion
from poetry.core.version.version import Version

from .config import get_pyproject


@click.command("version")
@click.option(
    "--repo/--no-repo",
    default=False,
    help="Print the repo name to publish to instead of applying the version.",
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Check what changes would be made",
)
def main(repo: bool, check: bool):
    # noqa: D301
    """
    Application for managing python versions via pyproject.toml file.

    \b
    This application enables:
    * Setting the version and which repo to publish to based on CI environment variables.
    * Validating that the version conforms to canonical pep440.
    * Checking that tags match the version listed in the poetry file.
    * Writing the version to the file containing `__version__ = "..."`
    """
    if repo and check:
        raise click.UsageError("--check and --repo are mutually exclusive.")
    try:
        app = VersionApp.from_pyproject(pyproject=get_pyproject(), apply=not check)
    except (InvalidVersion, ValueError) as exc:
        raise click.ClickException(click.style(str(exc), fg="red")) from exc

    if repo and app.repo:
        click.echo(expandvars(app.repo, nounset=True))
        return

    try:
        app.apply_version()
    except CalledProcessError as exc:
        raise click.ClickException(click.style(exc.output, fg="red")) from exc


@dataclass(frozen=True)
class VersionApp:
    """
    Version application.

    Arguments:
    ---------
    config:
        The config for running the app.
    project_version:
        The original `tool.poetry.version` field.
    apply:
        If True, changes will be applied.

    """

    config: VersionConfig
    project_version: Version
    apply: bool

    # _apply_colors[0] is used when apply = False, otherwise _apply_colors[1] is used.
    _apply_colors: ClassVar[Sequence[str]] = ["yellow", "green"]
    # Informative content (files, commands)
    _content_color: ClassVar[str] = "cyan"
    # Warnings
    _warn_color: ClassVar[str] = "magenta"

    def __post_init__(self):
        self.handler.check_version(self.full_version)

        if self.config.pep440_check and not self.is_canonical:
            raise ValueError(
                f"pyproject version {self.full_version!s} does not conform to pep-440"
            )
        if not self.apply:
            click.secho("Note: This run will not apply any changes.", fg=self._warn_color)

    @property
    def handler(self) -> VersionHandler:
        """Return the handler."""
        return self.config.get_handler()

    @property
    def full_version(self) -> Version:
        """Return the version including all of the extra environment tags."""
        extras = expandvars(self.handler.extra, nounset=True)
        return Version(str(self.project_version) + extras)

    @property
    def is_canonical(self) -> bool:
        """
        Return True if the version is canonical pep440.

        See
        https://peps.python.org/pep-0440/#appendix-b-parsing-version-strings-with-regular-expressions
        """
        return (
            re.match(
                r"^([1-9][0-9]*!)?(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*((a|b|rc)(0|[1-9][0-9]*))?"
                + r"(\.post(0|[1-9][0-9]*))?(\.dev(0|[1-9][0-9]*))?$",
                self.full_version.public,
            )
            is not None
        )

    @property
    def repo(self) -> str | None:
        """Return the repo this version should be published to."""
        return self.handler.repo

    @property
    def _apply_color(self) -> str:
        return "green" if self.apply else "yellow"

    @classmethod
    def from_pyproject(cls, pyproject: Path, apply: bool) -> VersionApp:
        """Load the application from a pyproject.toml file."""
        tool_root = toml.load(pyproject)["tool"]
        return cls(
            config=VersionConfig.from_dict(dict(tool_root.get("version", {}))),
            project_version=Version(tool_root.get("poetry", {}).get("version")),
            apply=apply,
        )

    def apply_version(self) -> VersionApp:
        """Change the version according to the environment."""
        self._apply_version()
        self._write_version_file()
        return self

    def _apply_version(self):
        # Use poetry to set the version
        cmd = ["poetry", "version", str(self.full_version)]

        click.secho(f"The new version is {self.full_version!s}", fg=self._apply_color)
        click.secho(f"{' '.join(cmd)}", fg=self._content_color)
        if not self.apply:
            return

        run(cmd, check=True, capture_output=True)  # nosec

    def _write_version_file(self):
        # Rewrite the version file
        matcher = re.compile(r"^__version__ = \"[^\"]*\".*$")
        version_string = f'__version__ = "{self.full_version!s}"  # Auto-generated'

        if not self.config.version_path:
            return

        with TemporaryDirectory() as outdir:
            new_contents: list[str] = []
            with self.config.version_path.open(encoding="utf-8") as read:
                new_contents = [matcher.sub(version_string, line) for line in read.readlines()]

            outfile = Path(outdir) / "out.py"
            with outfile.open("w") as out:
                out.writelines(new_contents)

            click.secho(f"Rewriting {self.config.version_path!s}", fg=self._apply_color)
            click.secho("".join(new_contents), nl=False, fg=self._content_color)

            if self.apply:
                shutil.copy(outfile, self.config.version_path)


@dataclass(frozen=True)
class VersionConfig:
    """
    Configuration for version tools.

    Arguments:
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

    Arguments:
    ---------
    matchers:
        Environment variables that trigger this handler
    repo:
        Repository location to publish to when this rule is triggered. This can contain
        environment variables.
    extra:
        Additional text to add to the project version when this rule is triggered. This can contain
        environment variables.

    """

    matchers: Sequence[Matcher] = field(default_factory=list)
    repo: str | None = None
    extra: str = ""

    def __post_init__(self):
        if len([1 for matcher in self.matchers if matcher.validate]) > 1:
            raise ValueError("It doesn't make sense to validate more than one matcher")

    def match_env(self) -> bool:
        """Return True if this handler should be triggered."""
        return all(matcher.match_env() for matcher in self.matchers)

    def check_version(self, full_version: Version):
        """Validate the supplied version against the group is validate is True."""
        for matcher in self.matchers:
            matcher.check_version(full_version)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VersionHandler:
        """Load an object from a dict."""
        data_copy = dict(data)
        matchers = data_copy.pop("matchers", [])
        return cls(**data_copy, matchers=[Matcher.from_dict(matcher) for matcher in matchers])


@dataclass(frozen=True)
class Matcher:
    """
    Determine if the environment variable matches a pattern.

    Arguments:
    ---------
    env:
        The environment variable to match on.
    pattern:
        The regex pattern to match on env.
    validate:
        If True, the first group in the pattern must match the version checked-in for this project.

    """

    env: str
    pattern: Pattern[str]
    validate: bool

    @property
    def _matched(self) -> Match[str] | None:
        """Return the matched pattern."""
        # Lint false-positive: https://github.com/PyCQA/pylint/issues/5091
        # pylint: disable=invalid-envvar-value
        return self.pattern.match(os.getenv(self.env, ""))

    def match_env(self) -> bool:
        """Return True if the environment variable matches the pattern."""
        return bool(self._matched)

    def check_version(self, full_version: Version):
        """Raise exception if argument doesn't match the first matching group."""
        if not self.validate:
            return

        if not self._matched:
            raise ValueError("Could not match the regex")

        version = Version(self._matched.groups()[0])
        if version == full_version:
            return
        raise ValueError(
            f"pyproject version {full_version!s} does not match environment version {version!s}"
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Matcher:
        """Load an object from a dict."""
        data_copy = dict(data)
        pattern = re.compile(data_copy.pop("pattern"))
        validate = bool(data_copy.pop("validate", False))
        return cls(**data_copy, pattern=pattern, validate=validate)


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
