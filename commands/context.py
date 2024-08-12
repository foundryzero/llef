"""Context command class."""
import argparse
import shlex
from typing import Any, Dict

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext
from lldb import (
    SBDebugger,
    SBExecutionContext,
)

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
        subparsers = parser.add_subparsers()

        registers_parser = subparsers.add_parser("registers", help="show registers")
        registers_parser.set_defaults(action="registers")

        stack_parser = subparsers.add_parser("stack", help="show stack")
        stack_parser.set_defaults(action="stack")

        code_parser = subparsers.add_parser("code", help="show code")
        code_parser.set_defaults(action="code")

        threads_parser = subparsers.add_parser("threads", help="show threads")
        threads_parser.set_defaults(action="threads")

        trace_parser = subparsers.add_parser("trace", help="show trace")
        trace_parser.set_defaults(action="trace")

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

        if not hasattr(args, "action"):
            self.context_handler.display_context(exe_ctx)
            return
        
        self.context_handler.refresh(exe_ctx)
        if args.action == "registers":
            self.context_handler.display_registers()
        elif args.action == "stack":
            self.context_handler.display_stack()
        elif args.action == "code":
            self.context_handler.display_code()
        elif args.action == "threads":
            self.context_handler.display_threads()
        elif args.action == "trace":
            self.context_handler.display_trace()
