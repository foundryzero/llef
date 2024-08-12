"""llefsettings command class."""
import argparse
from typing import Any, Dict

from lldb import SBDebugger

from common.settings import LLEFSettings
from commands.base_settings import BaseSettingsCommand


class SettingsCommand(BaseSettingsCommand):
    """Implements the llefsettings command"""

    program: str = "llefsettings"
    container = None

    def __init__(self, debugger: SBDebugger, dictionary: Dict[Any, Any]) -> None:
        super().__init__(debugger, dictionary)
        self.settings = LLEFSettings(debugger)

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
