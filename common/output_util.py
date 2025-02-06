"""Utility functions related to terminal output."""

import os
import re
from typing import Any, List

from lldb import SBInstruction, SBTarget

from common.constants import ALIGN, DEFAULT_TERMINAL_COLUMNS, DEFAULT_TERMINAL_LINES, GLYPHS, MSG_TYPE, TERM_COLORS
from common.state import LLEFState


def color_string(string: str, color_setting: str, lwrap: str = "", rwrap: str = "") -> str:
    """
    Colors a @string based on the @color_setting.
    Optional: Wrap the string with uncolored strings @lwrap and @rwrap.

    :param string: The string to color.
    :param color_setting: The color that will be fetched from TERM_COLORS (i.e., TERM_COLORS[color_setting]).
    :param lwrap: Uncolored string prepended to the colored @string.
    :param rwrap: Uncolored string appended to the colored @string.
    :return: The resulting string.
    """
    if color_setting is None:
        result = f"{lwrap}{string}{rwrap}"
    else:
        result = f"{lwrap}{TERM_COLORS[color_setting].value}{string}{TERM_COLORS.ENDC.value}{rwrap}"

    return result


def terminal_columns() -> int:
    """
    Returns the column width of the terminal. If this is not availble in the
    terminal environment variables then DEFAULT_TERMINAL_COLUMNS we be returned.
    """
    try:
        columns = os.get_terminal_size().columns or DEFAULT_TERMINAL_COLUMNS
    except OSError:
        columns = DEFAULT_TERMINAL_COLUMNS

    return columns


def output_line(line: Any) -> None:
    """
    Format a line of output for printing. Print should not be used elsewhere.
    Exception - clear_page would not function without terminal characters
    """
    line = str(line)
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    if LLEFState().use_color is False:
        line = ansi_escape.sub("", line)
    print(line)


def clear_page() -> None:
    """
    Used to clear the previously printed breakpoint information before
    printing the next information.
    """
    try:
        num_lines = os.get_terminal_size().lines
    except OSError:
        num_lines = DEFAULT_TERMINAL_LINES

    for _ in range(num_lines):
        print()
    print("\033[0;0H")  # Ansi escape code: Set cursor to 0,0 position
    print("\033[J")  # Ansi escape code: Clear contents from cursor to end of screen


def print_line_with_string(
    string: str,
    char: GLYPHS = GLYPHS.HORIZONTAL_LINE,
    line_color: str = TERM_COLORS.GREY.name,
    string_color: str = TERM_COLORS.BLUE.name,
    align: ALIGN = ALIGN.RIGHT,
) -> None:
    """
    Print a line with the provided @string padded with @char.

    :param string: The string to be embedded in the line.
    :param char: The character that the line consist of.
    :param line_color: The color setting to define the color of the line.
    :param string_color: The color setting to define the color of the embedded string.
    :align: Defines where the string will be embedded in the line.
    """
    width = terminal_columns()
    if align == ALIGN.RIGHT:
        l_pad = (width - len(string) - 6) * char.value
        r_pad = 4 * char.value

    elif align == ALIGN.CENTRE:
        l_pad = (width - len(string)) * char.value
        r_pad = 4 * char.value

    else:  # align == ALIGN.LEFT:
        l_pad = 4 * char.value
        r_pad = (width - len(string) - 6) * char.value

    line = color_string(l_pad, line_color)
    line += color_string(string, string_color, " ", " ")
    line += color_string(r_pad, line_color)

    output_line(line)


def print_line(char: GLYPHS = GLYPHS.HORIZONTAL_LINE, color: str = TERM_COLORS.GREY.name) -> None:
    """Print a line of @char"""
    output_line(color_string(terminal_columns() * char.value, color))


def print_message(msg_type: MSG_TYPE, message: str) -> None:
    """Format, color and print a @message based on its @msg_type."""
    info_color = TERM_COLORS.BLUE.name
    success_color = TERM_COLORS.GREEN.name
    error_color = TERM_COLORS.RED.name

    if msg_type == MSG_TYPE.INFO:
        output_line(color_string("[i] ", info_color, rwrap=message))
    elif msg_type == MSG_TYPE.SUCCESS:
        output_line(color_string("[+] ", success_color, rwrap=message))
    elif msg_type == MSG_TYPE.ERROR:
        output_line(color_string("[-] ", error_color, rwrap=message))
    else:
        raise KeyError(f"{msg_type} is an invalid MSG_TYPE.")


def print_instruction(
    instruction: SBInstruction,
    base: int,
    target: SBTarget,
    color_setting: str = TERM_COLORS.ENDC.name,
) -> None:
    """
    Print formatted @instruction extracted from SBInstruction object.

    :param instruction: The instruction object.
    :param base: The address base to calculate offsets from.
    :param target: The target executable.
    :param color_setting: The color that will be fetched from TERM_COLORS (i.e., TERM_COLORS[color_setting]).
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
    if comment != "":
        comment = f"; {comment}"
    line += f"{mnemonic:<10}{operands:<30}{comment}"

    output_line(color_string(line, color_setting))


def print_instructions(
    instructions: List[SBInstruction],
    base: int,
    target: SBTarget,
    color_setting: str = TERM_COLORS.ENDC.name,
) -> None:
    """
    Print formatted @instructions extracting information from the SBInstruction objects.

    :param instructions: A list of instruction objects.
    :param base: The address base to calculate offsets from.
    :param target: The target executable.
    :param color_setting: The color that will be fetched from TERM_COLORS (i.e., TERM_COLORS[color_setting]).
    """
    for instruction in instructions:
        print_instruction(instruction, base, target, color_setting)
