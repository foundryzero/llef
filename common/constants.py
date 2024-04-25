"""Constant definitions."""

from enum import Enum


class TERM_COLORS(Enum):
    """Used to colorify terminal output."""

    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    PINK = "\033[35m"
    CYAN = "\033[36m"
    GREY = "\033[1;38;5;240m"
    ENDC = "\033[0m"


class MSG_TYPE(Enum):
    """Log message types."""

    INFO = 1
    SUCCESS = 2
    ERROR = 3


class GLYPHS(Enum):
    """Various characters required to match GEF output."""

    LEFT_ARROW = " ← "
    RIGHT_ARROW = " → "
    DOWN_ARROW = "↳"
    HORIZONTAL_LINE = "─"
    VERTICAL_LINE = "│"
    CROSS = "✘ "
    TICK = "✓ "
    BP_GLYPH = "●"


class ALIGN(Enum):
    """Alignment values."""

    LEFT = 1
    CENTRE = 2
    RIGHT = 3
