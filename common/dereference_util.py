from lldb import SBAddress, SBError, SBInstruction, SBMemoryRegionInfoList, SBProcess, SBTarget

from common.color_settings import LLEFColorSettings
from common.constants import GLYPHS, MSG_TYPE, TERM_COLORS
from common.output_util import output_line, print_message
from common.util import attempt_to_read_string_from_memory, hex_or_str, is_code

color_settings = LLEFColorSettings()


def read_instruction(target: SBTarget, address: int) -> SBInstruction:
    """
    We disassemble an instruction at the given memory @address.

    :param target: The target object file.
    :param address: The memory address of the instruction.
    :return: An object of the disassembled instruction.
    """
    instruction_address = SBAddress(address, target)
    instruction_list = target.ReadInstructions(instruction_address, 1, "intel")
    return instruction_list.GetInstructionAtIndex(0)


def dereference_last_address(data: list, target: SBTarget, process: SBProcess, regions: SBMemoryRegionInfoList):
    """
    Memory data at the last address (second to last in @data list) is
    either disassembled to an instruction or converted to a string or neither.

    :param data: List of memory addresses/data.
    :param target: The target object file.
    :param process: The running process of the target.
    :param regions: List of memory regions of the process.
    """
    last_address = data[-2]

    if is_code(last_address, process, target, regions):
        instruction = read_instruction(target, last_address)
        if instruction.IsValid():
            data[-1] = (
                f"{TERM_COLORS[color_settings.instruction_color].value}{instruction.GetMnemonic(target)} "
                + f"{instruction.GetOperands(target)}{TERM_COLORS.ENDC.value}"
            )
    else:
        string = attempt_to_read_string_from_memory(process, last_address)
        if string != "":
            data[-1] = f"{TERM_COLORS[color_settings.string_color].value}{string}{TERM_COLORS.ENDC.value}"


def dereference(address: int, offset: int, target: SBTarget, process: SBProcess, regions: SBMemoryRegionInfoList):
    """
    Dereference a memory @address until it reaches data that cannot be resolved to an address.
    Memory data at the last address is either disassembled to an instruction or converted to a string or neither.
    The chain of dereferencing is output.

    :param address: The address to dereference
    :param offset: The offset of address from a choosen base.
    :param target: The target object file.
    :param process: The running process of the target.
    :param regions: List of memory regions of the process.
    """

    data = []

    error = SBError()
    while error.Success():
        data.append(address)
        address = process.ReadPointerFromMemory(address, error)
        if len(data) > 1 and data[-1] in data[:-2]:
            data.append("[LOOPING]")
            break

    if len(data) < 2:
        print_message(MSG_TYPE.ERROR, f"{hex(data[0])} is not accessible.")
        return

    dereference_last_address(data, target, process, regions)

    output = f"{TERM_COLORS.CYAN.value}{hex_or_str(data[0])}{TERM_COLORS.ENDC.value}{GLYPHS.VERTICAL_LINE.value}"
    if offset >= 0:
        output += f"+0x{offset:04x}: "
    else:
        output += f"-0x{-offset:04x}: "
    output += " -> ".join(map(hex_or_str, data[1:]))
    output_line(output)
