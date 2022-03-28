"""Environment for running behave."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable

from behave import fixture
from behave import use_fixture
from behave.model import Scenario

from features.steps.version import VersionExeContext
from features.steps.version import VersionExeEnvironment


@fixture
def version_environment(context: VersionExeContext) -> Iterable[VersionExeEnvironment]:
    """Create the version environment for the steps."""
    with TemporaryDirectory() as tmp_dir:
        environment = VersionExeEnvironment(_path=Path(tmp_dir), verbose=False)
        context.environment = environment
        yield environment


def before_scenario(context: VersionExeContext, _scenario: Scenario):
    """Enable the scenario fixture."""
    use_fixture(version_environment, context)
