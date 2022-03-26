"""Linting modules."""
from .cli import main

__all__ = ["main"]


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
