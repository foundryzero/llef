"""Functions called in Go-mode that improve context output, usually by adding function names or types."""

import re
from typing import Union

from lldb import (
    SBAddress,
    SBDebugger,
    SBError,
    SBExecutionContext,
    SBFrame,
    SBInstruction,
    SBMemoryRegionInfoList,
    SBProcess,
    SBTarget,
    eInstructionControlFlowKindCall,
    eInstructionControlFlowKindCondJump,
    eInstructionControlFlowKindJump,
)

from arch.base_arch import BaseArch
from common.color_settings import LLEFColorSettings
from common.constants import GLYPHS, pointer
from common.golang.constants import (
    GO_MIN_PTR,
    GO_OBJECT_UNPACK_DEPTH,
    GO_TYPE_DECODE_DEPTH,
)
from common.golang.data import Confidence
from common.golang.static import setup_go
from common.golang.types import ExtractInfo, GoType
from common.golang.util import (
    bytes_for_saved_pc,
    get_arg_registers,
    go_context_analysis,
    go_find_func,
    go_find_func_name_offset,
    go_stackwalk,
)
from common.output_util import color_string, generate_rebased_address_string
from common.settings import LLEFSettings
from common.state import LLEFState
from common.util import is_code


def go_get_backtrace(
    proc: SBProcess, frame: SBFrame, arch: type[BaseArch], col: LLEFColorSettings, length: int
) -> Union[str, None]:
    """
    A Go-specific replacement for display_trace() in context_handler.py.

    :param SBProcess proc: The process object currently being debugged.
    :param int my_pc: The program counter indicating the location we've stopped.
    :param int sp: The current stack pointer.
    :param type[BaseArch] arch: Information about the architecture of the target.
    :param LLEFColorSettings col: Colour settings for output.
    :return Union[str, None]: Return backtrace as a string, or None if unable to unwind Go stack.
    """
    # Not all architectures are supported for backtrace. Currently, only x86 and x86_64 are supported.
    output = ""
    walk = go_stackwalk(proc, frame.GetPC(), frame.GetSP(), bytes_for_saved_pc(arch), length)
    if len(walk) > 0:

        for index, (pc, bp) in enumerate(walk):
            name, _ = go_find_func_name_offset(pc)
            if name:
                if index == 0:
                    number_color = col.highlighted_index_color
                else:
                    number_color = col.index_color
                line = color_string(f"#{index}", number_color, "[", "]")

                line += f"{pc:#x} "
                line += color_string(f"(fp={bp:#x})", col.rebased_address_color)
                line += f"  {GLYPHS.RIGHT_ARROW.value} {color_string(name, col.function_name_color)}"

                output += line + "\n"
        return output.rstrip()
    return None


def go_annotate_jumps(target: SBTarget, instruction: SBInstruction, lldb_frame_start: pointer, comment: str) -> str:
    """
    Annotates jump instructions with (if not already present) symbols.

    :param SBTarget target: The target context, currently being debugged.
    :param SBInstruction instruction: The particular instruction to analyse.
    :param int lldb_frame_start: This is where LLDB thinks the frame starts (a load address as per get_frame_range).
    :param str comment: The current comment LLDB gives to this instruction.
    :return str: Returns a new comment if able to find jump target information, otherwise the current comment.
    """
    new_comment = comment
    if instruction.GetControlFlowKind(target) in [
        eInstructionControlFlowKindCall,
        eInstructionControlFlowKindJump,
        eInstructionControlFlowKindCondJump,
    ]:
        jump_address: Union[int, None] = None

        if comment.startswith("<+"):
            try:
                jump_address = lldb_frame_start + int(comment[2:-1])
            except ValueError:
                pass

        if jump_address is None:
            # Try pulling the address directly from the instruction.
            try:
                jump_address = int(instruction.GetOperands(target), 0)
            except ValueError:
                pass

        if jump_address is not None:
            jump_name, jump_offset = go_find_func_name_offset(jump_address)
            if jump_name:
                new_comment = jump_name
                if jump_offset != 0:
                    new_comment += f" + {jump_offset}"

    return new_comment


