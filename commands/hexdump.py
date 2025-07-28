"""Hexdump command class."""

import argparse
import shlex
from typing import Any, Dict

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_command import BaseCommand
from common.constants import SIZES
from common.context_handler import ContextHandler
from common.util import check_process, check_version, hex_int, positive_int


class HexdumpCommand(BaseCommand):
    """Implements the hexdump command"""

    program: str = "hexdump"
    container = None
    context_handler: ContextHandler | None = None

    # Define alias set, where each entry is an alias with any arguments the command should take.
    # For example, 'dq' maps to 'hexdump qword'.
    alias_set = {"dq": "qword", "dd": "dword", "dw": "word", "db": "byte"}

    def __init__(self, debugger: SBDebugger, __: Dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "type",
            choices=["qword", "dword", "word", "byte"],
            default="byte",
            help="The format for presenting data",
        )
        parser.add_argument(
            "--reverse",
            action="store_true",
            help="The direction of output lines. Low to high by default",
        )
        parser.add_argument(
            "--size",
            type=positive_int,
            default=16,
            help="The number of qword/dword/word/bytes to display",
        )
        parser.add_argument(
            "address",
            type=hex_int,
            help="A value/address/symbol used as the location to print the hexdump from",
        )
        return parser

    @staticmethod
    def get_short_help() -> str:
        """Return a short help message"""
        return "Usage: hexdump (qword|dword|word|byte) [-h] [--reverse] [--size SIZE] [address]"

    @staticmethod
    def get_long_help() -> str:
        """Return a longer help message"""
        return HexdumpCommand.get_command_parser().format_help()

    @check_version("15.0.0")
    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of the hexdump command"""

        args = self.parser.parse_args(shlex.split(command))

        divisions = SIZES[args.type.upper()].value
        address = args.address
        size = args.size

        if self.context_handler is None:
            raise AttributeError("Class not properly initialised: self.context_handler is None")

        self.context_handler.refresh(exe_ctx)

        start = (size - 1) * divisions if args.reverse else 0
        end = -divisions if args.reverse else size * divisions
        step = -divisions if args.reverse else divisions

        if divisions == SIZES.BYTE.value:
            if args.reverse:
                self.context_handler.print_bytes(address + size - (size % 16), size % 16)
                start = size - (size % 16) - 16
                end = -1
                step = -16

            for i in range(start, end, -16 if args.reverse else 16):
                self.context_handler.print_bytes(address + i, min(16, size - abs(start - i)))
        else:
            for i in range(start, end, step):
                self.context_handler.print_memory_address(address + i, i, divisions)
