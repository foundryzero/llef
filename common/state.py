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

    # Stores version of LLDB if on Linux. Stores clang verion if on Mac
    version = []

    # Linux, Mac (Darwin) or Windows
    platform = ""

    disassembly_syntax = None