def go_get_function_from_pc(pc: pointer, function_start: pointer, function_name: str) -> tuple[pointer, str]:
    """
    Attempt to match a recovered Go function symbol and address for pc.

    :param int pc: Code address (file offset) to search function ranges for.
    :param str function_name: The currently attributed symbol.
    :param int function_start: The currently attributed base address for that symbol.
    :return tuple[str, int]: An improved name/base pair, otherwise the provided function_name and function_start.
    """
    record = go_find_func(pc)
    if record is not None:
        (entry, gofunc) = record
        return (entry, gofunc.name)
    return (function_start, function_name)


def is_sufficient_confidence(q: Confidence, settings: LLEFSettings) -> bool:
    """
    Determines if the confidence of the unpacked object meets the user's requirement for it to be shown.

    :param Confidence q: The confidence of the unpacked object.
    :param LLEFSettings settings: Settings object used for accessing the confidence threshold.
    :return bool: Returns True if the object should be shown.
    """
    threshold = settings.go_confidence_threshold
    if threshold == "high" and (q is Confidence.CERTAIN or q is Confidence.HIGH):
        return True
    elif threshold == "medium" and (q is Confidence.CERTAIN or q is Confidence.HIGH or q is Confidence.MEDIUM):
        return True
    elif threshold == "low" and q is not Confidence.JUNK:
        # q is CERTAIN/HIGH/MEDIUM/LOW.
        return True

    return False


def attempt_object_unpack(
    proc: SBProcess, object_pointer: pointer, settings: LLEFSettings, col_settings: LLEFColorSettings
) -> Union[tuple[str, str], None]:
    """
    Precondition: must be called with LLEFState.go_state.moduledata_info not None.
    Looks up the pointer to see if its type has been deduced. If so, tries to unpack the pointer, and if successful
    returns an inline preview of the unpacking.

    :param SBProcess proc: The process object currently being debugged.
    :param pointer object_pointer: The raw pointer to fetch a guess for.
    :param LLEFSettings settings: The LLEFSettings for retrieving the confidence threshold.
    :param LLEFColorSettings col_settings: The LLEFColorSettings for generating the output.
    :return Union[tuple[str, str], None]: If extraction succeeded, returns an inline string to be displayed.
    Otherwise None.
    """
    to_return: Union[tuple[str, str], None] = None
    guessed_type_struct: Union[GoType, None] = LLEFState.go_state.type_guesses.search(object_pointer)
    if guessed_type_struct is not None:
        # Then we made a guess for this pointer as an object.
        info = ExtractInfo(
            proc=proc,
            ptr_size=LLEFState.go_state.pclntab_info.ptr_size,
            type_structs=LLEFState.go_state.moduledata_info.type_structs,  # type: ignore[union-attr]
        )
        obj = guessed_type_struct.extract_at(info, object_pointer, set(), GO_OBJECT_UNPACK_DEPTH)

        if is_sufficient_confidence(obj.confidence(), settings):
            type_string = guessed_type_struct.header.name
            if len(type_string) > 30:
                type_string = type_string[:29] + ".."

            if type_string == "string":
                object_string = color_string(obj, col_settings.string_color)
                object_string = f'"{object_string}"'
            else:
                object_string = color_string(obj, col_settings.dereferenced_value_color)

            type_string = color_string(f"({type_string})", col_settings.rebased_address_color)
            to_return = (type_string, object_string)
        else:
            LLEFState.go_state.type_guesses.delete(object_pointer)

    return to_return


def attempt_string_decode(buffer: bytes) -> str:
    """
    Attempts to decode the buffer with UTF-8.

    :param bytes buffer: The suspected string as bytes.
    :return str: The decoded string, otherwise empty string.
    """
    string = buffer.decode("utf-8", errors="ignore")
    # Respect null termination.
    string = string.split("\x00")[0]
    return repr(string)[1:-1]


