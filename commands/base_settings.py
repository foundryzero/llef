"""Base settings command class."""

import argparse
import shlex
from abc import ABC, abstractmethod
from typing import Any, Dict

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_command import BaseCommand
from common.base_settings import BaseLLEFSettings
from common.output_util import output_line


class BaseSettingsCommand(BaseCommand, ABC):
    """Base class for generic settings command"""

    program: str = ""
    container = None
    settings: BaseLLEFSettings | None = None

    def __init__(self, debugger: SBDebugger, __: Dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()

    @classmethod
    @abstractmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""

    @staticmethod
    @abstractmethod
    def get_short_help() -> str:
        """Return a short help message"""

    @classmethod
    def get_long_help(cls) -> str:
        """Return a longer help message"""
        return cls.get_command_parser().format_help()

    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of the command"""
        args = self.parser.parse_args(shlex.split(command))

        if not hasattr(args, "action"):
            output_line(self.__class__.get_long_help())
            return

        if self.settings is None:
            raise AttributeError("Class not properly initialised: self.settings is None")

        if args.action == "list":
            self.settings.list()
        elif args.action == "save":
            self.settings.save()
        elif args.action == "reload":
            self.settings.load()
        elif args.action == "reset":
            self.settings.load(reset=True)
        elif args.action == "set":
            self.settings.set(args.setting, args.value)
