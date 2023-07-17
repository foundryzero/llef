"""Base command definition."""

from abc import ABC, abstractmethod
from typing import Type

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_container import BaseContainer


class BaseCommand(ABC):
    """An abstract base class for all commands."""

    @abstractmethod
    def __init__(self) -> None:
        pass

    @property
    @abstractmethod
    def container(self) -> Type[BaseContainer]:
        """Container property."""

    @property
    @abstractmethod
    def program(self) -> str:
        """Program property."""

    @abstractmethod
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        pass

    @staticmethod
    @abstractmethod
    def get_short_help() -> str:
        """Get short help string."""

    @staticmethod
    @abstractmethod
    def get_long_help() -> str:
        """Get long help string."""

    @classmethod
    def lldb_self_register(cls, debugger: SBDebugger, module_name: str) -> None:
        """Automatically register a subcommand."""

        if cls.container is not None:
            command = f"command script add -c {module_name}.{cls.__name__} {cls.container.container_verb} {cls.program}"
        else:
            command = (
                f"command script add -c {module_name}.{cls.__name__} {cls.program}"
            )

        debugger.HandleCommand(command)
