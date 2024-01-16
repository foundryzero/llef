"""Break point handler."""
from typing import Any, Dict, Type

from lldb import (
    SBDebugger,
    SBExecutionContext,
    SBFrame,
    SBProcess,
    SBStream,
    SBStructuredData,
    SBTarget,
    SBThread,
)

from arch.base_arch import BaseArch
from common.context_handler import ContextHandler


class StopHookHandler:
    """Stop Hook handler."""

    frame: SBFrame
    process: SBProcess
    target: SBTarget
    thread: SBThread
    arch: Type[BaseArch]

    old_registers: Dict[str, int] = {}

    @classmethod
    def lldb_self_register(cls, debugger: SBDebugger, module_name: str) -> None:
        """Register the Stop Hook Handler"""

        command = f"target stop-hook add -P {module_name}.{cls.__name__}"
        debugger.HandleCommand(command)

    def __init__(
        self, target: SBTarget, _: SBStructuredData, __: Dict[Any, Any]
    ) -> None:
        """
        This is probably where a global state object should be initiated. Current version only uses
        class scoped state (e.g. self.old_registers). The limitation of this is that `commands` can't
        interact with state.

        For up to date documentation on args provided to this function run: `help target stop-hook add`
        """
        self.target = target

    def handle_stop(self, exe_ctx: SBExecutionContext, _: SBStream) -> None:
        """For up to date documentation on args provided to this function run: `help target stop-hook add`"""

        ContextHandler(self.target.debugger).display_context(exe_ctx)
