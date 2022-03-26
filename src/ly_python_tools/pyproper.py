import functools
import os
import subprocess  # nosec: B404
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Sequence

import click


@contextmanager
def environ(**env: str):
    """Temporarily set environment variables inside the context manager."""
    original_env = {key: os.getenv(key) for key in env}
    os.environ.update(env)
    try:
        yield
    finally:
        for key, value in original_env.items():
            if value is None:
                del os.environ[key]
            else:
                os.environ[key] = value


def pyright_env(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a function to set the pyright environment."""

    @functools.wraps(func)
    def wrap_pyright_env(*args: Any, **kwargs: Any):
        default_env_dir = (
            Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "pyright"
        )
        env_dir = Path(os.getenv("PYRIGHT_PYTHON_ENV_DIR", default_env_dir)).resolve()
        with environ(PYRIGHT_PYTHON_ENV_DIR=env_dir.as_posix(), PYRIGHT_PYTHON_GLOBAL_NODE="off"):
            return func(*args, **kwargs)

    return wrap_pyright_env


@click.command()
@click.option("--bootstrap", is_flag=True, default=False, help="Download pyright")
@click.option(
    "--pyright-help", is_flag=True, default=False, help="Show the help message for pyright"
)
@click.argument("pyright_args", nargs=-1, type=click.UNPROCESSED)
@pyright_env
def main(bootstrap: bool, pyright_help: bool, pyright_args: Sequence[str]):
    """A simple wrapper around pyright that enables downloading separately from running."""
    if bootstrap:
        subprocess.check_call(["pyright", "--version"])  # nosec: B603, B607
    elif pyright_help:
        subprocess.check_call(["pyright", "--help"])  # nosec: B603, B607
    else:
        subprocess.check_call(["pyright"] + list(pyright_args))  # nosec: B603, B607


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
