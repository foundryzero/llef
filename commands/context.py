"""Context command class."""

import argparse
import shlex
from typing import Any, Dict

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_command import BaseCommand
from common.context_handler import ContextHandler
from common.util import output_line


class ContextCommand(BaseCommand):
    """Implements the context"""

    program: str = "context"
    container = None

    def __init__(self, debugger: SBDebugger, __: Dict[Any, Any]) -> None:
        super().__init__()
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser(description="context command")
        parser.add_argument(
            "sections", nargs="*", choices=["registers", "stack", "code", "threads", "trace", "all"], default="all"
        )

        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: context [section (optional)]\n"

    @staticmethod
    def get_long_help() -> str:
        return "Refresh and print the context\n"

    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'context' command"""

        if not exe_ctx.frame:
            output_line("Program not running")
            return

        args = self.parser.parse_args(shlex.split(command))

        if not hasattr(args, "sections"):
            output_line(self.__class__.get_long_help())
            return

        self.context_handler.refresh(exe_ctx)

        if "all" in args.sections:
            self.context_handler.display_context(exe_ctx, False)
        else:
            if "registers" in args.sections:
                self.context_handler.display_registers()
            if "stack" in args.sections:
                self.context_handler.display_stack()
            if "code" in args.sections:
                self.context_handler.display_code()
            if "threads" in args.sections:
                self.context_handler.display_threads()
            if "trace" in args.sections:
                self.context_handler.display_trace()
