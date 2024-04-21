"""Context command class."""
import argparse
import shlex

from typing import Any, Dict
from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_command import BaseCommand
from common.settings import LLEFSettings


class SettingsCommand(BaseCommand):
    """Implements the llefsettings command"""

    program: str = "llefsettings"
    container = None

    def __init__(self, debugger: SBDebugger, __: Dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()
        self.settings = LLEFSettings()
    
    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser(description="Set LLEF settings")
        parser.add_argument("setting", type=str, help="LLEF setting name")
        parser.add_argument("value", type=str, help="New setting value")
        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: llefsettings <setting> <value>\n"

    @staticmethod
    def get_long_help() -> str:
        return SettingsCommand.get_command_parser().format_help()

    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'llefsettings' command"""
        args = self.parser.parse_args(shlex.split(command))
        self.settings.set(args.setting, args.value)
