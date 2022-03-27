# pylint: disable=all
# flake8: noqa
class ExpandvarsException(Exception):
    """The base exception for all the handleable exceptions."""

    ...

class UnboundVariable(ExpandvarsException, KeyError):
    def __init__(self, param: str) -> None: ...

def expandvars(vars_: str, nounset: bool = ...) -> str: ...
