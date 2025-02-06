"""Dereference command class."""

import argparse
import shlex
from typing import Any, Dict

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_command import BaseCommand
from common.context_handler import ContextHandler
from common.dereference_util import dereference
from common.util import check_process, hex_int, positive_int


class DereferenceCommand(BaseCommand):
    """Implements the dereference command"""

    program: str = "dereference"
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
            "-l",
            "--lines",
            type=positive_int,
            default=10,
            help="The number of consecutive addresses to dereference",
        )
        parser.add_argument(
            "-b",
            "--base",
            type=positive_int,
            default=0,
            help="An address to calculate offsets from. By default this is the stack pointer ($rsp)",
        )
        parser.add_argument(
            "address",
            type=hex_int,
            help="A value/address/symbol used as the location to print the dereference from",
        )
        return parser

    @staticmethod
    def get_short_help() -> str:
        """Return a short help message"""
        return "Usage: dereference [-h] [-l LINES] [-b OFFSET-BASE] [address]"

    @staticmethod
    def get_long_help() -> str:
        """Return a longer help message"""
        return DereferenceCommand.get_command_parser().format_help()

    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of the dereference command"""

        args = self.parser.parse_args(shlex.split(command))

        start_address = args.address
        lines = args.lines
        if args.base:
            base = args.base
        else:
            base = start_address

        self.context_handler.refresh(exe_ctx)

        address_size = exe_ctx.target.GetAddressByteSize()

        end_address = start_address + address_size * lines
        for address in range(start_address, end_address, address_size):
            offset = address - base
            dereference(address, offset, exe_ctx.target, exe_ctx.process, self.context_handler.regions)
