"""Configure the package version using the CI environment."""
from __future__ import annotations

import os
import re
import shutil
import tokenize
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from subprocess import check_output  # nosec: B404
from tempfile import TemporaryDirectory
from typing import Any
from typing import Mapping
from typing import Pattern
from typing import Sequence

import click
import pep440
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
def main(repo: bool):
    r"""
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
        if self.handler.tag_validate and version and version != self.full_version:
            raise ValueError(
                f"pyproject version {self.full_version} "
                f"does not match environment version {version}"
            )
        if self.handler.branch_validate and version and version != self.full_version:
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
        return base_version + expandvars(self.handler.extra)

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
        check_output(["poetry", "version", self.full_version])  # nosec

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
                        if token.type == tokenize.NL:
                            out.write(token.line)
                        if token.type == tokenize.NEWLINE:
                            out.write(matcher.sub(version_string, token.line))
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
class VersionHandler:  # pylint: disable=too-many-instance-attributes
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

    tag_env: str | None = None
    tag_match: Pattern[str] | None = None
    tag_validate: bool = False
    branch_env: str | None = None
    branch_match: Pattern[str] | None = None
    branch_validate: bool = False
    repo: str | None = None
    extra: str = ""

    def __post_init__(self):
        if bool(self.tag_env) != bool(self.tag_match):
            raise ValueError('"tag_env" and "tag_match" must both be specified')
        if bool(self.branch_env) != bool(self.branch_match):
            raise ValueError('"branch_env" and "branch_match" must both be specified')
        if self.branch_validate and self.tag_validate:
            raise ValueError("It doesn't make any sense to validate both tags and branches")

    def match_env(self) -> bool:
        """Return True if this handler should be triggered."""
        ret = [True]
        if self.tag_env and self.tag_match:
            ret.append(bool(self.tag_match.match(os.getenv(self.tag_env) or "")))
        if self.branch_env and self.branch_match:
            ret.append(bool(self.branch_match.match(os.getenv(self.branch_env) or "")))
        return all(ret)

    def get_version(self) -> str | None:
        """Return the group match from the matcher."""
        if self.tag_env and self.tag_match and self.tag_validate:
            match = self.tag_match.match(os.getenv(self.tag_env) or "")
            if match:
                return match.groups()[0]
        if self.branch_env and self.branch_match and self.branch_validate:
            match = self.branch_match.match(os.getenv(self.branch_env) or "")
            if match:
                return match.groups()[0]
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> VersionHandler:
        """Load an object from a dict."""
        data_copy = dict(data)
        tag_match = data_copy.pop("tag_match", None)
        tag_validate = bool(data_copy.pop("tag_validate", False))
        branch_match = data_copy.pop("branch_match", None)
        branch_validate = bool(data_copy.pop("branch_validate", False))
        return cls(
            **data_copy,
            tag_validate=tag_validate,
            tag_match=re.compile(tag_match) if tag_match else None,
            branch_validate=branch_validate,
            branch_match=re.compile(branch_match) if branch_match else None,
        )


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
