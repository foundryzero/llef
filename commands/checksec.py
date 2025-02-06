"""Checksec command class."""

import argparse
from typing import Any, Dict

from lldb import SBCommandReturnObject, SBDebugger, SBError, SBExecutionContext, SBTarget

from arch import get_arch
from commands.base_command import BaseCommand
from common.constants import (
    ARCH_BITS,
    DYNAMIC_ENTRY_TYPE,
    DYNAMIC_ENTRY_VALUE,
    EXECUTABLE_TYPE,
    MSG_TYPE,
    PERMISSION_SET,
    PROGRAM_HEADER_TYPE,
    SECURITY_CHECK,
    SECURITY_FEATURE,
    TERM_COLORS,
)
from common.context_handler import ContextHandler
from common.output_util import color_string, output_line, print_message
from common.util import check_elf, check_target, read_program_int

PROGRAM_HEADER_OFFSET_32BIT_OFFSET = 0x1C
PROGRAM_HEADER_SIZE_32BIT_OFFSET = 0x2A
PROGRAM_HEADER_COUNT_32BIT_OFFSET = 0x2C
PROGRAM_HEADER_PERMISSION_OFFSET_32BIT_OFFSET = 0x18

PROGRAM_HEADER_OFFSET_64BIT_OFFSET = 0x20
PROGRAM_HEADER_SIZE_64BIT_OFFSET = 0x36
PROGRAM_HEADER_COUNT_64BIT_OFFSET = 0x38
PROGRAM_HEADER_PERMISSION_OFFSET_64BIT_OFFSET = 0x04


