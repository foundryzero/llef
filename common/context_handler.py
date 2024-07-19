from typing import Dict, Type, Optional

from lldb import (
    SBAddress,
    SBDebugger,
    SBError,
    SBExecutionContext,
    SBFrame,
    SBProcess,
    SBTarget,
    SBThread,
    SBValue,
)

from arch import get_arch
from arch.base_arch import BaseArch, FlagRegister
from common.constants import GLYPHS, TERM_COLORS
from common.settings import LLEFSettings
from common.state import LLEFState
from common.util import (
    attempt_to_read_string_from_memory,
    clear_page,
    get_frame_arguments,
    get_registers,
    is_code,
    is_heap,
    is_stack,
    print_instruction,
    print_line,
    print_line_with_string,
)


class ContextHandler:
    """Context handler."""

    frame: SBFrame
    process: SBProcess
    target: SBTarget
    thread: SBThread
    arch: Type[BaseArch]
    debugger: SBDebugger
    exe_ctx: SBExecutionContext
    settings: LLEFSettings
    state: LLEFState

    def __init__(
        self,
        debugger: SBDebugger,
    ) -> None:
        """
        For up to date documentation on args provided to this function run: `help target stop-hook add`
        """
        self.debugger = debugger
        self.settings = LLEFSettings()
        self.state = LLEFState()

    def output_line(self, line: str) -> None:
        if self.settings.color_output is False:
            for term_color in TERM_COLORS:
                line = line.replace(term_color.value, "")
        print(line)

    def generate_printable_line_from_pointer(
        self, pointer: SBValue, address_containing_pointer: Optional[int] = None
    ) -> str:
        """
        Generate a line from a memory address (@pointer) that contains relevant
        information about the address.
        This is intended to be used when printing stack and register values.
        """

        line = ""
        pointer_value = SBAddress(pointer, self.target)

        if pointer_value.symbol.IsValid():
            offset = (
                pointer_value.offset - pointer_value.symbol.GetStartAddress().offset
            )
            line += (
                f" {GLYPHS.RIGHT_ARROW.value} {TERM_COLORS.GREY.value}"
                + f"<{pointer_value.symbol.name}+{offset}>{TERM_COLORS.ENDC.value}"
            )

        referenced_string = attempt_to_read_string_from_memory(
            self.process, pointer_value.GetLoadAddress(self.target)
        )

        if len(referenced_string) > 0 and referenced_string.isprintable():
            # Only add this to the line if there are any printable characters in refd_string
            referenced_string = referenced_string.replace("\n", " ")
            line += (
                f' {GLYPHS.RIGHT_ARROW.value} ("{TERM_COLORS.YELLOW.value}{referenced_string}'
                + f'{TERM_COLORS.ENDC.value}"?)'
            )

        if address_containing_pointer is not None:
            registers_pointing_to_address = []
            for register in get_registers(self.frame, self.arch().gpr_key):
                if register.GetValueAsUnsigned() == address_containing_pointer:
                    registers_pointing_to_address.append(f"${register.GetName()}")
            if len(registers_pointing_to_address) > 0:
                reg_list = ", ".join(registers_pointing_to_address)
                line += f" {TERM_COLORS.BLUE.value}{GLYPHS.LEFT_ARROW.value}{reg_list}"

        return line

    def print_stack_addr(self, addr: SBValue, offset: int) -> None:
        """Produce a printable line containing information about a given stack @addr and print it"""
        # Add stack address to line
        line = (
            f"{TERM_COLORS.CYAN.value}{hex(addr.GetValueAsUnsigned())}"
            + f"{TERM_COLORS.ENDC.value}{GLYPHS.VERTICAL_LINE.value}"
        )
        # Add offset to line
        line += f"+{offset:04x}: "

        # Add value to line
        err = SBError()
        stack_value = self.process.ReadPointerFromMemory(addr.GetValueAsUnsigned(), err)
        if err.Success():
            line += f"0x{stack_value:0{self.arch().bits // 4}x}"
        else:
            # Shouldn't happen as stack should always contain something
            line += str(err)

        line += self.generate_printable_line_from_pointer(
            stack_value, addr.GetValueAsUnsigned()
        )
        self.output_line(line)

    def print_register(self, register: SBValue) -> None:
        """Print details of a @register"""
        reg_name = register.GetName()
        reg_value = register.GetValueAsUnsigned()

        if self.state.prev_registers.get(reg_name) == register.GetValueAsUnsigned():
            # Register value as not changed
            highlight = TERM_COLORS.BLUE
        else:
            # Register value has changed so highlight
            highlight = TERM_COLORS.RED

        if is_code(reg_value, self.process, self.regions):
            color = TERM_COLORS.RED
        elif is_stack(reg_value, self.process, self.regions):
            color = TERM_COLORS.PINK
        elif is_heap(reg_value, self.process, self.regions):
            color = TERM_COLORS.GREEN
        else:
            color = TERM_COLORS.ENDC
        formatted_reg_value = f"{reg_value:x}".ljust(12)
        line = (
            f"{highlight.value}{reg_name.ljust(7)}{TERM_COLORS.ENDC.value}: "
            + f"{color.value}0x{formatted_reg_value}{TERM_COLORS.ENDC.value}"
        )

        line += self.generate_printable_line_from_pointer(reg_value)

        self.output_line(line)

    def print_flags_register(self, flag_register: FlagRegister) -> None:
        """Format and print the contents of the flag register."""
        flag_value = self.frame.register[flag_register.name].GetValueAsUnsigned()

        if self.state.prev_registers.get(flag_register.name) == flag_value:
            # No change
            highlight = TERM_COLORS.BLUE
        else:
            # Change and highlight
            highlight = TERM_COLORS.RED

        line = f"{highlight.value}{flag_register.name.ljust(7)}{TERM_COLORS.ENDC.value}: ["
        line += " ".join(
            [
                name.upper() if flag_value & bitmask else name
                for name, bitmask in flag_register.bit_masks.items()
            ]
        )
        line += "]"
        self.output_line(line)

    def update_registers(self) -> None:
        """This updates the cached registers, which are used to track which registered have changed."""

        for reg in get_registers(self.frame, self.arch().gpr_key):
            self.state.prev_registers[reg.GetName()] = reg.GetValueAsUnsigned()

    def print_legend(self) -> None:
        """Print a line containing the color legend"""

        self.output_line(
            f"[ Legend: "
            f"{TERM_COLORS.RED.value}Modified register{TERM_COLORS.ENDC.value} | "
            f"{TERM_COLORS.RED.value}Code{TERM_COLORS.ENDC.value} | "
            f"{TERM_COLORS.GREEN.value}Heap{TERM_COLORS.ENDC.value} | "
            f"{TERM_COLORS.PINK.value}Stack{TERM_COLORS.ENDC.value} | "
            f"{TERM_COLORS.YELLOW.value}String{TERM_COLORS.ENDC.value} ]"
        )

    def display_registers(self) -> None:
        """Print the registers display section"""

        print_line_with_string("registers")
        for reg in get_registers(self.frame, self.arch().gpr_key):
            if reg.GetName() in self.arch().gpr_registers:
                self.print_register(reg)
        for flag_register in self.arch.flag_registers:
            if self.frame.register[flag_register.name] is not None:
                self.print_flags_register(flag_register)

    def display_stack(self) -> None:
        """Print information about the contents of the top of the stack"""

        print_line_with_string("stack")
        for inc in range(0, self.arch().bits, 8):
            stack_pointer = self.frame.GetSP()
            addr = self.target.EvaluateExpression(f"{stack_pointer} + {inc}")
            self.print_stack_addr(addr, inc)

    def display_code(self) -> None:
        """
        Print the disassembly generated by LLDB.
        """
        print_line_with_string("code")

        if self.frame.disassembly:
            instructions = self.frame.disassembly.split("\n")

            current_pc = hex(self.frame.GetPC())
            for i, item in enumerate(instructions):
                if current_pc in item:
                    self.output_line(instructions[0])
                    if i > 3:
                        print_instruction(instructions[i - 3], TERM_COLORS.GREY)
                        print_instruction(instructions[i - 2], TERM_COLORS.GREY)
                        print_instruction(instructions[i - 1], TERM_COLORS.GREY)
                        print_instruction(item, TERM_COLORS.GREEN)
                        # This slice notation (and the 4 below) are a buggy interaction of black and pycodestyle
                        # See: https://github.com/psf/black/issues/157
                        # fmt: off
                        for instruction in instructions[i + 1:i + 6]:  # noqa
                            # fmt: on
                            print_instruction(instruction)
                    if i == 3:
                        print_instruction(instructions[i - 2], TERM_COLORS.GREY)
                        print_instruction(instructions[i - 1], TERM_COLORS.GREY)
                        print_instruction(item, TERM_COLORS.GREEN)
                        # fmt: off
                        for instruction in instructions[i + 1:10]:  # noqa
                            # fmt: on
                            print_instruction(instruction)
                    if i == 2:
                        print_instruction(instructions[i - 1], TERM_COLORS.GREY)
                        print_instruction(item, TERM_COLORS.GREEN)
                        # fmt: off
                        for instruction in instructions[i + 1:10]:  # noqa
                            # fmt: on
                            print_instruction(instruction)
                    if i == 1:
                        print_instruction(item, TERM_COLORS.GREEN)
                        # fmt: off
                        for instruction in instructions[i + 1:10]:  # noqa
                            # fmt: on
                            print_instruction(instruction)
        else:
            print("No disassembly to print")

    def display_threads(self) -> None:
        """Print LLDB formatted thread information"""
        print_line_with_string("threads")
        for thread in self.process:
            print(thread)

    def display_trace(self) -> None:
        """
        Prints the call stack including arguments if LLDB knows them.
        """
        print_line_with_string("trace")

        for i in range(self.thread.GetNumFrames()):
            number_color = TERM_COLORS.GREEN if i == 0 else TERM_COLORS.PINK
            line = f"[{number_color.value}#{i}{TERM_COLORS.ENDC.value}] "

            current_frame = self.thread.GetFrameAtIndex(i)
            pc_address = current_frame.GetPCAddress()
            func = current_frame.GetFunction()

            if func:
                line += (
                    f"{pc_address.GetLoadAddress(self.target):#x}  {GLYPHS.RIGHT_ARROW.value} "
                    + f"{TERM_COLORS.GREEN.value}{func.GetName()}{TERM_COLORS.ENDC.value}"
                )
            else:
                line += (
                    f"{pc_address.GetLoadAddress(self.target):#x}  {GLYPHS.RIGHT_ARROW.value} "
                    + f"{TERM_COLORS.GREEN.value}{current_frame.GetSymbol().GetName()}{TERM_COLORS.ENDC.value}"
                )

            line += get_frame_arguments(current_frame)

            self.output_line(line)

    def display_context(
        self,
        exe_ctx: SBExecutionContext,
    ) -> None:
        """For up to date documentation on args provided to this function run: `help target stop-hook add`"""

        # Refresh frame, process, target, and thread objects at each stop.
        self.frame = exe_ctx.GetFrame()
        self.process = exe_ctx.GetProcess()
        self.target = exe_ctx.GetTarget()
        self.thread = exe_ctx.GetThread()
        self.arch = get_arch(self.target)
        if self.settings.register_coloring is True:
            self.regions = self.process.GetMemoryRegions()
        else:
            self.regions = None

        # Hack to print cursor at the top of the screen
        clear_page()

        if self.settings.show_legend:
            self.print_legend()

        if self.settings.show_registers:
            self.display_registers()

        if self.settings.show_stack:
            self.display_stack()

        if self.settings.show_code:
            self.display_code()

        if self.settings.show_threads:
            self.display_threads()

        if self.settings.show_trace:
            self.display_trace()

        print_line()

        self.update_registers()