def attempt_string_unpack(
    proc: SBProcess, str_pointer: pointer, col_settings: LLEFColorSettings, address_containing_pointer=None
) -> Union[str, None]:
    """
    Looks up the pointer to see if it's been registered as a possible string pointer. If so, unpacks that string
    and attempts to decode it as a Python string.

    :param SBProcess proc: The process object currently being debugged.
    :param pointer str_pointer: The raw pointer that could be the base address of a string.
    :param LLEFColorSettings col_settings: The LLEFColorSettings object for formatting the output.
    :return Union[str, None]: If a length was found for the string and decoding succeeded,
                              returns inline output. Otherwise None.
    """
    to_return: Union[str, None] = None
    guessed_string_length: Union[int, None] = LLEFState.go_state.string_guesses.search(str_pointer)

    if guessed_string_length is None and address_containing_pointer is not None:
        # Attempt to see if the next value in memory makes sense as a length value.
        next_memory_location = address_containing_pointer + LLEFState.go_state.pclntab_info.ptr_size
        err = SBError()
        try:
            size = proc.ReadUnsignedFromMemory(next_memory_location, LLEFState.go_state.pclntab_info.ptr_size, err)
            if err.Success() and size > 0:
                if str_pointer >= GO_MIN_PTR and size < GO_MIN_PTR:
                    LLEFState.go_state.string_guesses.add(str_pointer, size)
                    guessed_string_length = size
        except OverflowError:
            pass

    if guessed_string_length is not None:
        # Then we made a guess for this pointer as a string.
        successful_read = False
        # Safely attempt to read the memory:
        max_pointer_value = 1 << (LLEFState.go_state.pclntab_info.ptr_size * 8)
        if str_pointer >= 0 and guessed_string_length > 0 and str_pointer + guessed_string_length <= max_pointer_value:
            err = SBError()
            buffer = proc.ReadMemory(str_pointer, guessed_string_length, err)
            if err.Success() and buffer is not None:
                referenced_string = attempt_string_decode(buffer)
                if len(referenced_string) > 0:
                    successful_read = True
                    to_return = color_string(
                        referenced_string,
                        col_settings.string_color,
                        f' {GLYPHS.RIGHT_ARROW.value} ("',
                        '")',
                    )

        if not successful_read:
            LLEFState.go_state.string_guesses.delete(str_pointer)

    return to_return


