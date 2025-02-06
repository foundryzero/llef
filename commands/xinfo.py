"""Xinfo command class."""

import argparse
import os
import shlex
from typing import Any, Dict

from lldb import (
    SBCommandReturnObject,
    SBDebugger,
    SBExecutionContext,
    SBMemoryRegionInfo,
    SBProcess,
    SBStream,
    SBTarget,
)

from arch import get_arch
from commands.base_command import BaseCommand
from common.constants import MSG_TYPE, XINFO
from common.context_handler import ContextHandler
from common.output_util import print_message
from common.state import LLEFState
from common.util import check_process, hex_int


class XinfoCommand(BaseCommand):
    """Implements the xinfo command"""

    program: str = "xinfo"
    container = None
    context_handler = None

    def __init__(self, debugger: SBDebugger, __: Dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.state = LLEFState()

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

    def get_xinfo(self, process: SBProcess, target: SBTarget, address: int) -> Dict[str, Any]:
        """
        Gets memory region information for a given `address`, including:
        - `region_start` address
        - `region_end` address
        - `region_size`
        - `region_offset` (offset of address from start of region)
        - file `path` corrosponding to the address
        - `inode` of corrosponding file

        :param state: The LLEF state containing platform variable.
        :param process: The running process of the target to extract memory regions.
        :param target: The target executable.
        :param address: The address get information about.
        :return: A dictionary containing the information about the address.
        The function will return `None` if the address isn't mapped.
        """
        memory_region = SBMemoryRegionInfo()
        error = process.GetMemoryRegionInfo(address, memory_region)

        if error.Fail() or not memory_region.IsMapped():
            return None

        xinfo = {
            XINFO.REGION_START: None,
            XINFO.REGION_END: None,
            XINFO.REGION_SIZE: None,
            XINFO.REGION_OFFSET: None,
            XINFO.PERMISSIONS: None,
            XINFO.PATH: None,
            XINFO.INODE: None,
        }

        xinfo[XINFO.REGION_START] = memory_region.GetRegionBase()
        xinfo[XINFO.REGION_END] = memory_region.GetRegionEnd()
        xinfo[XINFO.REGION_SIZE] = xinfo[XINFO.REGION_END] - xinfo[XINFO.REGION_START]
        xinfo[XINFO.REGION_OFFSET] = address - xinfo[XINFO.REGION_START]

        permissions = ""
        permissions += "r" if memory_region.IsReadable() else ""
        permissions += "w" if memory_region.IsWritable() else ""
        permissions += "x" if memory_region.IsExecutable() else ""
        xinfo[XINFO.PERMISSIONS] = permissions

        if self.state.platform == "Darwin":
            sb_address = target.ResolveLoadAddress(address)
            module = sb_address.GetModule()
            filespec = module.GetFileSpec()
            description = SBStream()
            filespec.GetDescription(description)
            xinfo[XINFO.PATH] = description.GetData()
        else:
            xinfo[XINFO.PATH] = memory_region.GetName()

        if xinfo[XINFO.PATH] is not None and os.path.exists(xinfo[XINFO.PATH]):
            xinfo[XINFO.INODE] = os.stat(xinfo[XINFO.PATH]).st_ino

        return xinfo

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

        if address < 0 or address > 2 ** get_arch(exe_ctx.target).bits:
            print_message(MSG_TYPE.ERROR, "Invalid address.")
            return

        xinfo = self.get_xinfo(exe_ctx.process, exe_ctx.target, address)

        if xinfo is not None:
            print_message(MSG_TYPE.SUCCESS, f"Found: {hex(address)}")
            print_message(
                MSG_TYPE.INFO,
                (
                    f"Page/Region: {hex(xinfo[XINFO.REGION_START])}->{hex(xinfo[XINFO.REGION_END])}"
                    f" (size={hex(xinfo[XINFO.REGION_SIZE])})"
                ),
            )
            print_message(MSG_TYPE.INFO, f"Permissions: {xinfo[XINFO.PERMISSIONS]}")
            print_message(MSG_TYPE.INFO, f"Pathname: {xinfo[XINFO.PATH]}")
            print_message(MSG_TYPE.INFO, f"Offset (from page/region): +{hex(xinfo[XINFO.REGION_OFFSET])}")

            if xinfo["inode"] is not None:
                print_message(MSG_TYPE.INFO, f"Inode: {xinfo[XINFO.INODE]}")
            else:
                print_message(MSG_TYPE.ERROR, "No inode found: Path cannot be found locally.")
        else:
            print_message(MSG_TYPE.ERROR, f"Not Found: {hex(address)}")
