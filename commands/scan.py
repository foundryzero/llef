"""Scan command class."""

import argparse
import shlex
from typing import Any, Union

from lldb import (
    SBCommandReturnObject,
    SBDebugger,
    SBError,
    SBExecutionContext,
    SBMemoryRegionInfo,
    SBProcess,
    SBTarget,
    SBValue,
)

from commands.base_command import BaseCommand
from common.constants import MSG_TYPE
from common.context_handler import ContextHandler
from common.output_util import print_message
from common.state import LLEFState
from common.util import check_process


class ScanCommand(BaseCommand):
    """Implements the scan command"""

    program: str = "scan"
    container = None
    context_handler: Union[ContextHandler, None] = None

    def __init__(self, debugger: SBDebugger, __: dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.state = LLEFState()

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "search_region",
            type=str,
            help="Memory region to search through.",
        )
        parser.add_argument(
            "target_region",
            type=str,
            help="Memory address range to search for.",
        )
        return parser

    @staticmethod
    def get_short_help() -> str:
        """Return a short help message"""
        return "Usage: scan [search_region] [target_region]"

    @staticmethod
    def get_long_help() -> str:
        """Return a longer help message"""
        return ScanCommand.get_command_parser().format_help()

    def parse_address_ranges(self, process: SBProcess, region_name: str) -> list[tuple[int, int]]:
        """
        Parse a custom address range (e.g., 0x7fffffffe208-0x7fffffffe240)
        or extract address ranges from memory regions with a given name (e.g., libc).

        :param process: Running process of target executable.
        :param region_name: A name that can be found in the pathname of memory regions or a custom address range.
        :return: A list of address ranges.
        """
        address_ranges = []

        if "-" in region_name:
            region_start_end = region_name.split("-")
            if len(region_start_end) == 2:
                try:
                    region_start = int(region_start_end[0], 16)
                    region_end = int(region_start_end[1], 16)
                    address_ranges.append((region_start, region_end))
                except ValueError:
                    print_message(MSG_TYPE.ERROR, "Invalid address range.")
        else:
            address_ranges = self.find_address_ranges(process, region_name)

        return address_ranges

    def find_address_ranges(self, process: SBProcess, region_name: str) -> list[tuple[int, int]]:
        """
        Extract address ranges from memory regions with @region_name.

        :param process: Running process of target executable.
        :param region_name: A name that can be found in the pathname of memory regions.
        :return: A list of address ranges.
        """

        address_ranges = []

        memory_regions = process.GetMemoryRegions()
        memory_region_count = memory_regions.GetSize()
        for i in range(memory_region_count):
            memory_region = SBMemoryRegionInfo()
            if (
                memory_regions.GetMemoryRegionAtIndex(i, memory_region)
                and memory_region.IsMapped()
                and memory_region.GetName() is not None
                and region_name in memory_region.GetName()
            ):
                region_start = memory_region.GetRegionBase()
                region_end = memory_region.GetRegionEnd()
                address_ranges.append((region_start, region_end))

        return address_ranges

    def scan(
        self,
        search_address_ranges: list[tuple[int, int]],
        target_address_ranges: list[tuple[int, int]],
        address_size: int,
        process: SBProcess,
        target: SBTarget,
    ) -> list[tuple[SBValue, int]]:
        """
        Scan through a given search space in memory for addresses that point towards a target memory space.

        :param search_address_ranges: A list of start and end addresses of memory regions to search.
        :param target_address_ranges: A list of start and end addresses defining the range of addresses to search for.
        :param address_size: The expected address size for the architecture.
        :param process: The running process of the target.
        :param target: The target executable.
        :return: A list of addresses (with their offsets) in the search space that point towards the target address
        space.
        """
        results = []
        error = SBError()
        for search_start, search_end in search_address_ranges:
            for search_address in range(search_start, search_end, address_size):
                target_address = process.ReadUnsignedFromMemory(search_address, address_size, error)
                if error.Success():
                    for target_start, target_end in target_address_ranges:
                        if target_address >= target_start and target_address < target_end:
                            offset = search_address - search_start
                            search_address_value = target.EvaluateExpression(f"{search_address}")
                            results.append((search_address_value, offset))
                else:
                    print_message(MSG_TYPE.ERROR, f"Memory at {search_address} couldn't be read.")
        return results

    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of the scan command"""

        args = self.parser.parse_args(shlex.split(command))
        search_region = args.search_region
        target_region = args.target_region

        if self.context_handler is None:
            raise AttributeError("Class not properly initialised: self.context_handler is None")

        self.context_handler.refresh(exe_ctx)

        search_address_ranges = self.parse_address_ranges(exe_ctx.process, search_region)
        target_address_ranges = self.parse_address_ranges(exe_ctx.process, target_region)

        if self.state.platform == "Darwin" and (search_address_ranges == [] or target_address_ranges == []):
            print_message(
                MSG_TYPE.ERROR,
                "Memory region names cannot be resolved on macOS. Use memory address ranges instead.",
            )
            return

        print_message(MSG_TYPE.INFO, f"Searching for addresses in '{search_region}' that point to '{target_region}'")

        address_size = exe_ctx.target.GetAddressByteSize()

        results = self.scan(search_address_ranges, target_address_ranges, address_size, exe_ctx.process, exe_ctx.target)
        for address, offset in results:
            self.context_handler.print_stack_addr(address.GetValueAsUnsigned(), offset)
