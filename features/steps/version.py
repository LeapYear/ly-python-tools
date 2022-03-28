"""Version gherkin step implementation."""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from ly_python_tools.version import main
from pathlib import Path

from behave import given
from behave import then
from behave import when
from behave.runner import Context
from click.testing import CliRunner
from click.testing import Result


@contextmanager
def set_directory(path: Path):
    """Set the cwd within the context."""
    origin = Path().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)


@dataclass
class VersionExeEnvironment:
    """Temporary environment for running the version executable."""

    _path: Path
    verbose: bool = False
    project_files: dict[str, str] = field(default_factory=dict)
    environ: dict[str, str] = field(default_factory=dict)
    _runner: CliRunner = field(default_factory=CliRunner)

    def run(self, *args: str) -> Result:
        """Run the version executable in this environment."""
        if not self._path.exists():
            self._path.mkdir(parents=True)
        for rel_path, contents in self.project_files.items():
            (self._path / rel_path).parent.mkdir(parents=True, exist_ok=True)
            (self._path / rel_path).write_text(contents)
        self._runner.env = {**self.environ, **self._runner.env}
        invoke_args = list(args)
        with set_directory(self._path):
            return self._runner.invoke(main, invoke_args)  # type: ignore

    def read_file(self, filename: str | Path) -> str:
        """Read a file from the environment."""
        with (self._path / filename).open() as handle:
            return handle.read()


class VersionExeContext(Context):
    """Behave context for the version executable."""

    environment: VersionExeEnvironment
    result: Result | None


@given('the "{filename}" file')
def step_file_contents(context: VersionExeContext, filename: str):
    """Populate a file."""
    context.environment.project_files[filename] = context.text


@given("the env vars")
def step_set_env(context: VersionExeContext):
    """Set the environment using a Table."""
    for row in context.table:
        context.environment.environ[row["name"]] = row["value"]


@when('I run version with "{args}"')
def step_run_version(context: VersionExeContext, args: str):
    """Run version with arguments."""
    context.result = context.environment.run(*args.split())


@when("I run version with no arguments")
def step_run_version_no_args(context: VersionExeContext):
    """Run version without arguments."""
    context.result = context.environment.run()


@then('stdout contains "{content}"')
def step_stdout_contains(context: VersionExeContext, content: str):
    """Find text in the stdout after running version."""
    assert context.result, "No result"
    if context.result.exception:
        raise AssertionError() from context.result.exception
    assert content in context.result.stdout, context.result.stdout


@then("stdout contains text")
def step_stdout_contains_text(context: VersionExeContext):
    """Find text in the stdout after running version."""
    assert context.result, "No result"
    if context.result.exception:
        raise AssertionError() from context.result.exception
    assert context.text in context.result.stdout, context.result.stdout


@then('the file "{filename}" contains text')
def step_filename_contains_text(context: VersionExeContext, filename: str):
    """Find text in the file."""
    file_contents = context.environment.read_file(filename)
    assert context.text in file_contents, file_contents