class ChecksecCommand(BaseCommand):
    """Implements the checksec command"""

    program: str = "checksec"
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
        return parser

    @staticmethod
    def get_short_help() -> str:
        """Return a short help message"""
        return "Usage: checksec"

    @staticmethod
    def get_long_help() -> str:
        """Return a longer help message"""
        return ChecksecCommand.get_command_parser().format_help()

    def get_executable_type(self, target: SBTarget):
        """
        Get executable type for a given @target ELF file.

        :param target: The target object file.
        :return: An integer representing the executable type.
        """
        return read_program_int(target, 0x10, 2)

    def get_program_header_permission(self, target: SBTarget, target_header_type: int):
        """
        Get value of the permission field from a program header entry.

        :param target: The target object file.
        :param target_header_type: The type of the program header entry.
        :return: An integer between 0 and 7 representing the permission. Returns 'None' if program header is not found.
        """
        arch = get_arch(target).bits

        if arch == ARCH_BITS.BITS_32:
            program_header_offset = read_program_int(target, PROGRAM_HEADER_OFFSET_32BIT_OFFSET, 4)
            program_header_entry_size = read_program_int(target, PROGRAM_HEADER_SIZE_32BIT_OFFSET, 2)
            program_header_count = read_program_int(target, PROGRAM_HEADER_COUNT_32BIT_OFFSET, 2)
            program_header_permission_offset = PROGRAM_HEADER_PERMISSION_OFFSET_32BIT_OFFSET
        else:
            program_header_offset = read_program_int(target, PROGRAM_HEADER_OFFSET_64BIT_OFFSET, 8)
            program_header_entry_size = read_program_int(target, PROGRAM_HEADER_SIZE_64BIT_OFFSET, 2)
            program_header_count = read_program_int(target, PROGRAM_HEADER_COUNT_64BIT_OFFSET, 2)
            program_header_permission_offset = PROGRAM_HEADER_PERMISSION_OFFSET_64BIT_OFFSET

        permission = None
        for i in range(program_header_count):
            program_header_type = read_program_int(target, program_header_offset + program_header_entry_size * i, 4)
            if program_header_type == target_header_type:
                permission = read_program_int(
                    target, program_header_offset + program_header_entry_size * i + program_header_permission_offset, 4
                )
                break

        return permission

    def get_dynamic_entry(self, target: SBTarget, target_entry_type: int):
        """
        Get value for a given entry type in the .dynamic section table.

        :param target: The target object file.
        :param target_entry_type: The type of the entry in the .dynamic table.
        :return: Value of the entry. Returns 'None' if entry type not found.
        """
        target_entry_value = None
        # Executable has always been observed at module 0, but isn't specifically stated in docs.
        module = target.GetModuleAtIndex(0)
        section = module.FindSection(".dynamic")
        entry_count = int(section.GetByteSize() / 16)
        for i in range(entry_count):
            entry_type = section.GetSectionData(i * 16, 8).GetUnsignedInt64(SBError(), 0)
            entry_value = section.GetSectionData(i * 16 + 8, 8).GetUnsignedInt64(SBError(), 0)

            if target_entry_type == entry_type:
                target_entry_value = entry_value
                break

        return target_entry_value

    def check_security(self, target: SBTarget) -> Dict[str, SECURITY_CHECK]:
        """
        Checks the following security features on the target executable:
         - Stack Canary
         - NX Support
         - PIE Support
         - RPath
         - RunPath
         - Full/Partial RelRO

        :param target: The target executable.
        :return: A dictionary showing whether each security feature is enabled or disabled.
        """
        checks = {
            SECURITY_FEATURE.STACK_CANARY: SECURITY_CHECK.NO,
            SECURITY_FEATURE.NX_SUPPORT: SECURITY_CHECK.UNKNOWN,
            SECURITY_FEATURE.PIE_SUPPORT: SECURITY_CHECK.UNKNOWN,
            SECURITY_FEATURE.NO_RPATH: SECURITY_CHECK.UNKNOWN,
            SECURITY_FEATURE.NO_RUNPATH: SECURITY_CHECK.UNKNOWN,
            SECURITY_FEATURE.PARTIAL_RELRO: SECURITY_CHECK.UNKNOWN,
            SECURITY_FEATURE.FULL_RELRO: SECURITY_CHECK.UNKNOWN,
        }

        # Check for Stack Canary
        for symbol in target.GetModuleAtIndex(0):
            if symbol.GetName() in ["__stack_chk_fail", "__stack_chk_guard", "__intel_security_cookie"]:
                checks[SECURITY_FEATURE.STACK_CANARY] = SECURITY_CHECK.YES
                break

        # Check for NX Support
        try:
            if self.get_program_header_permission(target, PROGRAM_HEADER_TYPE.GNU_STACK) in PERMISSION_SET.NOT_EXEC:
                checks[SECURITY_FEATURE.NX_SUPPORT] = SECURITY_CHECK.YES
            else:
                checks[SECURITY_FEATURE.NX_SUPPORT] = SECURITY_CHECK.NO
        except MemoryError as error:
            print_message(MSG_TYPE.ERROR, error)
            checks[SECURITY_FEATURE.NX_SUPPORT] = SECURITY_CHECK.UNKNOWN

        # Check for PIE Support
        try:
            if self.get_executable_type(target) == EXECUTABLE_TYPE.DYN:
                checks[SECURITY_FEATURE.PIE_SUPPORT] = SECURITY_CHECK.YES
            else:
                checks[SECURITY_FEATURE.PIE_SUPPORT] = SECURITY_CHECK.NO
        except MemoryError as error:
            print_message(MSG_TYPE.ERROR, error)
            checks[SECURITY_FEATURE.PIE_SUPPORT] = SECURITY_CHECK.UNKNOWN

        # Check for Partial RelRO
        try:
            if self.get_program_header_permission(target, PROGRAM_HEADER_TYPE.GNU_RELRO) is not None:
                checks[SECURITY_FEATURE.PARTIAL_RELRO] = SECURITY_CHECK.YES
            else:
                checks[SECURITY_FEATURE.PARTIAL_RELRO] = SECURITY_CHECK.NO
        except MemoryError as error:
            print_message(MSG_TYPE.ERROR, error)
            checks[SECURITY_FEATURE.PARTIAL_RELRO] = SECURITY_CHECK.UNKNOWN

        # Check for Full RelRO
        if checks[SECURITY_FEATURE.PARTIAL_RELRO] == SECURITY_CHECK.UNKNOWN:
            checks[SECURITY_FEATURE.FULL_RELRO] = SECURITY_CHECK.UNKNOWN
        elif (
            self.get_dynamic_entry(target, DYNAMIC_ENTRY_TYPE.FLAGS) == DYNAMIC_ENTRY_VALUE.BIND_NOW
            and checks[SECURITY_FEATURE.PARTIAL_RELRO] == SECURITY_CHECK.YES
        ):
            checks[SECURITY_FEATURE.FULL_RELRO] = SECURITY_CHECK.YES
        else:
            checks[SECURITY_FEATURE.FULL_RELRO] = SECURITY_CHECK.NO

        # Check for No RPath
        if self.get_dynamic_entry(target, DYNAMIC_ENTRY_TYPE.RPATH) is None:
            checks[SECURITY_FEATURE.NO_RPATH] = SECURITY_CHECK.YES
        else:
            checks[SECURITY_FEATURE.NO_RPATH] = SECURITY_CHECK.NO

        # Check for No RunPath
        if self.get_dynamic_entry(target, DYNAMIC_ENTRY_TYPE.RUNPATH) is None:
            checks[SECURITY_FEATURE.NO_RUNPATH] = SECURITY_CHECK.YES
        else:
            checks[SECURITY_FEATURE.NO_RUNPATH] = SECURITY_CHECK.NO

        return checks

    @check_target
    @check_elf
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of the checksec command"""

        self.context_handler.refresh(exe_ctx)

        target = exe_ctx.GetTarget()
        checks = self.check_security(target)

        for check, status in checks.items():
            if status == SECURITY_CHECK.YES:
                color = TERM_COLORS.GREEN.name
            elif status == SECURITY_CHECK.NO:
                color = TERM_COLORS.RED.name
            else:
                color = TERM_COLORS.GREY.name
            check_value_string = check.value + ": "
            line = color_string(status.value, color, lwrap=f"{check_value_string:<20}")
            output_line(line)
