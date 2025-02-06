"""Xinfo command class."""

import argparse
import os
import shlex
from typing import Any, Dict

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext, SBMemoryRegionInfo

from commands.base_command import BaseCommand
from common.constants import MSG_TYPE
from common.context_handler import ContextHandler
from common.util import check_process, hex_int, print_message


class XinfoCommand(BaseCommand):
    """Implements the xinfo command"""

    program: str = "xinfo"
    container = None
    context_handler = None

    def __init__(self, debugger: SBDebugger, __: Dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "address",
            type=hex_int,
            help="A value/address/symbol used as the location to print the xinfo from",
        )
        return parser

    @staticmethod
    def get_short_help() -> str:
        """Return a short help message"""
        return "Usage: xinfo [address]"

    @staticmethod
    def get_long_help() -> str:
        """Return a longer help message"""
        return XinfoCommand.get_command_parser().format_help()

    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of the xinfo command"""

        args = self.parser.parse_args(shlex.split(command))
        address = args.address

        memory_region = SBMemoryRegionInfo()
        error = exe_ctx.process.GetMemoryRegionInfo(address, memory_region)

        if error.Fail():
            print_message(MSG_TYPE.ERROR, "Couldn't obtain region info")

        if not memory_region.IsMapped():
            print_message(MSG_TYPE.ERROR, f"Not Found: {hex(address)}")
            return

        print_message(MSG_TYPE.SUCCESS, f"Found: {hex(address)}")

        start = memory_region.GetRegionBase()
        end = memory_region.GetRegionEnd()
        size = end - start
        print_message(
            MSG_TYPE.INFO,
            f"Page/Region: {hex(start)}->{hex(end)} (size={hex(size)})",
        )

        permissions = ""
        permissions += "r" if memory_region.IsReadable() else ""
        permissions += "w" if memory_region.IsWritable() else ""
        permissions += "x" if memory_region.IsExecutable() else ""
        print_message(MSG_TYPE.INFO, f"Permissions: {permissions}")

        path = memory_region.GetName()
        print_message(MSG_TYPE.INFO, f"Pathname: {path}")

        print_message(MSG_TYPE.INFO, f"Offset (from page/region): +{hex(address - memory_region.GetRegionBase())}")

        if os.path.exists(path):
            print_message(MSG_TYPE.INFO, f"Inode: {os.stat(path).st_ino}")
        else:
            print_message(MSG_TYPE.ERROR, "No inode found: Path cannot be found locally.")