def go_annotate_pointer_line(
    proc: SBProcess,
    target: SBTarget,
    regions: Union[SBMemoryRegionInfoList, None],
    pointer_to_annotate: pointer,
    address_containing_pointer: Union[pointer, None],
    settings: LLEFSettings,
    col_settings: LLEFColorSettings,
    depth: int = 0,
) -> str:
    """
    Go-specific annotations for values in the register or stack context views.
    Includes information for code pointers and type structures / corresponding object unpacking attempts.

    :param SBProcess proc: The process object currently being debugged.
    :param SBTarget target: The target context, currently being debugged.
    :param Union[SBMemoryRegionInfoList, None] regions: If register_coloring, the region list for the process.
    :param pointer pointer_to_annotate: The value read on this line of the context view.
    :param Union[pointer, None] address_containing_pointer: If on the stack, the address that contains this pointer.
    :param LLEFSettings settings: Settings object used for rebasing information.
    :param LLEFColorSettings col_settings: Colour settings used for output formatting.
    :param int depth: Depth for recursion.
    :return str: If annotations could be made, a string containing them. Otherwise empty string.
    """
    pointer_value = SBAddress(pointer_to_annotate, target)
    line = ""

    rebased = generate_rebased_address_string(
        pointer_value, settings.rebase_addresses, settings.rebase_offset, col_settings.rebased_address_color
    )

    if is_code(pointer_to_annotate, proc, target, regions):
        name, offset = go_find_func_name_offset(pointer_to_annotate)
        if name:
            line += f" {rebased} {GLYPHS.RIGHT_ARROW.value} "
            line += color_string(f"<{name}+{offset}>", col_settings.dereferenced_value_color)

    else:
        if LLEFState.go_state.moduledata_info is not None:
            # Attempt type inference.
            # Check for the condition that the current pointer is a pointer to a Go type,
            # and see if it makes sense that the next sequential pointer is an object of that type.

            # Attempt to see if previous analysis has identified this pointer as a type pointer.
            referenced_type_struct = LLEFState.go_state.moduledata_info.type_structs.get(pointer_to_annotate)
            if referenced_type_struct is not None:
                # Matching type has been found.
                next_pointer_unpacked = None
                if address_containing_pointer is not None:
                    # Guess the next pointer in memory aligns with the pointed to type object.
                    # If the association does not make sense, then the object won't be unpacked anyway.
                    next_pointer = address_containing_pointer + LLEFState.go_state.pclntab_info.ptr_size
                    # Associate Go data object with a Go type definition, so the link can be preserved.
                    # These pointers are stored in a Least-Recently-Used Dictionary structure, so type associations
                    # will eventually decay.
                    err = SBError()
                    object_ptr = proc.ReadUnsignedFromMemory(
                        next_pointer,
                        LLEFState.go_state.pclntab_info.ptr_size,
                        err,
                    )
                    # Sanity check - filter out pointers from integers.
                    if err.Success() and object_ptr >= GO_MIN_PTR:
                        # Associate the object pointer with its type for future display.
                        LLEFState.go_state.type_guesses.add(object_ptr, referenced_type_struct)
                        unpacked_data = attempt_object_unpack(proc, object_ptr, settings, col_settings)
                        if unpacked_data:
                            (_, next_pointer_unpacked) = unpacked_data

                # Markup line with identified Go data type.
                go_type_name = color_string(referenced_type_struct.header.name, col_settings.go_type_color)
                line += f" {GLYPHS.RIGHT_ARROW.value} Go type ptr: {go_type_name}"
                resolved = referenced_type_struct.get_underlying_type(GO_TYPE_DECODE_DEPTH)
                if referenced_type_struct.header.name != resolved:
                    line += " = " + resolved
                if next_pointer_unpacked:
                    line += f", possible match: {next_pointer_unpacked}?"

            else:
                # If it's not a type info struct, try unpacking it as an object.
                unpacked_data = attempt_object_unpack(proc, pointer_to_annotate, settings, col_settings)
                object_at_pointer = None
                if unpacked_data:
                    (resolved_type, object_at_pointer) = unpacked_data
                if object_at_pointer:
                    line += f" {GLYPHS.RIGHT_ARROW.value} {resolved_type} {object_at_pointer}"

        if line == "":
            # If it's not any of the above, try as a string.
            string_at_pointer = attempt_string_unpack(
                proc, pointer_to_annotate, col_settings, address_containing_pointer
            )
            if string_at_pointer:
                line += string_at_pointer

    if line == "" and depth == 0:
        # Check to see if the pointer is to an object we can mark up.
        err = SBError()
        if pointer_to_annotate > GO_MIN_PTR:
            dereferenced_value = proc.ReadPointerFromMemory(pointer_to_annotate, err)
            if err.Success():
                recursive_line = go_annotate_pointer_line(
                    proc, target, regions, dereferenced_value, pointer_to_annotate, settings, col_settings, depth=1
                )
                if recursive_line:
                    line = f" {GLYPHS.RIGHT_ARROW.value} *{hex(dereferenced_value)}{recursive_line}"

    return line


def add_type_guess_to_register_value(frame: SBFrame, reg_name: str, type_struct: GoType) -> None:
    """
    Attempt to assign a type guess to the pointer held in the named register.

    :param SBFrame frame: The current frame, to retrieve registers from.
    :param str reg_name: The name of the register to inspect.
    :param GoType type_struct: The Python type information structure to assign against this register value.
    """
    pointer_value = frame.FindRegister(reg_name)
    if pointer_value.IsValid():
        pointer = pointer_value.GetValueAsUnsigned()
        if pointer >= GO_MIN_PTR:
            LLEFState.go_state.type_guesses.add(pointer, type_struct)


