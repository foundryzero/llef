"""Context command class."""
from typing import Any, Dict, Type, Optional

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from lldb import (
    SBAddress,
    SBDebugger,
    SBError,
    SBExecutionContext,
    SBFrame,
    SBProcess,
    SBTarget,
    SBThread,
    SBValue,
)

from arch import get_arch
from arch.base_arch import BaseArch
from common.constants import GLYPHS, TERM_COLOURS
from common.context_handler import ContextHandler


class ContextCommand:
    """Implements the context"""

    program: str = "context"

    def __init__(self, debugger: SBDebugger, __: Dict[Any, Any]) -> None:
        super().__init__()
        self.context_handler = ContextHandler(debugger)

    @classmethod
    def lldb_self_register(cls, debugger: SBDebugger, module_name: str) -> None:
        command = f"command script add -c {module_name}.{cls.__name__} {cls.program}"
        debugger.HandleCommand(command)

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

        self.context_handler.display_context(exe_ctx)
