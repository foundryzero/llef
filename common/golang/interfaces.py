"Dataclasses (emulating structs in Python) for read-only information return from parsing utilities"

from dataclasses import dataclass

from common.golang.types import GoType


@dataclass(frozen=True)
class GoFunc:
    """
    A datastructure for describing an individual Go function.
    """

    # The name of the function. Can be recovered even if the binary is stripped.
    name: str
    # The address of the function as in the binary. This may be distinct from the address it has been loaded at.
    file_addr: int

    # A list of pairs of program counter followed by the stack delta at that point in execution - this is the
    # difference between the current stack pointer register and the stack pointer as it was at function entry.
    # Used to calculate a base frame pointer.
    stack_deltas: list[tuple[int, int]]


@dataclass(frozen=True)
class PCLnTabInfo:
    """
    A datastructure that stores information retrieved from the PCLNTAB section.
    """

    # The last address in the text section, or the highest possible value the program counter can take.
    # Available both as relative to the binary (file) and as in-memory (load).
    max_pc_file: int
    max_pc_load: int

    # A list of pairs of program counter, then GoFunc - the program counter is the entry address of that function.
    func_mapping: list[tuple[int, GoFunc]]

    # A tuple describing (min_version, max_version). We guarantee that min_version <= actual go version <= max_version.
    version_bounds: tuple[int, int]

    # The size of a pointer on this architecture in bytes.
    ptr_size: int


@dataclass(frozen=True)
class ModuleDataInfo:
    """
    A datastructure that stores information retreieved from the ModuleData structure.
    """

    # A mapping from type structure address (as in the binary) to a parsed python GoType struct.
    type_structs: dict[int, GoType]
