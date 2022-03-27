"""Configure the package version using the CI environment."""
from __future__ import annotations

import os
import re
import shutil
import tokenize
from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from pathlib import Path
from subprocess import check_output  # nosec: B404
from tempfile import TemporaryDirectory
from textwrap import indent
from typing import Any
from typing import Mapping
from typing import Match
from typing import Pattern
from typing import Sequence

import click
import toml
from expandvars import expandvars
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
    app = VersionApp.from_pyproject(get_pyproject())
    if check:
        click.echo("Note: This run will not apply any changes")
    if not repo:
        app.apply_version(not check)
    if repo and app.repo:
        click.echo(expandvars(app.repo))


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

    """

    config: VersionConfig
    project_version: str

    def __post_init__(self):
        version = self.handler.get_version()
        for matcher in self.handler.matchers:
            if matcher.validate and version and version != str(self.full_version):
                raise ValueError(
                    f"pyproject version {self.full_version} "
                    f"does not match environment version {version}"
                )
        if self.config.pep440_check and not is_canonical(self.full_version):
            raise ValueError(
                f"pyproject version {self.full_version!s} does not conform to pep-440"
            )

    @property
    def handler(self) -> VersionHandler:
        """Return the handler."""
        return self.config.get_handler()

    @property
    def full_version(self) -> Version:
        """Return the version including all of the extra environment tags."""
        base_version = str(Version(self.project_version).base_version)  # type: ignore
        return Version(base_version + expandvars(self.handler.extra))

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

    def apply_version(self, apply: bool) -> VersionApp:
        """Change the version according to the environment."""
        self._apply_version(apply=apply)
        self._write_version_file(apply=apply)
        return self

    def _apply_version(self, apply: bool):
        # Use poetry to set the version
        click.echo(f"Setting version to {self.full_version}")
        cmd = ["poetry", "version", str(self.full_version)]
        click.echo(f"> {' '.join(cmd)}")
        if apply:
            check_output(cmd)  # nosec

    def _write_version_file(self, apply: bool):
        # Rewrite the version file
        matcher = re.compile(r"^__version__ = \"[^\"]*\".*$")
        version_string = f'__version__ = "{self.full_version!s}"  # Auto-generated'

        if self.config.version_path:
            with TemporaryDirectory() as outdir:
                outfile = Path(outdir) / "out.py"
                with self.config.version_path.open(encoding="utf-8") as read, outfile.open(
                    "w"
                ) as out:
                    for token in tokenize.generate_tokens(read.readline):
                        if token.type == tokenize.NL:
                            out.write(token.line)
                        if token.type == tokenize.NEWLINE:
                            out.write(matcher.sub(version_string, token.line))

                click.echo(f"Write to {self.config.version_path!s}")
                with outfile.open("r") as out:
                    click.echo(indent(out.read(), "> ", predicate=lambda _: True), nl=False)

                if apply:
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

    matchers: Sequence[Matcher] = field(default_factory=list)
    repo: str | None = None
    extra: str = ""

    def __post_init__(self):
        if len([1 for matcher in self.matchers if matcher.validate]) > 1:
            raise ValueError("It doesn't make sense to validate more than one matcher")

    def match_env(self) -> bool:
        """Return True if this handler should be triggered."""
        return all(matcher.match_env() for matcher in self.matchers)

    def get_version(self) -> str | None:
        """Return the group match from the matcher."""
        for matcher in self.matchers:
            if matcher.validate:
                return matcher.get_version()
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VersionHandler:
        """Load an object from a dict."""
        data_copy = dict(data)
        matchers = data_copy.pop("matchers", [])
        return cls(**data_copy, matchers=[Matcher.from_dict(matcher) for matcher in matchers])


@dataclass(frozen=True)
class Matcher:
    """Determine if the environment variable matches a pattern."""

    env: str
    pattern: Pattern[str]
    validate: bool

    @property
    @lru_cache()
    def _matched(self) -> Match[str] | None:
        """Return the matched pattern."""
        # Lint false-positive: https://github.com/PyCQA/pylint/issues/5091
        # pylint: disable=invalid-envvar-value
        return self.pattern.match(os.getenv(self.env, ""))

    def match_env(self) -> bool:
        """Return True if the environment variable matches the pattern."""
        return bool(self._matched)

    def get_version(self) -> str | None:
        """Return the first group of the pattern if validate is True."""
        if self.validate:
            if self._matched:
                return self._matched.groups()[0]
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Matcher:
        """Load an object from a dict."""
        data_copy = dict(data)
        pattern = re.compile(data_copy.pop("pattern"))
        validate = bool(data_copy.pop("validate", False))
        return cls(**data_copy, pattern=pattern, validate=validate)


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter


def is_canonical(version: Version):
    """
    Return True if the version is canonical pep440.

    See
    https://peps.python.org/pep-0440/#appendix-b-parsing-version-strings-with-regular-expressions
    """
    return (
        re.match(
            r"^([1-9][0-9]*!)?(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*((a|b|rc)(0|[1-9][0-9]*))?"
            + r"(\.post(0|[1-9][0-9]*))?(\.dev(0|[1-9][0-9]*))?$",
            version.public,
        )
        is not None
    )
