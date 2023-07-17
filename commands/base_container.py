"""Base container definition."""
from abc import ABC, abstractmethod

from lldb import SBDebugger


class BaseContainer(ABC):
    """Base container class."""

    @property
    @abstractmethod
    def container_verb(self) -> str:
        """Container verb property."""

    @staticmethod
    @abstractmethod
    def get_short_help() -> str:
        """Get short help message."""

    @staticmethod
    @abstractmethod
    def get_long_help() -> str:
        """Get long help message."""

    @classmethod
    def lldb_self_register(cls, debugger: SBDebugger, _: str) -> None:
        """Automatically register a container."""
        container_command = f'command container add -h "{cls.get_long_help()}" -H "{cls.get_short_help()}" {cls.container_verb}'
        debugger.HandleCommand(container_command)
