"""llefcolorsettings command class."""

import argparse
from typing import Any, Dict

from lldb import SBDebugger

from commands.base_settings import BaseSettingsCommand
from common.color_settings import LLEFColorSettings


class ColorSettingsCommand(BaseSettingsCommand):
    """Implements the llefcolorsettings commands"""

    program: str = "llefcolorsettings"
    container = None

    def __init__(self, debugger: SBDebugger, dictionary: Dict[Any, Any]) -> None:
        super().__init__(debugger, dictionary)
        self.settings = LLEFColorSettings()

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser(description="LLEF settings command for colors")
        subparsers = parser.add_subparsers()

        list_parser = subparsers.add_parser("list", help="list all color settings")
        list_parser.set_defaults(action="list")

        save_parser = subparsers.add_parser("save", help="Save settings to config file")
        save_parser.set_defaults(action="save")

        reload_parser = subparsers.add_parser("reload", help="Reload settings from config file (retain session values)")
        reload_parser.set_defaults(action="reload")

        reset_parser = subparsers.add_parser("reset", help="Reload settings from config file (purge session values)")
        reset_parser.set_defaults(action="reset")

        set_parser = subparsers.add_parser("set", help="Set LLEF color settings")
        set_parser.add_argument("setting", type=str, help="LLEF color setting name")
        set_parser.add_argument("value", type=str, help="New color")
        set_parser.set_defaults(action="set")

        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: llefcolorsettings <setting> <value>\n"