def go_stop_hook(exe_ctx: SBExecutionContext, arch: BaseArch, settings: LLEFSettings, debugger: SBDebugger) -> None:
    """
    This function is called with every refresh of the context view.
    Ensures the binary has been statically analysed if not already, and performs dynamic Go analysis.

    :param SBExecutionContext exe_ctx: The execution context for retrieving frame, process and target.
    :param BaseArch arch: The class describing our current target architecture.
    :param LLEFSettings settings: The LLEFSettings class used to query Go support level.
    """

    frame = exe_ctx.GetFrame()
    proc = exe_ctx.GetProcess()
    target = exe_ctx.GetTarget()

    # If Go support is disabled, this function will do nothing.
    # Only analyse if not done already.
    if settings.go_support_level != "disable" and not LLEFState.go_state.analysed:
        setup_go(proc, target, settings)
        if go_context_analysis(settings):
            # The Go runtime issues lots of SIGURG signals which causes a stop by default.
            debugger.HandleCommand("process handle SIGURG --stop 0 --notify 0 ")

    # If we have now determined this is not a Go binary / Go support disabled, then quit.
    if not go_context_analysis(settings):
        return

    arg_registers = get_arg_registers(arch)
    (go_min_version, _) = LLEFState.go_state.pclntab_info.version_bounds
    if go_min_version >= 17:
        # HOOK TASK 1:
        # Register-straddling interface/string guessing. Needs register-based calling convention (Go >= 1.17).
        for i in range(len(arg_registers) - 1):
            # Try type pointer in arg_registers[i], data pointer in arg_registers[i+1]
            abi_register = frame.FindRegister(arg_registers[i])
            if abi_register.IsValid():
                arg_value = abi_register.GetValueAsUnsigned()

                found_type = False
                if LLEFState.go_state.moduledata_info is not None:
                    # Attempt to match arg_value against list of known type pointers.
                    type_struct = LLEFState.go_state.moduledata_info.type_structs.get(arg_value)
                    if type_struct is not None:
                        # It's a type information struct, so guess pointer in next register as that type of value.
                        add_type_guess_to_register_value(frame, arg_registers[i + 1], type_struct)
                        found_type = True

                if not found_type:
                    # Attempt to determine if there is a string, where reg i is the pointer and reg i+1 is the length.
                    next_abi_register = frame.FindRegister(arg_registers[i + 1])
                    if next_abi_register.IsValid():
                        next_register_value = next_abi_register.GetValueAsUnsigned()
                        if arg_value >= GO_MIN_PTR and next_register_value < GO_MIN_PTR:
                            LLEFState.go_state.string_guesses.add(arg_value, next_register_value)

        # HOOK TASK 2:
        # Pointer receiver guessing. Needs register-based calling convention and present ModuleData.
        pc = frame.GetPC()
        record = go_find_func(pc)
        if record is not None and LLEFState.go_state.moduledata_info is not None:
            (entry, gofunc) = record
            if entry != LLEFState.go_state.prev_func:
                LLEFState.go_state.prev_func = entry
                # Either this function was just called, or we stopped in the middle of it.
                # Take one-shot guess at pointer receiver if applicable.

                # Regex is for the literal string .(*X). where X is any string. i.e. a pointer receiver.
                match = re.search(r"\.\(\*.*\)\.", gofunc.name)
                if match is not None:
                    ptr_receiver = match.group(0)[3:-2]
                    path = gofunc.name[: match.start()].split("/")
                    if len(path) > 0:
                        module_name = path[-1]

                        # Attempt to match the type name against names found in the Go runtime.
                        type_name = module_name + "." + ptr_receiver
                        type_obj: Union[GoType, None] = None
                        for t in LLEFState.go_state.moduledata_info.type_structs.values():
                            if t.header.name == type_name:
                                type_obj = t
                                break

                        if type_obj is not None:
                            # If the type object was found, lable the pointer receiver register against that type.
                            # As per https://go.dev/s/regabi, X86 uses RAX/EAX and ARM uses R0, etc.
                            # (first register in the calling convention)
                            add_type_guess_to_register_value(frame, arg_registers[0], type_obj)
