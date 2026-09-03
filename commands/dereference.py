"""Dereference command class."""

import argparse
import shlex
from typing import Any, Union

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

from arch import I386, X86_64
from commands.base_command import BaseCommand
from common.color_settings import LLEFColorSettings
from common.constants import GLYPHS, MSG_TYPE, TERM_COLORS
from common.context_handler import ContextHandler
from common.output_util import color_string, output_line, print_message
from common.settings import LLEFSettings
from common.state import LLEFState
from common.util import (
    attempt_to_read_string_from_memory,
    check_process,
    hex_int,
    hex_or_str,
    is_code_section,
    positive_int,
)


class DereferenceCommand(BaseCommand):
    """Implements the dereference command"""

    program: str = "dereference"
    container = None
    context_handler: Union[ContextHandler, None] = None
    alias_set = {"telescope": ""}
    last_address: Union[int, None] = None
    last_base: Union[int, None] = None
    last_lines: int = 10
    last_command: str = ""
    # Identifies the process and the stop it was continued from, so that resuming or restarting
    # the process invalidates the stored position.
    last_stop_state: Union[tuple[int, int], None] = None

    def __init__(self, debugger: SBDebugger, __: dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.color_settings = LLEFColorSettings()
        self.settings = LLEFSettings(debugger)
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
            nargs="?",
            default=None,
            help="A value/address/symbol to print the dereference from. Accepts a hex/decimal literal, a"
            " register/convenience variable (e.g. $rsp), a variable name, or an expression (e.g. nodes,"
            " &buf). If omitted, continues from last position.",
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

    @staticmethod
    def stop_state(process: SBProcess) -> tuple[int, int]:
        """
        Identify the current stop of @process. The unique ID distinguishes one process from the
        next (e.g. after `run` is issued again) and the stop ID changes every time the process
        resumes and stops again.

        :param process: The running process of the target.
        :return: A (process unique ID, stop ID) pair.
        """
        return (process.GetUniqueID(), process.GetStopID())

    @classmethod
    def invalidate_continuation(cls) -> None:
        """Forget the stored position so the next invocation cannot continue from it."""
        cls.last_address = None
        cls.last_base = None
        cls.last_lines = 10
        cls.last_command = ""
        cls.last_stop_state = None

    def resolve_address(self, value: str, exe_ctx: SBExecutionContext) -> Union[int, None]:
        """
        Resolve @value to an address. Plain hex/decimal literals are parsed directly; anything else
        (a register, convenience variable, source variable name, or arbitrary expression) is resolved
        via LLDB's expression evaluator in the context of the currently selected frame.

        :param value: The raw address argument as typed by the user.
        :param exe_ctx: The current execution context.
        :return: The resolved address, or None if @value could not be resolved.
        """
        try:
            return hex_int(value)
        except ValueError:
            pass

        address_value = exe_ctx.GetTarget().EvaluateExpression(value)
        if address_value.GetError().Fail():
            return None
        return address_value.GetValueAsUnsigned()

    def read_instruction(self, target: SBTarget, address: int) -> SBInstruction:
        """
        We disassemble an instruction at the given memory @address.

        :param target: The target object file.
        :param address: The memory address of the instruction.
        :return: An object of the disassembled instruction.
        """
        instruction_address = SBAddress(address, target)
        if self.context_handler.arch is I386 or self.context_handler.arch is X86_64:
            instruction_list = target.ReadInstructions(instruction_address, 1, self.state.disassembly_syntax)
        else:
            instruction_list = target.ReadInstructions(instruction_address, 1)
        return instruction_list.GetInstructionAtIndex(0)

    def read_symbol_name(self, target: SBTarget, address: int) -> Union[str, None]:
        """
        Resolve @address to a <symbol> or <symbol+offset> string, or None if no symbol is known.

        :param target: The target object file.
        :param address: The memory address to resolve.
        :return: A <symbol> / <symbol+offset> string, or None.
        """
        sb_address = SBAddress(address, target)
        symbol = sb_address.symbol
        if not symbol.IsValid():
            return None
        name = symbol.GetName()
        if name is None:
            return None
        offset = address - symbol.GetStartAddress().GetLoadAddress(target)
        return f"<{name}+{offset}>" if offset else f"<{name}>"

    def dereference_last_address(
        self,
        data: list[Union[int, str]],
        target: SBTarget,
        process: SBProcess,
        regions: Union[SBMemoryRegionInfoList, None],
    ) -> None:
        """
        Resolve the last address (second to last in @data list) to a symbol, instruction or
        string and render the end of the chain according to the `dereference_print` setting.

        :param data: List of memory addresses/data.
        :param target: The target object file.
        :param process: The running process of the target.
        :param regions: List of memory regions of the process.
        """
        last_address = data[-2]
        # Skip pre-rendered markers such as "[LOOPING]"; there is nothing to resolve.
        if isinstance(last_address, str) or isinstance(data[-1], str):
            return

        # Resolve to a symbol or string. Only genuine code sections are disassembled, so
        # const/data in an executable module segment is treated as a value.
        annotation = None
        if is_code_section(last_address, target):
            symbol_name = self.read_symbol_name(target, last_address)
            if symbol_name is not None:
                # Colour the symbol like a binary pointer to match its address.
                annotation = color_string(symbol_name, self.color_settings.code_color)
            else:
                instruction = self.read_instruction(target, last_address)
                if instruction.IsValid():
                    annotation = color_string(
                        f"{instruction.GetMnemonic(target)}{instruction.GetOperands(target)}",
                        self.color_settings.instruction_color,
                    )
        else:
            string = attempt_to_read_string_from_memory(process, last_address)
            if string != "":
                annotation = color_string(f'"{string}"', self.color_settings.string_color)

        if annotation is None:
            return

        mode = self.settings.dereference_print

        # With no intermediate pointer hop (data[-2] is the address column itself), show the
        # annotation alone, or leave the raw value in "pointer" mode.
        if len(data) < 3:
            if mode != "pointer":
                data[-1] = annotation
            return

        # Drop the raw bytes read through last_address and render the resolved pointer.
        data.pop()
        if mode == "symbol":
            data[-1] = annotation
        elif mode == "pointer":
            pass  # Leave the raw pointer in place; coloured by print_dereference_result.
        else:  # "both"
            pointer_color = self.context_handler.pointer_type_color(last_address)
            data[-1] = f"{color_string(hex_or_str(last_address), pointer_color)} ({annotation})"

    def dereference(
        self, address: int, target: SBTarget, process: SBProcess, regions: Union[SBMemoryRegionInfoList, None]
    ) -> list[Union[int, str]]:
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

        data: list[Union[int, str]] = []

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

    def print_dereference_result(self, result: list[Union[int, str]], offset: int) -> None:
        """Format and output the results of dereferencing an address."""
        output = color_string(hex_or_str(result[0]), TERM_COLORS.CYAN.name, rwrap=GLYPHS.VERTICAL_LINE.value)
        if offset >= 0:
            output += f"+0x{offset:04x}: "
        else:
            output += f"-0x{-offset:04x}: "

        colored_chain = []
        for item in result[1:]:
            if isinstance(item, int):
                color = self.context_handler.pointer_type_color(item)
                colored_chain.append(color_string(hex_or_str(item), color))
            else:
                colored_chain.append(item)

        output += " -> ".join(colored_chain)
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

        # A stored position is only meaningful for the process and the stop it was taken at, so
        # drop it if the process has resumed, exited, or been replaced since.
        stop_state = self.stop_state(exe_ctx.process)
        if DereferenceCommand.last_stop_state != stop_state:
            self.invalidate_continuation()

        if args.address is None:
            if DereferenceCommand.last_address is None:
                print_message(MSG_TYPE.ERROR, "No address specified and no previous command to continue from")
                return
            address_size = exe_ctx.target.GetAddressByteSize()
            start_address = DereferenceCommand.last_address + (address_size * DereferenceCommand.last_lines)
            base = DereferenceCommand.last_base
            lines = DereferenceCommand.last_lines
        else:
            if command == DereferenceCommand.last_command and DereferenceCommand.last_address is not None:
                address_size = exe_ctx.target.GetAddressByteSize()
                start_address = DereferenceCommand.last_address + (address_size * DereferenceCommand.last_lines)
                base = DereferenceCommand.last_base
                lines = DereferenceCommand.last_lines
            else:
                resolved_address = self.resolve_address(args.address, exe_ctx)
                if resolved_address is None:
                    print_message(MSG_TYPE.ERROR, f"Could not resolve address argument: {args.address}")
                    return
                start_address = resolved_address
                lines = args.lines
                if args.base:
                    base = args.base
                else:
                    base = start_address

        if self.context_handler is None:
            raise AttributeError("Class not properly initialised: self.context_handler is None")

        self.context_handler.refresh(exe_ctx)

        address_size = exe_ctx.target.GetAddressByteSize()

        allocation_map = {}
        if self.settings.dereference_show_heap_boundaries:
            from common.output_util import print_line

            allocation_map = self.context_handler.darwin_allocation_map(start_address, lines, address_size)

        end_address = start_address + address_size * lines
        previous_allocation = None
        first_line = True

        for address in range(start_address, end_address, address_size):
            if self.settings.dereference_show_heap_boundaries and allocation_map:
                current_allocation = allocation_map.get(address)
                if not first_line and current_allocation != previous_allocation:
                    print_line()
                previous_allocation = current_allocation
                first_line = False

            offset = address - base
            deref_result = self.dereference(address, exe_ctx.target, exe_ctx.process, self.context_handler.regions)
            self.print_dereference_result(deref_result, offset)

        DereferenceCommand.last_address = start_address
        DereferenceCommand.last_base = base
        DereferenceCommand.last_lines = lines
        DereferenceCommand.last_command = command
        DereferenceCommand.last_stop_state = self.stop_state(exe_ctx.process)
