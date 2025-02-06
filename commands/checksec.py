"""Checksec command class."""

import argparse
from typing import Any, Dict

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_command import BaseCommand
from common.checksec_util import get_dynamic_entry, get_executable_type, get_program_header_permission
from common.constants import (
    DYNAMIC_ENTRY_TYPE,
    DYNAMIC_ENTRY_VALUE,
    EXECUTABLE_TYPE,
    MSG_TYPE,
    PERMISSION_SET,
    PROGRAM_HEADER_TYPE,
    SECURITY_CHECK,
    TERM_COLORS,
)
from common.context_handler import ContextHandler
from common.output_util import output_line, print_message
from common.util import check_elf, check_target


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

        checks = {
            "Canary": SECURITY_CHECK.NO,
            "NX Support": SECURITY_CHECK.UNKNOWN,
            "PIE Support": SECURITY_CHECK.UNKNOWN,
            "No RPath": SECURITY_CHECK.UNKNOWN,
            "No RunPath": SECURITY_CHECK.UNKNOWN,
            "Partial RelRO": SECURITY_CHECK.UNKNOWN,
            "Full RelRO": SECURITY_CHECK.UNKNOWN,
        }

        for symbol in target.GetModuleAtIndex(0):
            if symbol.GetName() in ["__stack_chk_fail", "__stack_chk_guard", "__intel_security_cookie"]:
                checks["Canary"] = SECURITY_CHECK.YES
                break

        try:
            if get_program_header_permission(target, PROGRAM_HEADER_TYPE.GNU_STACK) in PERMISSION_SET.NOT_EXEC:
                checks["NX Support"] = SECURITY_CHECK.YES
            else:
                checks["NX Support"] = SECURITY_CHECK.NO
        except MemoryError as error:
            print_message(MSG_TYPE.ERROR, error)
            checks["NX Support"] = SECURITY_CHECK.UNKNOWN

        try:
            if get_program_header_permission(target, PROGRAM_HEADER_TYPE.GNU_RELRO) is not None:
                checks["Partial RelRO"] = SECURITY_CHECK.YES
            else:
                checks["Partial RelRO"] = SECURITY_CHECK.NO
        except MemoryError as error:
            print_message(MSG_TYPE.ERROR, error)
            checks["Partial RelRO"] = SECURITY_CHECK.UNKNOWN

        try:
            if get_executable_type(target) == EXECUTABLE_TYPE.DYN:
                checks["PIE Support"] = SECURITY_CHECK.YES
            else:
                checks["PIE Support"] = SECURITY_CHECK.NO
        except MemoryError as error:
            print_message(MSG_TYPE.ERROR, error)
            checks["PIE Support"] = SECURITY_CHECK.UNKNOWN

        if checks["Partial RelRO"] == SECURITY_CHECK.UNKNOWN:
            checks["Full RelRO"] = SECURITY_CHECK.UNKNOWN
        elif (
            get_dynamic_entry(target, DYNAMIC_ENTRY_TYPE.FLAGS) == DYNAMIC_ENTRY_VALUE.BIND_NOW
            and checks["Partial RelRO"] == SECURITY_CHECK.YES
        ):
            checks["Full RelRO"] = SECURITY_CHECK.YES
        else:
            checks["Full RelRO"] = SECURITY_CHECK.NO

        if get_dynamic_entry(target, DYNAMIC_ENTRY_TYPE.RPATH) is None:
            checks["No RPath"] = SECURITY_CHECK.YES
        else:
            checks["No RPath"] = SECURITY_CHECK.NO

        if get_dynamic_entry(target, DYNAMIC_ENTRY_TYPE.RUNPATH) is None:
            checks["No RunPath"] = SECURITY_CHECK.YES
        else:
            checks["No RunPath"] = SECURITY_CHECK.NO

        for check, status in checks.items():
            if status == SECURITY_CHECK.YES:
                color = TERM_COLORS.GREEN.value
            elif status == SECURITY_CHECK.NO:
                color = TERM_COLORS.RED.value
            else:
                color = TERM_COLORS.GREY.value
            check += ": "
            output_line(f"{check:<20} {color}{status.value}{TERM_COLORS.ENDC.value}")
