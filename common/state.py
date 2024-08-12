"""Global state module"""
from typing import Dict

from common.singleton import Singleton


class LLEFState(metaclass=Singleton):
    """
    Global state class - stores state accessible across any LLEF command/handler
    """

    # Stores previous register state at the last breakpoint
    prev_registers: Dict[str, int] = {}

    # Stores patterns created by the `pattern` command
    created_patterns = []

    # Stores whether color should be used
    use_color = False
