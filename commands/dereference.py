"""Dereference command class."""

import argparse
import shlex
from typing import Any, Dict

from lldb import (
    SBAddress,
    SBCommandReturnObject,
    SBDebugger,
    SBError,
    SBExecutionContext,
    SBInstruction,
    SBMemoryRegionInfoList,
    SBProcess,
    SBTarget,
)

from commands.base_command import BaseCommand
from common.color_settings import LLEFColorSettings
from common.constants import GLYPHS, TERM_COLORS
from common.context_handler import ContextHandler
from common.output_util import color_string, output_line
from common.state import LLEFState
from common.util import attempt_to_read_string_from_memory, check_process, hex_int, hex_or_str, is_code, positive_int


class DereferenceCommand(BaseCommand):
    """Implements the dereference command"""

    program: str = "dereference"
    container = None
    context_handler: ContextHandler | None = None

    def __init__(self, debugger: SBDebugger, __: Dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.color_settings = LLEFColorSettings()
        self.state = LLEFState()

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

    def read_instruction(self, target: SBTarget, address: int) -> SBInstruction:
        """
        We disassemble an instruction at the given memory @address.

        :param target: The target object file.
        :param address: The memory address of the instruction.
        :return: An object of the disassembled instruction.
        """
        instruction_address = SBAddress(address, target)
        instruction_list = target.ReadInstructions(instruction_address, 1, self.state.disassembly_syntax)
        return instruction_list.GetInstructionAtIndex(0)

    def dereference_last_address(
        self, data: list[int | str], target: SBTarget, process: SBProcess, regions: SBMemoryRegionInfoList | None
    ) -> None:
        """
        Memory data at the last address (second to last in @data list) is
        either disassembled to an instruction or converted to a string or neither.

        :param data: List of memory addresses/data.
        :param target: The target object file.
        :param process: The running process of the target.
        :param regions: List of memory regions of the process.
        """
        last_address = data[-2]
        if isinstance(last_address, str):
            return

        if is_code(last_address, process, target, regions):
            instruction = self.read_instruction(target, last_address)
            if instruction.IsValid():
                data[-1] = color_string(
                    f"{instruction.GetMnemonic(target)}{instruction.GetOperands(target)}",
                    self.color_settings.instruction_color,
                )
        else:
            string = attempt_to_read_string_from_memory(process, last_address)
            if string != "":
                data[-1] = color_string(string, self.color_settings.string_color)

    def dereference(
        self, address: int, target: SBTarget, process: SBProcess, regions: SBMemoryRegionInfoList | None
    ) -> list[int | str]:
        """
        Dereference a memory @address until it reaches data that cannot be resolved to an address.
        Memory data at the last address is either disassembled to an instruction or converted to a string or neither.
        The chain of dereferencing is output.

        :param address: The address to dereference
        :param offset: The offset of address from a choosen base.
        :param target: The target object file.
        :param process: The running process of the target.
        :param regions: List of memory regions of the process.
        """

        data: list[int | str] = []

        error = SBError()
        while error.Success():
            data.append(address)
            address = process.ReadPointerFromMemory(address, error)
            if len(data) > 1 and data[-1] in data[:-2]:
                data.append(color_string("[LOOPING]", TERM_COLORS.GREY.name))
                break

        if len(data) < 2:
            data.append(color_string("NOT ACCESSIBLE", TERM_COLORS.RED.name))
        else:
            self.dereference_last_address(data, target, process, regions)

        return data

    def print_dereference_result(self, result: list[int | str], offset: int) -> None:
        """Format and output the results of dereferencing an address."""
        output = color_string(hex_or_str(result[0]), TERM_COLORS.CYAN.name, rwrap=GLYPHS.VERTICAL_LINE.value)
        if offset >= 0:
            output += f"+0x{offset:04x}: "
        else:
            output += f"-0x{-offset:04x}: "
        output += " -> ".join(map(hex_or_str, result[1:]))
        output_line(output)

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

        if self.context_handler is None:
            raise AttributeError("Class not properly initialised: self.context_handler is None")

        self.context_handler.refresh(exe_ctx)

        address_size = exe_ctx.target.GetAddressByteSize()

        end_address = start_address + address_size * lines
        for address in range(start_address, end_address, address_size):
            offset = address - base
            deref_result = self.dereference(address, exe_ctx.target, exe_ctx.process, self.context_handler.regions)
            self.print_dereference_result(deref_result, offset)
