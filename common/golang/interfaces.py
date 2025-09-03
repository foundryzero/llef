from dataclasses import dataclass

from common.constants import pointer
from common.golang.types import GoType


@dataclass(frozen=True)
class GoFunc:
    """
    A data structure for describing an individual Go function.
    """

    # The name of the function. Can be recovered even if the binary is stripped.
    name: str
    # The location of the function as an offset into the binary.
    file_addr: int

    # A list of pairs of program counter followed by the stack delta at that point in execution - this is the
    # difference between the current stack pointer register and the stack pointer as it was at function entry.
    # Used to calculate a base frame pointer.
    stack_deltas: list[tuple[pointer, int]]


@dataclass(frozen=True)
class PCLnTabInfo:
    """
    A data structure that stores information retrieved from the PCLNTAB section.
    """

    # The last address in the text section, or the highest possible value the program counter can take.
    # Available both as relative to the binary (file) and address at runtime.
    max_pc_file: int
    max_pc_runtime: pointer

    # A list of pairs of program counter, then GoFunc - the program counter is the entry address of that function.
    func_mapping: list[tuple[pointer, GoFunc]]

    # A tuple describing (min_version, max_version). We guarantee that min_version <= actual go version <= max_version.
    version_bounds: tuple[int, int]

    # The size of a pointer on this architecture in bytes.
    ptr_size: int


@dataclass(frozen=True)
class ModuleDataInfo:
    """
    A data structure that stores information retrieved from the ModuleData structure.
    """

    # A mapping from type structure address (offset into the binary) to a parsed python GoType struct.
    type_structs: dict[int, GoType]
