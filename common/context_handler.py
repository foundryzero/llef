import os
from string import printable
from typing import List, Optional, Tuple, Type

from lldb import (
    SBAddress,
    SBCommandReturnObject,
    SBDebugger,
    SBError,
    SBExecutionContext,
    SBFrame,
    SBMemoryRegionInfo,
    SBProcess,
    SBTarget,
    SBThread,
    SBValue,
)

from arch import get_arch, get_arch_from_str
from arch.base_arch import BaseArch, FlagRegister
from common.color_settings import LLEFColorSettings
from common.constants import GLYPHS, TERM_COLORS
from common.instruction_util import extract_instructions, print_instruction, print_instructions
from common.output_util import clear_page, color_string, output_line, print_line, print_line_with_string
from common.settings import LLEFSettings
from common.state import LLEFState
from common.util import (
    address_to_filename,
    attempt_to_read_string_from_memory,
    find_darwin_heap_regions,
    find_stack_regions,
    get_frame_arguments,
    get_frame_range,
    get_registers,
    is_code,
    is_heap,
    is_stack,
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
    color_settings: LLEFColorSettings
    state: LLEFState
    darwin_stack_regions: List[SBMemoryRegionInfo]
    darwin_heap_regions: List[Tuple[int, int]]

    def __init__(
        self,
        debugger: SBDebugger,
    ) -> None:
        """
        For up to date documentation on args provided to this function run: `help target stop-hook add`
        """
        self.debugger = debugger
        self.settings = LLEFSettings(debugger)
        self.color_settings = LLEFColorSettings()
        self.state = LLEFState()
        self.state.change_use_color(self.settings.color_output)
        self.darwin_stack_regions = None
        self.darwin_heap_regions = None

    def generate_rebased_address_string(self, address: SBAddress) -> str:
        module = address.GetModule()

        if module is not None and self.settings.rebase_addresses is True:
            file_name = os.path.basename(str(module.file))
            rebased_address = address.GetFileAddress() + self.settings.rebase_offset
            return color_string(f"({file_name} {rebased_address:#x})", self.color_settings.rebased_address_color)

        return ""

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
            offset = pointer_value.offset - pointer_value.symbol.GetStartAddress().offset
            line += f" {self.generate_rebased_address_string(pointer_value)} {GLYPHS.RIGHT_ARROW.value}"
            line += color_string(
                f"<{pointer_value.symbol.name}+{offset}>", self.color_settings.dereferenced_value_color
            )

        referenced_string = attempt_to_read_string_from_memory(self.process, pointer_value.GetLoadAddress(self.target))

        if len(referenced_string) > 0 and referenced_string.isprintable():
            # Only add this to the line if there are any printable characters in refd_string
            referenced_string = referenced_string.replace("\n", " ")
            line += color_string(
                referenced_string, self.color_settings.string_color, f' {GLYPHS.RIGHT_ARROW.value} ("', "?)"
            )

        if address_containing_pointer is not None:
            registers_pointing_to_address = []
            for register in get_registers(self.frame, self.arch().gpr_key):
                if register.GetValueAsUnsigned() == address_containing_pointer:
                    registers_pointing_to_address.append(f"${register.GetName()}")
            if len(registers_pointing_to_address) > 0:
                reg_list = ", ".join(registers_pointing_to_address)
                line += color_string(
                    f"{GLYPHS.LEFT_ARROW.value}{reg_list}", self.color_settings.dereferenced_register_color
                )

        return line

    def print_stack_addr(self, addr: SBValue, offset: int) -> None:
        """Produce a printable line containing information about a given stack @addr and print it"""
        # Add stack address and offset to line

        line = color_string(
            hex(addr.GetValueAsUnsigned()),
            self.color_settings.stack_address_color,
            rwrap=f"{GLYPHS.VERTICAL_LINE.value}+{offset:04x}: ",
        )

        # Add value to line
        err = SBError()
        stack_value = self.process.ReadPointerFromMemory(addr.GetValueAsUnsigned(), err)
        if err.Success():
            line += f"0x{stack_value:0{self.arch().bits // 4}x}"
        else:
            # Shouldn't happen as stack should always contain something
            line += str(err)

        line += self.generate_printable_line_from_pointer(stack_value, addr.GetValueAsUnsigned())
        output_line(line)

    def print_memory_address(self, addr: int, offset: int, size: int) -> None:
        """Print a line containing information about @size bytes at @addr displaying @offset"""
        # Add address and offset to line
        line = color_string(
            hex(addr),
            self.color_settings.read_memory_address_color,
            rwrap=f"{GLYPHS.VERTICAL_LINE.value}+{offset:04x}: ",
        )

        # Add value to line
        err = SBError()
        memory_value = self.process.ReadMemory(addr, size, err)

        if err.Success():
            line += f"0x{int.from_bytes(memory_value, 'little'):0{size * 2}x}"
        else:
            line += str(err)

        output_line(line)

    def print_bytes(self, addr: int, size: int) -> None:
        """Print a line containing information about @size individual bytes at @addr"""
        if size > 0:
            # Add address to line
            line = color_string(hex(addr), self.color_settings.read_memory_address_color, "", "\t")

            # Add value to line
            err = SBError()
            memory_value: bytes = self.process.ReadMemory(addr, size, err)
            if err.Success():
                line += f"{memory_value.hex(' '):47}    "

                # Add characters to line
                characters = ""
                for byte in memory_value:
                    if chr(byte) in printable.strip():
                        characters += chr(byte)
                    else:
                        characters += "."

                line += characters
            else:
                line += str(err)

            output_line(line)

    def print_register(self, register: SBValue) -> None:
        """Print details of a @register"""
        reg_name = register.GetName()
        reg_value = register.GetValueAsUnsigned()

        if self.state.prev_registers.get(reg_name) == register.GetValueAsUnsigned():
            # Register value as not changed
            highlight = self.color_settings.register_color
        else:
            # Register value has changed so highlight
            highlight = self.color_settings.modified_register_color

        if is_code(reg_value, self.process, self.target, self.regions):
            color = self.color_settings.code_color
        elif is_stack(reg_value, self.regions, self.darwin_stack_regions):
            color = self.color_settings.stack_color
        elif is_heap(reg_value, self.target, self.regions, self.darwin_stack_regions, self.darwin_heap_regions):
            color = self.color_settings.heap_color
        else:
            color = None
        formatted_reg_value = f"{reg_value:x}".ljust(12)
        line = color_string(reg_name.ljust(7), highlight, "", ": ")
        line += color_string(f"0x{formatted_reg_value}", color)

        line += self.generate_printable_line_from_pointer(reg_value)

        output_line(line)

    def print_flags_register(self, flag_register: FlagRegister) -> None:
        """Format and print the contents of the flag register."""
        flag_value = self.frame.register[flag_register.name].GetValueAsUnsigned()

        if self.state.prev_registers.get(flag_register.name) == flag_value:
            # No change
            highlight = self.color_settings.register_color
        else:
            # Change and highlight
            highlight = self.color_settings.modified_register_color

        flags = " ".join(
            [name.upper() if flag_value & bitmask else name for name, bitmask in flag_register.bit_masks.items()]
        )
        line = color_string(flag_register.name.ljust(7), highlight, rwrap=f": [{flags}]")
        output_line(line)

    def update_registers(self) -> None:
        """
        This updates the cached registers, which are used to track which registered have changed.
        If there is no frame currently then the previous registers do not change
        """
        self.state.prev_registers = self.state.current_registers.copy()
        if self.frame is not None:
            for reg_set in self.frame.registers:
                for reg in reg_set:
                    self.state.current_registers[reg.GetName()] = reg.GetValueAsUnsigned()

    def print_legend(self) -> None:
        """Print a line containing the color legend"""

        legend = "[ Legend: "
        legend += color_string("Modified register", self.color_settings.modified_register_color, rwrap=" | ")
        legend += color_string("Code", self.color_settings.code_color, rwrap=" | ")

        # Only set when platform is Darwin (iOS, MacOS, etc) and darwin heap scan is enabled in settings.
        if self.darwin_heap_regions is not None:
            legend += color_string("Heap (Darwin heap scan)", self.color_settings.heap_color, rwrap=" | ")
        else:
            legend += color_string("Heap", self.color_settings.heap_color, rwrap=" | ")

        legend += color_string("Stack", self.color_settings.stack_color, rwrap=" | ")
        legend += color_string("String", self.color_settings.string_color, rwrap=" ]")
        output_line(legend)

    def display_registers(self) -> None:
        """Print the registers display section"""

        print_line_with_string(
            "registers",
            line_color=self.color_settings.line_color,
            string_color=self.color_settings.section_header_color,
        )

        if self.settings.show_all_registers:
            register_list = []
            for reg_set in self.frame.registers:
                for reg in reg_set:
                    register_list.append(reg.name)
            for reg in self.arch.flag_registers:
                if reg.name in register_list:
                    register_list.remove(reg.name)
        else:
            register_list = self.arch().gpr_registers

        for reg in register_list:
            if self.frame.register[reg] is not None:
                self.print_register(self.frame.register[reg])
        for flag_register in self.arch.flag_registers:
            if self.frame.register[flag_register.name] is not None:
                self.print_flags_register(flag_register)

    def display_stack(self) -> None:
        """Print information about the contents of the top of the stack"""

        print_line_with_string(
            "stack",
            line_color=self.color_settings.line_color,
            string_color=self.color_settings.section_header_color,
        )
        for inc in range(0, self.arch().bits, 8):
            stack_pointer = self.frame.GetSP()
            addr = self.target.EvaluateExpression(f"{stack_pointer} + {inc}")
            self.print_stack_addr(addr, inc)

    def display_code(self) -> None:
        """
        Print the disassembly generated by LLDB.
        """
        print_line_with_string(
            "code",
            line_color=self.color_settings.line_color,
            string_color=self.color_settings.section_header_color,
        )

        pc = self.frame.GetPC()

        filename = address_to_filename(self.target, pc)
        function_name = self.frame.GetFunctionName()
        output_line(f"{filename}'{function_name}:")

        frame_start_address, frame_end_address = get_frame_range(self.frame, self.target)

        pre_instructions = extract_instructions(self.target, frame_start_address, pc - 1, self.state.disassembly_syntax)
        print_instructions(
            self.target,
            pre_instructions[-3:],
            frame_start_address,
            self.color_settings,
        )

        post_instructions = extract_instructions(self.target, pc, frame_end_address, self.state.disassembly_syntax)

        if len(post_instructions) > 0:
            pc_instruction = post_instructions[0]
            print_instruction(
                self.target,
                pc_instruction,
                frame_start_address,
                self.color_settings,
                True,
            )

            limit = 9 - min(len(pre_instructions), 3)
            print_instructions(
                self.target,
                post_instructions[1:limit],
                frame_start_address,
                self.color_settings,
            )

    def display_threads(self) -> None:
        """Print LLDB formatted thread information"""
        print_line_with_string(
            "threads",
            line_color=self.color_settings.line_color,
            string_color=self.color_settings.section_header_color,
        )
        for thread in self.process:
            output_line(thread)

    def display_trace(self) -> None:
        """
        Prints the call stack including arguments if LLDB knows them.
        """
        print_line_with_string(
            "trace",
            line_color=self.color_settings.line_color,
            string_color=self.color_settings.section_header_color,
        )

        for i in range(self.thread.GetNumFrames()):
            if i == 0:
                number_color = self.color_settings.highlighted_index_color
            else:
                number_color = self.color_settings.index_color
            line = color_string(f"#{i}", number_color, "[", "]")

            current_frame = self.thread.GetFrameAtIndex(i)
            pc_address = current_frame.GetPCAddress()
            func = current_frame.GetFunction()
            trace_address = pc_address.GetLoadAddress(self.target)

            if func:
                line += (
                    f"{trace_address:#x}{self.generate_rebased_address_string(pc_address)}  {GLYPHS.RIGHT_ARROW.value} "
                    f"{color_string(func.GetName(), self.color_settings.function_name_color)}"
                )
            else:
                line += (
                    f"{trace_address:#x}{self.generate_rebased_address_string(pc_address)}  {GLYPHS.RIGHT_ARROW.value} "
                    f"{color_string(current_frame.GetSymbol().GetName(), self.color_settings.function_name_color)}"
                )

            line += get_frame_arguments(
                current_frame, frame_argument_name_color=TERM_COLORS[self.color_settings.frame_argument_name_color]
            )

            output_line(line)

    def load_disassembly_syntax(self, debugger: SBDebugger) -> None:
        """Load the disassembly flavour from LLDB into LLEF's state."""
        self.state.disassembly_syntax = "default"
        if LLEFState.version >= [16]:
            self.state.disassembly_syntax = debugger.GetSetting("target.x86-disassembly-flavor").GetStringValue(100)

        if self.state.disassembly_syntax == "":
            command_interpreter = debugger.GetCommandInterpreter()
            result = SBCommandReturnObject()
            command_interpreter.HandleCommand("settings show target.x86-disassembly-flavor", result)
            if result.Succeeded():
                self.state.disassembly_syntax = result.GetOutput().split("=")[1][1:].replace("\n", "")

        if self.state.disassembly_syntax == "":
            self.state.disassembly_syntax = "default"

    def refresh(self, exe_ctx: SBExecutionContext) -> None:
        """Refresh stored values"""
        self.process = exe_ctx.GetProcess()
        self.target = exe_ctx.GetTarget()
        self.thread = exe_ctx.GetThread()
        self.frame = self.thread.GetFrameAtIndex(0)
        if self.settings.force_arch is not None:
            self.arch = get_arch_from_str(self.settings.force_arch)
        else:
            self.arch = get_arch(self.target)

        if self.settings.register_coloring is True:
            self.regions = self.process.GetMemoryRegions()
        else:
            self.regions = None

        if self.state.disassembly_syntax == "":
            self.load_disassembly_syntax(self.debugger)

        if LLEFState.platform == "Darwin":
            self.darwin_stack_regions = find_stack_regions(self.process)
            if self.settings.enable_darwin_heap_scan:
                self.darwin_heap_regions = find_darwin_heap_regions(self.process)
            else:
                # Setting darwin_heap_regions to None will cause the fallback heap
                # scanning method to be used.
                self.darwin_heap_regions = None

    def display_context(self, exe_ctx: SBExecutionContext, update_registers: bool) -> None:
        """For up to date documentation on args provided to this function run: `help target stop-hook add`"""

        # Refresh frame, process, target, and thread objects at each stop.
        self.refresh(exe_ctx)

        # Update current and previous registers
        if update_registers:
            self.update_registers()

        # Hack to print cursor at the top of the screen
        if self.debugger.GetUseColor():
            clear_page()

        if self.settings.show_legend:
            self.print_legend()

        for section in self.settings.output_order.split(","):
            if section == "registers" and self.settings.show_registers:
                self.display_registers()
            elif section == "stack" and self.settings.show_stack:
                self.display_stack()
            elif section == "code" and self.settings.show_code:
                self.display_code()
            elif section == "threads" and self.settings.show_threads:
                self.display_threads()
            elif section == "trace" and self.settings.show_trace:
                self.display_trace()

        print_line(color=self.color_settings.line_color)
