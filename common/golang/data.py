from dataclasses import dataclass
from enum import Enum

from common.golang.constants import GO_STR_TRUNCATE_LEN


class Confidence(Enum):
    JUNK = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CERTAIN = 5

    def to_float(self) -> float:
        if self is Confidence.JUNK:
            return 0.0
        elif self is Confidence.LOW:
            return 0.2
        elif self is Confidence.MEDIUM:
            return 0.4
        elif self is Confidence.HIGH:
            return 0.7
        else:
            # CERTAIN (only to provide a 1.0, not for comparing against!)
            return 1.0


@dataclass(frozen=True)
class GoData:
    """
    Base class for Python representations of Go objects.
    """

    heuristic: float  # Internal only: a measure from 0.0-1.0 of how successful the parsing was.

    def confidence(self) -> Confidence:
        if self.heuristic < Confidence.LOW.to_float():
            return Confidence.JUNK
        elif self.heuristic < Confidence.MEDIUM.to_float():
            return Confidence.LOW
        elif self.heuristic < Confidence.HIGH.to_float():
            return Confidence.MEDIUM
        else:
            return Confidence.HIGH


@dataclass(frozen=True)
class GoDataBad(GoData):
    """
    The underlying memory region doesn't exist or the values obtained cannot constitute a legal Go object.
    """

    def __str__(self) -> str:
        return "?"


@dataclass(frozen=True)
class GoDataUnparsed(GoData):
    """
    There was more to parse, but we ran out of depth.
    The heuristic represents how likely we think the data would be valid.
    """

    address: int

    def __str__(self) -> str:
        return hex(self.address) + ".."


@dataclass(frozen=True)
class GoDataBool(GoData):
    """
    A boolean.
    """

    value: bool

    def __str__(self) -> str:
        if self.value:
            return "true"
        else:
            return "false"


@dataclass(frozen=True)
class GoDataInteger(GoData):
    """
    A uint or int.
    """

    value: int

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class GoDataFloat(GoData):
    """
    A floating point number.
    """

    value: float

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class GoDataComplex(GoData):
    """
    A complex number (two floats).
    """

    real: float
    imag: float

    def __str__(self) -> str:
        return f"({self.real}+{self.imag}i)"


@dataclass(frozen=True)
class GoDataArray(GoData):
    """
    An array.
    """

    contents: list[GoData]

    def __str__(self) -> str:
        build = "["
        for elem in self.contents:
            if isinstance(elem, GoDataString):
                build += f'"{str(elem)}", '
            else:
                build += f"{str(elem)}, "
        return build.removesuffix(", ") + "]"


@dataclass(frozen=True)
class GoDataSlice(GoData):
    """
    A slice.
    """

    base: int
    length: int
    capacity: int

    # The len(self.contents) may be less than self.length, in the case of a memory read error or truncation.
    contents: list[GoData]

    def __str__(self) -> str:
        if len(self.contents) == 0:
            return f"<slice @{hex(self.base)} #{self.length}/{self.capacity}>"

        else:
            build = "["
            for elem in self.contents:
                build += str(elem) + ", "
            build = build.removesuffix(", ")
            if len(self.contents) < self.length:
                build += f"...{self.length - len(self.contents)} more"
            return build + "]"


@dataclass(frozen=True)
class GoDataString(GoData):
    """
    A string.
    """

    base: int
    length: int

    # The len(self.contents) may be less than self.length, in the case of a memory read error.
    contents: bytes

    def __str__(self) -> str:
        if len(self.contents) == self.length:
            full = self.contents.decode("utf-8", "replace")
            rep = repr(full)
            # Switch single quotes from repr() to double quotes.
            if len(rep) >= 2:
                rep = rep[1:-1]
            if len(rep) > GO_STR_TRUNCATE_LEN:
                return rep[: GO_STR_TRUNCATE_LEN - 1] + ".."
            else:
                return rep
        else:
            return f"<string @{hex(self.base)} #{self.length}>"


@dataclass(frozen=True)
class GoDataStruct(GoData):
    """
    A struct.
    """

    fields: list[tuple[str, GoData]]

    def __str__(self) -> str:
        build = "{"
        for f_name, f_val in self.fields:
            if isinstance(f_val, GoDataString):
                build += f'{f_name}: "{str(f_val)}", '
            else:
                build += f"{f_name}: {str(f_val)}, "
        build = build.removesuffix(", ") + "}"
        return build


@dataclass(frozen=True)
class GoDataMap(GoData):
    """
    A map.
    """

    entries: list[tuple[GoData, GoData]]

    def __str__(self) -> str:
        build = "["
        for key, val in self.entries:
            if isinstance(val, GoDataString):
                build += f'{key}: "{str(val)}", '
            else:
                build += f"{key}: {str(val)}, "
        build = build.removesuffix(", ") + "]"
        return build


@dataclass(frozen=True)
class GoDataPointer(GoData):
    """
    A pointer.
    """

    address: int

    def __str__(self) -> str:
        return hex(self.address)
