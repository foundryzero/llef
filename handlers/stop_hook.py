"""Break point handler."""

from typing import Any

from lldb import SBDebugger, SBExecutionContext, SBStream, SBStructuredData, SBTarget

from common.context_handler import ContextHandler


class StopHookHandler:
    """Stop Hook handler."""

    context_handler: ContextHandler

    @classmethod
    def lldb_self_register(cls, debugger: SBDebugger, module_name: str) -> None:
        """Register the Stop Hook Handler"""

        command = f"target stop-hook add -P {module_name}.{cls.__name__}"
        debugger.HandleCommand(command)

    def __init__(self, target: SBTarget, _: SBStructuredData, __: dict[Any, Any]) -> None:
        """
        For up to date documentation on args provided to this function run: `help target stop-hook add`
        """
        self.context_handler = ContextHandler(target.debugger)

    def handle_stop(self, exe_ctx: SBExecutionContext, _: SBStream) -> None:
        """For up to date documentation on args provided to this function run: `help target stop-hook add`"""
        self.context_handler.display_context(exe_ctx, True)
