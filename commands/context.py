"""Context command class."""
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
        self.context_handler = ContextHandler(debugger)

    @staticmethod
    def get_short_help() -> str:
        return "Usage: context\n"

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

        self.context_handler.display_context(exe_ctx)
