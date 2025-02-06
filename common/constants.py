"""Constant definitions."""

from enum import Enum, IntEnum


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


class SIZES(Enum):
    """Size of data types"""

    QWORD = 8
    DWORD = 4
    WORD = 2
    BYTE = 1


class SECURITY_CHECK(Enum):
    NO = "No"
    YES = "Yes"
    UNKNOWN = "Unknown"


class PERMISSION_SET:
    """Values for 3bit permission sets."""

    NOT_EXEC = [0, 2, 4, 6]
    EXEC = [1, 3, 5, 7]


class PROGRAM_HEADER_TYPE(IntEnum):
    """Program header type values (in ELF files)."""

    GNU_STACK = 0x6474E551
    GNU_RELRO = 0x6474E552


class EXECUTABLE_TYPE(IntEnum):
    """Executable ELF file types."""

    DYN = 0x03


class DYNAMIC_ENTRY_TYPE(IntEnum):
    """Entry types in the .dynamic section table of the ELF file."""

    FLAGS = 0x1E
    RPATH = 0x0F
    RUNPATH = 0x1D


class DYNAMIC_ENTRY_VALUE(IntEnum):
    """Entry values in the .dynamic section table of the ELF file."""

    BIND_NOW = 0x08


class ARCH_BITS(IntEnum):
    """32bit or 64bit architecture."""

    BITS_32 = 1
    BITS_64 = 2
