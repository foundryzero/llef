import re
from typing import List

from lldb import SBAddress, SBInstruction, SBTarget

from common.color_settings import LLEFColorSettings
from common.output_util import color_string, output_line


def extract_instructions(
    target: SBTarget, start_address: int, end_address: int, disassembly_flavour: str
) -> List[SBInstruction]:
    """
    Returns a list of instructions between a range of memory address defined by @start_address and @end_address.

    :param target: The target context.
    :param start_address: The address to start reading instructions from memory.
    :param end_address: The address to stop reading instruction from memory.
    :return: A list of instructions.
    """
    instructions = []
    current = start_address
    while current <= end_address:
        address = SBAddress(current, target)
        instruction = target.ReadInstructions(address, 1, disassembly_flavour).GetInstructionAtIndex(0)
        instructions.append(instruction)
        instruction_size = instruction.GetByteSize()
        if instruction_size > 0:
            current += instruction_size
        else:
            break

    return instructions


def color_operands(
    operands: str,
    color_settings: LLEFColorSettings,
):
    """
    Colors the registers and addresses in the instruction's operands.

    :param operands: A string of the instruction's operands returned from instruction.GetOperands().
    :param color_settings: Contains the color settings to color the instruction.
    """

    # Addresses can start with either '$0x', '#0x' or just '0x', followed by atleast one hex value.
    address_pattern = r"(\$?|#?)-?0x[0-9a-fA-F]+"

    # Registers MAY start with '%'.
    # Then there MUST be a sequence of letters, which CAN be followed by a number.
    # A register can NEVER start with numbers or any other special character other than '%'.
    register_pattern = r"(?<![\w])%?[a-zA-Z]+[0-9]*"

    def color_register(match):
        return color_string(match.group(0), color_settings.register_color)

    def color_address(match):
        return color_string(match.group(0), color_settings.address_operand_color)

    operands = re.sub(register_pattern, color_register, operands)
    operands = re.sub(address_pattern, color_address, operands)

    return operands


def print_instruction(
    target: SBTarget,
    instruction: SBInstruction,
    base: int,
    color_settings: LLEFColorSettings,
    highlight: bool = False,
) -> None:
    """
    Print formatted @instruction extracted from SBInstruction object.

    :param target: The target executable.
    :param instruction: The instruction object.
    :param base: The address base to calculate offsets from.
    :param color_settings: Contains the color settings to color the instruction.
    :param highlight: If true, highlight the whole instruction with the highlight color.
    """

    address = instruction.GetAddress().GetLoadAddress(target)
    offset = address - base

    line = hex(address)
    if offset >= 0:
        line += f" <+{offset:02}>: "
    else:
        line += f" <-{abs(offset):02}>: "

    mnemonic = instruction.GetMnemonic(target) or ""
    operands = instruction.GetOperands(target) or ""
    comment = instruction.GetComment(target) or ""

    if not highlight:
        operands = color_operands(operands, color_settings)

    if comment != "":
        comment = f"; {comment}"
    line += f"{mnemonic:<10}{operands:<30}{comment}"

    if highlight:
        line = color_string(line, color_settings.highlighted_instruction_color)

    output_line(line)


def print_instructions(
    target: SBTarget,
    instructions: List[SBInstruction],
    base: int,
    color_settings: LLEFColorSettings,
) -> None:
    """
    Print formatted @instructions extracting information from the SBInstruction objects.

    :param target: The target executable.
    :param instructions: A list of instruction objects.
    :param base: The address base to calculate offsets from.
    :param color_settings: Contains the color settings to color the instruction.
    """
    for instruction in instructions:
        print_instruction(target, instruction, base, color_settings)
