"""Break point handler."""
from typing import Any, Dict, Optional, Type

from lldb import (
    SBAddress,
    SBDebugger,
    SBError,
    SBExecutionContext,
    SBFrame,
    SBProcess,
    SBStream,
    SBStructuredData,
    SBTarget,
    SBThread,
    SBValue,
)

from arch import get_arch
from arch.base_arch import BaseArch
from common.constants import GLYPHS, TERM_COLOURS
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


class StopHookHandler:
    """Stop Hook handler."""

    frame: SBFrame
    process: SBProcess
    target: SBTarget
    thread: SBThread
    arch: Type[BaseArch]

    old_registers: Dict[str, int] = {}

    @classmethod
    def lldb_self_register(cls, debugger: SBDebugger, module_name: str) -> None:
        """Register the Stop Hook Handler"""

        command = f"target stop-hook add -P {module_name}.{cls.__name__}"
        debugger.HandleCommand(command)

    def __init__(
        self, target: SBTarget, _: SBStructuredData, __: Dict[Any, Any]
    ) -> None:
        """
        This is probably where a global state object should be initiated. Current version only uses
        class scoped state (e.g. self.old_registers). The limitation of this is that `commands` can't
        interact with state.

        For up to date documentation on args provided to this function run: `help target stop-hook add`
        """
        self.target = target

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
                f" {GLYPHS.RIGHT_ARROW.value} {TERM_COLOURS.GREY.value}"
                + f"<{pointer_value.symbol.name}+{offset}>{TERM_COLOURS.ENDC.value}"
            )

        referenced_string = attempt_to_read_string_from_memory(
            self.process, pointer_value.GetLoadAddress(self.target)
        )

        if len(referenced_string) > 0 and referenced_string.isprintable():
            # Only add this to the line if there are any printable characters in refd_string
            referenced_string = referenced_string.replace("\n", " ")
            line += (
                f' {GLYPHS.RIGHT_ARROW.value} ("{TERM_COLOURS.YELLOW.value}{referenced_string}'
                + f'{TERM_COLOURS.ENDC.value}"?)'
            )

        if address_containing_pointer is not None:
            registers_pointing_to_address = []
            for register in get_registers(self.frame, self.arch().gpr_key):
                if register.GetValueAsUnsigned() == address_containing_pointer:
                    registers_pointing_to_address.append(f"${register.GetName()}")
            if len(registers_pointing_to_address) > 0:
                reg_list = ", ".join(registers_pointing_to_address)
                line += f" {TERM_COLOURS.BLUE.value}{GLYPHS.LEFT_ARROW.value}{reg_list}"

        return line

    def print_stack_addr(self, addr: SBValue, offset: int) -> None:
        """Produce a printable line containing information about a given stack @addr and print it"""
        # Add stack address to line
        line = (
            f"{TERM_COLOURS.CYAN.value}{hex(addr.GetValueAsUnsigned())}"
            + f"{TERM_COLOURS.ENDC.value}{GLYPHS.VERTICAL_LINE.value}"
        )
        # Add offset to line
        line += f"+{offset:04x}: "

        # Add value to line
        err = SBError()
        stack_value = self.process.ReadPointerFromMemory(addr.GetValueAsUnsigned(), err)
        if err.Success():
            line += f"0x{stack_value:015x}"
        else:
            # Shouldn't happen as stack should always contain something
            line += str(err)

        line += self.generate_printable_line_from_pointer(
            stack_value, addr.GetValueAsUnsigned()
        )
        print(line)

    def print_register(self, register: SBValue) -> None:
        """Print details of a @register"""
        reg_name = register.GetName()
        reg_value = register.GetValueAsUnsigned()

        if self.old_registers.get(reg_name) == register.GetValueAsUnsigned():
            # Register value as not changed
            highlight = TERM_COLOURS.BLUE
        else:
            # Register value has changed so highlight
            highlight = TERM_COLOURS.RED

        if is_code(reg_value, self.process, self.regions):
            color = TERM_COLOURS.RED
        elif is_stack(reg_value, self.process, self.regions):
            color = TERM_COLOURS.PINK
        elif is_heap(reg_value, self.process, self.regions):
            color = TERM_COLOURS.GREEN
        else:
            color = TERM_COLOURS.ENDC
        formatted_reg_value = f"{reg_value:x}".ljust(12)
        line = (
            f"{highlight.value}{reg_name.ljust(7)}{TERM_COLOURS.ENDC.value}: "
            + f"{color.value}0x{formatted_reg_value}{TERM_COLOURS.ENDC.value}"
        )

        line += self.generate_printable_line_from_pointer(reg_value)

        print(line)

    def print_flags_register(self, flag_register: SBValue) -> None:
        """Format and print the contents of the flag register."""

        if (
            self.old_registers.get(self.arch().flag_register)
            == flag_register.GetValueAsUnsigned()
        ):
            # No change
            highlight = TERM_COLOURS.BLUE
        else:
            # Change and highlight
            highlight = TERM_COLOURS.RED

        flag_value = flag_register.GetValueAsUnsigned()
        line = f"{highlight.value}{flag_register.GetName().ljust(7)}{TERM_COLOURS.ENDC.value}: ["
        line += " ".join(
            [
                name.upper() if flag_value & bitmask else name
                for name, bitmask in self.arch().flag_register_bit_masks.items()
            ]
        )
        line += "]"
        print(line)

    def update_registers(self) -> None:
        """This updates the cached registers, which are used to track which registered have changed."""

        for reg in get_registers(self.frame, self.arch().gpr_key):
            self.old_registers[reg.GetName()] = reg.GetValueAsUnsigned()

    def print_legend(self) -> None:
        """Print a line containing the color legend"""

        print(
            f"[ Legend: "
            f"{TERM_COLOURS.RED.value}Modified register{TERM_COLOURS.ENDC.value} | "
            f"{TERM_COLOURS.RED.value}Code{TERM_COLOURS.ENDC.value} | "
            f"{TERM_COLOURS.GREEN.value}Heap{TERM_COLOURS.ENDC.value} | "
            f"{TERM_COLOURS.PINK.value}Stack{TERM_COLOURS.ENDC.value} | "
            f"{TERM_COLOURS.YELLOW.value}String{TERM_COLOURS.ENDC.value} ]"
        )

    def display_registers(self) -> None:
        """Print the registers display section"""

        print_line_with_string("registers")
        for reg in get_registers(self.frame, self.arch().gpr_key):
            if reg.GetName() in self.arch().gpr_registers:
                self.print_register(reg)
        self.print_flags_register(self.frame.register[self.arch.flag_register])

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

            for i, item in enumerate(instructions):
                if "\x1b[33m-> \x1b[0m" in item:
                    print(instructions[0])
                    if i > 3:
                        print_instruction(instructions[i - 3], TERM_COLOURS.GREY)
                        print_instruction(instructions[i - 2], TERM_COLOURS.GREY)
                        print_instruction(instructions[i - 1], TERM_COLOURS.GREY)
                        print_instruction(item, TERM_COLOURS.GREEN)
                        # This slice notation (and the 4 below) are a buggy interaction of black and pycodestyle
                        # See: https://github.com/psf/black/issues/157
                        # fmt: off
                        for instruction in instructions[i + 1:10]:  # noqa
                            # fmt: on
                            print_instruction(instruction)
                    if i == 3:
                        print_instruction(instructions[i - 2], TERM_COLOURS.GREY)
                        print_instruction(instructions[i - 1], TERM_COLOURS.GREY)
                        print_instruction(item, TERM_COLOURS.GREEN)
                        # fmt: off
                        for instruction in instructions[i + 1:10]:  # noqa
                            # fmt: on
                            print_instruction(instruction)
                    if i == 2:
                        print_instruction(instructions[i - 1], TERM_COLOURS.GREY)
                        print_instruction(item, TERM_COLOURS.GREEN)
                        # fmt: off
                        for instruction in instructions[i + 1:10]:  # noqa
                            # fmt: on
                            print_instruction(instruction)
                    if i == 1:
                        print_instruction(item, TERM_COLOURS.GREEN)
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
            number_colour = TERM_COLOURS.GREEN if i == 0 else TERM_COLOURS.PINK
            line = f"[{number_colour.value}#{i}{TERM_COLOURS.ENDC.value}] "

            current_frame = self.thread.GetFrameAtIndex(i)
            pc_address = current_frame.GetPCAddress()
            func = current_frame.GetFunction()

            if func:
                line += (
                    f"{pc_address.GetLoadAddress(self.target):#x}  {GLYPHS.RIGHT_ARROW.value} "
                    + f"{TERM_COLOURS.GREEN.value}{func.GetName()}{TERM_COLOURS.ENDC.value}"
                )
            else:
                line += (
                    f"{pc_address.GetLoadAddress(self.target):#x}  {GLYPHS.RIGHT_ARROW.value} "
                    + f"{TERM_COLOURS.GREEN.value}{current_frame.GetSymbol().GetName()}{TERM_COLOURS.ENDC.value}"
                )

            line += get_frame_arguments(current_frame)

            print(line)

    def handle_stop(self, exe_ctx: SBExecutionContext, _: SBStream) -> None:
        """For up to date documentation on args provided to this function run: `help target stop-hook add`"""

        # Refresh frame, process, target, and thread objects at each stop.
        self.frame = exe_ctx.GetFrame()
        self.process = exe_ctx.GetProcess()
        self.target = exe_ctx.GetTarget()
        self.thread = exe_ctx.GetThread()
        self.arch = get_arch(self.target)
        self.regions = self.process.GetMemoryRegions()

        # Hack to print cursor at the top of the screen
        clear_page()

        self.print_legend()

        self.display_registers()

        self.display_stack()

        self.display_code()

        self.display_threads()

        self.display_trace()

        print_line()

        self.update_registers()
