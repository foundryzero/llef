"""Various utility functions used for Go analysis"""

from functools import lru_cache
from typing import Any, Union

from lldb import SBError, SBFrame, SBProcess

from arch.aarch64 import Aarch64
from arch.arm import Arm
from arch.base_arch import BaseArch
from arch.i386 import I386
from arch.ppc import PPC
from arch.x86_64 import X86_64
from common.constants import pointer
from common.golang.interfaces import GoFunc
from common.settings import LLEFSettings
from common.state import LLEFState


def go_context_analysis(settings: LLEFSettings) -> bool:
    """
    Check preconditions for running Go context analysis functions on the current binary:
    1. The current binary is a Go binary.
    2. The one-shot static Go analysis has been performed successfully.
    3. The user-configurable setting for Go analysis is set to either "auto" or "force".

    :param LLEFSettings settings: The LLEFSettings object for accessing the user-configured Go support level.
    :return bool: Returns True if all preconditions for Go context analysis are met, otherwise False.
    """

    return (
        LLEFState.go_state.is_go_binary
        and LLEFState.go_state.analysed
        and settings.go_support_level in ("auto", "force")
    )


def is_address_go_frame_pointer(settings: LLEFSettings, addr: int, frame: SBFrame) -> bool:
    """
    Checks whether the given address is the current Go frame pointer.

    :param LLEFSettings settings: The LLEFSettings for checking Go support level.
    :param int addr: A stack address.
    :param SBFrame frame: The current frame containing PC and SP information.
    :return bool: Returns true if the given address is the current Go frame pointer.
    """
    if go_context_analysis(settings):
        # Need to calculate base pointer as it may not be stored in dedicated bp register depending on arch.
        bp = go_calculate_base_pointer(frame.GetPC(), frame.GetSP())
        return addr == bp

    return False


def bytes_for_saved_pc(arch: type[BaseArch]) -> int:
    """
    Calculates how many bytes are taken up by a saved return address.

    :param Type[BaseArch] arch: The class describing our current target architecture
    :return int: The size of a saved return pointer. Returns 0 for unsupported architectures.
    """
    if arch in (I386, X86_64):
        return arch().bits // 8
    return 0


def go_stackwalk(proc: SBProcess, pc: int, sp: int, bytes_for_pc: int, length: int) -> list[tuple[int, int]]:
    """
    Walks back through stack frames from the current frame. Uses metadata intended for Go's panic traceback.

    :param SBProcess proc: The process object currently being debugged.
    :param int pc: The current program counter to begin walking at.
    :param int sp: The current stack pointer to begin walking at.
    :param int bytes_for_pc: How many bytes are taken up by a saved return address.
    :return list[tuple[int, int]]: A list of PC, frame pointer pairs tracing through the call stack.
    """
    if bytes_for_pc == 0:
        # Unsupported architecture for stack walking.
        return []

    out = []
    # Hard-cap the number of iterations, as we only display so many on-screen.
    for _ in range(length):
        bp = go_calculate_base_pointer(pc, sp)
        out.append((pc, bp or 0))
        if bp is None:
            break
        ra_loc = bp
        sp = bp + bytes_for_pc

        err = SBError()
        max_pointer_size = 1 << (LLEFState.go_state.pclntab_info.ptr_size * 8)
        if ra_loc >= 0 and ra_loc + bytes_for_pc <= max_pointer_size:
            pc = proc.ReadUnsignedFromMemory(ra_loc, bytes_for_pc, err)
            if err.Fail():
                break
        else:
            break
    return out


def go_find_func_name_offset(pc: int) -> tuple[str, int]:
    """
    Retrieves the name of the function containing the supplied program counter, and the offset from its entry address.

    :param int pc: Program counter, a pointer to code.
    :return tuple[str, int]: Returns the Go function name and offset into it corresponding to the supplied address.
    """
    record = go_find_func(pc)
    if record is not None:
        (entry, gofunc) = record
        return (gofunc.name, pc - entry)

    # otherwise, gracefully fail for display purposes
    return ("", pc)


