"""Global state module"""

from typing import Dict

from common.singleton import Singleton


class LLEFState(metaclass=Singleton):
    """
    Global state class - stores state accessible across any LLEF command/handler
    """

    # Stores previous register state at the last breakpoint
    prev_registers: Dict[str, int] = {}

    # Stores register state at the current breakpoint (caches the contents of the current frame as frame is mutable)
    current_registers: Dict[str, int] = {}

    # Stores patterns created by the `pattern` command
    created_patterns = []

    # Stores whether color should be used
    use_color = False

    # Stores whether output lines should be truncated
    truncate_output = True

    # Stores version of LLDB if on Linux. Stores clang verion if on Mac
    version = []

    # Linux, Mac (Darwin) or Windows
    platform = ""

    disassembly_syntax = ""

    def change_use_color(self, new_value: bool) -> None:
        """
        Change the global use_color bool. use_color should not be written to directly
        """
        self.use_color = new_value

    def change_truncate_output(self, new_value: bool) -> None:
        """Change the global truncate_output bool."""
        self.truncate_output = new_value
