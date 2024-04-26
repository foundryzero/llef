"""llefsettings command class."""
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
        parser = argparse.ArgumentParser(description="LLEF settings command")
        subparsers = parser.add_subparsers()

        list_parser = subparsers.add_parser("list", help="list all settings")
        list_parser.set_defaults(action="list")

        save_parser = subparsers.add_parser("save", help="Save settings to config file")
        save_parser.set_defaults(action="save")

        reload_parser = subparsers.add_parser("reload", help="Reload settings from config file (retain session values)")
        reload_parser.set_defaults(action="reload")

        reset_parser = subparsers.add_parser("reset", help="Reload settings from config file (purge session values)")
        reset_parser.set_defaults(action="reset")

        set_parser = subparsers.add_parser("set", help="Set LLEF settings")
        set_parser.add_argument("setting", type=str, help="LLEF setting name")
        set_parser.add_argument("value", type=str, help="New setting value")
        set_parser.set_defaults(action="set")

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

        if not hasattr(args, "action"):
            print(SettingsCommand.get_long_help())
            return

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