def pc_binsearch(search_pc: pointer, data: list[tuple[pointer, Any]]) -> Union[tuple[pointer, Any], None]:
    """
    Implements a generic binary search to find a record (of any type)
    paired to the highest PC that is less than or equal to the search_pc.

    :param pointer search_pc: Program counter, the code address.
    :return Union[tuple[pointer, Any], None]: The record associated with the greatest PC still less than search_pc,
                                          otherwise None.
    """
    n = len(data)

    # let pcs = map(data, lambda x: x[0])
    # Precondition: pcs is sorted (a safe assumption since the Go runtime relies on it)
    # Postcondition: finds i s.t. pcs[i] <= search_pc && pcs[i+1] > search_pc
    left = 0
    right = n
    # Invariant: pcs[0..left) <= search_pc && pcs[right..n) > search_pc.
    # The invariant is true at the beginning and end of every loop cycle.
    # Liveness variant: (right - left) is strictly decreasing
    while right - left > 0:
        middle = (left + right) // 2
        if data[middle][0] <= search_pc:
            left = middle + 1
        else:
            right = middle
    # Inv & !cond => left = right
    #             => pcs[0..left) <= search_pc && pcs[left..n) > search_pc

    if left == 0:
        # all pcs > search_pc
        return None

    # func_entries[0..left-1] <= search_pc, so left-1 is our man.
    return data[left - 1]


# Caching is safe - we clear whenever internal state changes.
@lru_cache(maxsize=128)
def go_find_func(pc: pointer) -> Union[tuple[pointer, GoFunc], None]:
    """
    Performs a binary search to find the function record corresponding to a code address.

    :param pointer pc: Program counter, the code address.
    :return Union[tuple[pointer, str], None]: Returns the function record containing the program counter,
    otherwise None.
    """
    result = None
    if pc <= LLEFState.go_state.pclntab_info.max_pc_runtime:
        func_mapping = LLEFState.go_state.pclntab_info.func_mapping
        result = pc_binsearch(pc, func_mapping)
    return result


# Caching is safe - we clear whenever internal state changes.
@lru_cache(maxsize=128)
def go_calculate_base_pointer(pc: pointer, sp: pointer) -> Union[pointer, None]:
    """
    Performs two binary searches to first identify the function, then the stack pointer delta, corresponding to a PC.

    :param pointer pc: The current program counter.
    :param pointer sp: The current stack pointer.
    :return Union[pointer, None]: Returns the offset from the stack pointer to the Go frame pointer,
    else None if unknown.
    """
    if pc <= LLEFState.go_state.pclntab_info.max_pc_runtime:
        func_mapping = LLEFState.go_state.pclntab_info.func_mapping

        result = pc_binsearch(pc, func_mapping)
        if result is not None:
            stack_deltas = result[1].stack_deltas

            result2 = pc_binsearch(pc, stack_deltas)
            if result2 is not None:
                stack_delta: int = result2[1]
                return sp + stack_delta
    return None


def get_arg_registers(arch: BaseArch) -> list[str]:
    """
    Get a sequence of register names in which Go will pass arguments before going to the stack.
    See https://go.dev/s/regabi.

    :param BaseArch arch: The object describing our current target architecture
    :return list[str]: The ordered list of register names that Go passes function arguments in.
    """
    if isinstance(arch, I386):
        return ["eax", "ebx", "ecx", "edi", "esi"]
    elif isinstance(arch, X86_64):
        return ["rax", "rbx", "rcx", "rdi", "rsi", "r8", "r9", "r10", "r11"]
    elif isinstance(arch, Arm):
        return ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7"]
    elif isinstance(arch, Aarch64):
        return ["x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15"]
    elif isinstance(arch, PPC):
        return ["r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"]
    else:
        return []
