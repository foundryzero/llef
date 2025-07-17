"""Class for extracting information from a Go pclntab section."""

import itertools
from collections.abc import Callable, Iterator
from typing import Any, Union

from lldb import SBData, SBError, SBProcess, SBTarget

from common.golang.constants import GO_MAGIC_2_TO_15, GO_MAGIC_16_TO_17, GO_MAGIC_18_TO_19, GO_MAGIC_20_TO_24
from common.golang.interfaces import GoFunc, PCLnTabInfo
from common.golang.util_stateless import file_to_load_address, read_varint


class PCLnTabParser:
    """
    Stores information retrieved from the pclntab header and parses further data.
    """

    # Extracted from the binary:
    base: int
    magic: int
    pad: int
    min_instr_size: int
    ptr_size: int
    num_funcs: int
    num_files: int  # unset in Go < 1.16
    text_start: int  # unset in Go < 1.18
    func_name_off: int  # unset in Go < 1.16
    cu_off: int  # unset in Go < 1.16
    file_off: int  # unset in Go < 1.16
    pc_off: int  # unset in Go < 1.16
    pc_ln_off: int

    # Helper properties:

    valid: bool

    __make_func_map: Callable[[SBProcess, SBTarget, SBData], bool]
    """
    Parses the map from function entry addresses to human-readable names.

    :param SBProcess proc: The process object currently being debugged.
    :param SBData buf: The data buffer holding the section associated with gopclntab.
    :return int: Returns True if the parsing succeeded.
    """

    __read_header: Callable[[list[int]], None]
    """
    Set up internal state from the PCLNTAB header.

    :param list[int] reader: List of pointer-sized integers read after the first 8 bytes of the PCLNTAB.
    """

    __get_int_reader: Callable[[SBData], Any]
    """
    Return an appropriate reader for ints of size self.ptr_size bytes.

    :return Any: An array-like object allowing indexed access to the integers.
    """

    __unnamed_ctr: Iterator[int]

    # State to be returned after parsing:
    max_pc_file: int
    func_mapping: list[tuple[int, GoFunc]]
    version_bounds: tuple[int, int]

    def __init__(self, base: int, magic: int, pad: int, min_instr_size: int, ptr_size: int) -> None:
        # Assumes a little-endian format, since LLEF only supports LE architectures for now.
        self.base = base
        self.magic = magic
        self.pad = pad
        self.min_instr_size = min_instr_size
        self.ptr_size = ptr_size

        self.__unnamed_ctr = itertools.count()

        self.valid = self.pad == 0 and self.min_instr_size in (1, 2, 4) and self.ptr_size in (4, 8)
        self.func_mapping = []

        # Go ints are the same width as pointers
        if self.ptr_size == 4:
            self.__get_int_reader = lambda buf: buf.uint32
        else:
            self.__get_int_reader = lambda buf: buf.uint64

        if self.magic == GO_MAGIC_20_TO_24:
            self.__read_header = self.read_header_18to24
            self.__make_func_map = self.make_func_map_18to24
            self.version_bounds = (20, 24)
        elif self.magic == GO_MAGIC_18_TO_19:
            self.__read_header = self.read_header_18to24
            self.__make_func_map = self.make_func_map_18to24
            self.version_bounds = (18, 19)
        elif self.magic == GO_MAGIC_16_TO_17:
            self.__read_header = self.read_header_16to17
            self.__make_func_map = self.make_func_map_16to17
            self.version_bounds = (16, 17)
        elif self.magic == GO_MAGIC_2_TO_15:
            self.__read_header = self.read_header_2to15
            self.__make_func_map = self.make_func_map_2to15
            self.version_bounds = (2, 15)
        else:
            self.valid = False

    def make_stackmap(self, target: SBTarget, bytebuf: Any, offset: int, entry: int) -> list[tuple[int, int]]:
        """Parses the zig-zag, varint-encoded data relating PC offsets and SP deltas for a given function.

        :param SBTarget target: The target associated with the process. Used for resolving file->load addresses.
        :param Any bytebuf: An array-like object allowing indexed access to bytes.
        :param int offset: The address offset into the byte buffer to start reading from.
        :param int entry: The first address containing code for the target function.
        :return list[tuple[int, int]]: A list of pairs of program counter followed by stack pointer delta.
        """
        pc = file_to_load_address(target, entry)
        spdelta = -1
        pairs = []
        while True:
            vdelta, offset = read_varint(bytebuf, offset)
            if vdelta == 0 and pc > entry:
                break

            # vdelta is zig-zag encoded.
            if vdelta & 1 != 0:
                vdelta = -((vdelta + 1) >> 1)
            else:
                vdelta >>= 1

            pcdelta, offset = read_varint(bytebuf, offset)
            spdelta += vdelta
            pairs.append((pc, spdelta))
            pc += pcdelta * self.min_instr_size

        return pairs

    def add_func(
        self, proc: SBProcess, target: SBTarget, entry: int, nameptr: int, stack_deltas: list[tuple[int, int]]
    ) -> None:
        """
        Add a single GoFunc entry to state by reading a string from memory.

        :param SBProcess proc: The process object currently being debugged.
        :param SBTarget target: The target associated with the process. Used for resolving file->load addresses.
        :param int entry: The file address for the entrypoint of the function we wish to add.
        :param int nameptr: A pointer to the string in memory, to use as the function name.
        :param list[tuple[int, int]] stack_deltas: The list of stack deltas to pass to the GoFunc.
        """
        err = SBError()
        name = proc.ReadCStringFromMemory(nameptr, 256, err)
        if err.Fail():
            name = f"Unnamed_{next(self.__unnamed_ctr)}"

        record = GoFunc(name=name, file_addr=entry, stack_deltas=stack_deltas)

        mem_entry = file_to_load_address(target, entry)
        self.func_mapping.append((mem_entry, record))

    def make_func_map_18to24(self, proc: SBProcess, target: SBTarget, buf: SBData) -> bool:
        """
        Parses the map from function entry addresses to GoFunc structures for 1.18 <= Go <= 1.24.

        :param SBProcess proc: The process object currently being debugged.
        :param SBTarget target: The target associated with the process. Used for resolving file->load addresses.
        :param SBData buf: The data buffer holding the section associated with gopclntab.
        :return bool: Returns True if the parsing succeeded.
        """
        funcname_tab_addr = self.base + self.func_name_off

        # set up to read uint32s
        start = self.pc_ln_off // 4
        if start * 4 != self.pc_ln_off:
            # we must be 4-byte aligned
            return False

        pairs: list[int] = buf.uint32[start : start + 1 + self.num_funcs * 2]
        for func_i in range(self.num_funcs):
            func_entry = self.text_start + pairs[2 * func_i]
            funcinfo = (self.pc_ln_off + pairs[2 * func_i + 1] + 4) // 4
            [name_offset, _, _, pcsp] = buf.uint32[funcinfo : funcinfo + 4]
            stackmap = self.make_stackmap(target, buf.uint8, self.pc_off + pcsp, func_entry)
            self.add_func(proc, target, func_entry, funcname_tab_addr + name_offset, stackmap)

        self.max_pc_file = self.text_start + pairs[2 * self.num_funcs]
        return True

    def make_func_map_16to17(self, proc: SBProcess, target: SBTarget, buf: SBData) -> bool:
        """
        Parses the map from function entry addresses to GoFunc structures for 1.16 <= Go < 1.18.

        :param SBProcess proc: The process object currently being debugged.
        :param SBTarget target: The target associated with the process. Used for resolving file->load addresses.
        :param SBData buf: The data buffer holding the section associated with gopclntab.
        :return bool: Returns True if the parsing succeeded.
        """
        funcname_tab_addr = self.base + self.func_name_off

        # entries are pairs of pointer-sized numbers.
        start = self.pc_ln_off // self.ptr_size
        if start * self.ptr_size != self.pc_ln_off:
            # we must be aligned
            return False

        pairs: list[int] = self.__get_int_reader(buf)[start : start + 1 + self.num_funcs * 2]
        for func_i in range(self.num_funcs):
            func_entry = pairs[2 * func_i]
            funcinfo = (self.pc_ln_off + pairs[2 * func_i + 1] + self.ptr_size) // 4
            [name_offset, _, _, pcsp] = buf.uint32[funcinfo : funcinfo + 4]
            stackmap = self.make_stackmap(target, buf.uint8, self.pc_off + pcsp, func_entry)
            self.add_func(proc, target, func_entry, funcname_tab_addr + name_offset, stackmap)

        self.max_pc_file = pairs[2 * self.num_funcs]
        return True

    def make_func_map_2to15(self, proc: SBProcess, target: SBTarget, buf: SBData) -> bool:
        """
        Parses the map from function entry addresses to GoFunc structures for 1.2 <= Go < 1.16.

        :param SBProcess proc: The process object currently being debugged.
        :param SBTarget target: The target associated with the process. Used for resolving file->load addresses.
        :param SBData buf: The data buffer holding the section associated with gopclntab.
        :return bool: Returns True if the parsing succeeded.
        """

        # entries are pairs of pointer-sized numbers.
        start = self.pc_ln_off // self.ptr_size
        if start * self.ptr_size != self.pc_ln_off:
            # we must be aligned
            return False

        pairs: list[int] = self.__get_int_reader(buf)[start : start + 1 + self.num_funcs * 2]
        for func_i in range(self.num_funcs):
            func_entry = pairs[2 * func_i]
            funcinfo = (pairs[2 * func_i + 1] + self.ptr_size) // 4
            [name_offset, _, _, pcsp] = buf.uint32[funcinfo : funcinfo + 4]
            stackmap = self.make_stackmap(target, buf.uint8, pcsp, func_entry)
            self.add_func(proc, target, func_entry, self.base + name_offset, stackmap)

        self.max_pc_file = pairs[2 * self.num_funcs]
        return True

    def read_header_18to24(self, reader: list[int]) -> None:
        """
        Set up internal state from the PCLNTAB header for 1.18 <= Go <= 1.24.

        :param list[int] reader: List of pointer-sized integers read after the first 8 bytes of the PCLNTAB.
        """
        [
            self.num_funcs,
            self.num_files,
            self.text_start,
            self.func_name_off,
            self.cu_off,
            self.file_off,
            self.pc_off,
            self.pc_ln_off,
            *_,
        ] = reader

    def read_header_16to17(self, reader: list[int]) -> None:
        """
        Set up internal state from the PCLNTAB header for 1.16 <= Go < 1.24.

        :param list[int] reader: List of pointer-sized integers read after the first 8 bytes of the PCLNTAB.
        """
        [
            self.num_funcs,
            self.num_files,
            self.func_name_off,
            self.cu_off,
            self.file_off,
            self.pc_off,
            self.pc_ln_off,
            *_,
        ] = reader

    def read_header_2to15(self, reader: list[int]) -> None:
        """
        Set up internal state from the PCLNTAB header for 1.2 <= Go < 1.16.

        :param list[int] reader: List of pointer-sized integers read after the first 8 bytes of the PCLNTAB.
        """
        self.num_funcs = reader[0]
        self.pc_ln_off = 8 + self.ptr_size

    def differentiate_versions(self) -> tuple[int, int]:
        """
        Uses the list of function names from the PCLNTAB to more finely differentiate between Go versions.
        This analysis is used in ModuleData parsing, where the internal layout changes more frequently.

        :return tuple[int, int]: Tighter version bounds.
        """
        func_names = list(map(lambda x: x[1].name, self.func_mapping))
        new_bounds = self.version_bounds
        # We search for internal functions that are always included (architecture-independent). i.e. core runtime funcs.

        if self.version_bounds == (20, 24):
            # The 1.24 update removed runtime.evacuate as part of the old map implementation by default.
            # However, a user could still compile with the old map implementation turned on. So we don't have an "else".
            if "runtime.evacuate" not in func_names:
                new_bounds = (24, 24)

        elif self.version_bounds == (18, 19):
            # The 1.19 update renamed runtime.findrunnable to runtime.findRunnable.
            if "runtime.findrunnable" in func_names:
                new_bounds = (18, 18)
            elif "runtime.findRunnable" in func_names:
                new_bounds = (19, 19)

        elif self.version_bounds == (16, 17):
            # The 1.17 update renamed runtime.freespecial to runtime.freeSpecial.
            if "runtime.freespecial" in func_names:
                new_bounds = (16, 16)
            elif "runtime.freeSpecial" in func_names:
                new_bounds = (17, 17)

        elif self.version_bounds == (2, 15):
            # The 1.8 update added the function runtime.modulesinit.
            if "runtime.modulesinit" in func_names:
                # We are 1.8-1.15 inclusive.
                # The 1.9 update removed the function runtime.lfstackpush (replacing with runtime.(*lfstack).push)
                if "runtime.lfstackpush" in func_names:
                    new_bounds = (8, 8)
                else:
                    new_bounds = (9, 15)

            else:
                # We are 1.2-1.7 inclusive.
                # The 1.7 update added the function runtime.typelinksinit.
                if "runtime.typelinksinit" in func_names:
                    new_bounds = (7, 7)
                else:
                    new_bounds = (2, 6)
        return new_bounds

    def parse(self, proc: SBProcess, target: SBTarget, buf: SBData) -> Union[PCLnTabInfo, None]:
        """
        Run parsing on the PCLNTAB for a Go binary. Uses the correctly-selected version-specific subroutines.

        :param SBProcess proc: The process object currently being debugged.
        :param SBTarget target: The target associated with the process. Used for resolving file->load addresses.
        :param SBData buf: The data buffer holding the section associated with gopclntab.
        :return Union[PCLnTabInfo, None]: If parsing succeeds: returns a completed PCLnTabInfo. Otherwise None.
        """

        if self.valid:
            reader = self.__get_int_reader(buf)[8 // self.ptr_size :]

            self.__read_header(reader)

            if self.__make_func_map(proc, target, buf):
                self.version_bounds = self.differentiate_versions()
                return PCLnTabInfo(
                    max_pc_file=self.max_pc_file,
                    max_pc_load=file_to_load_address(target, self.max_pc_file),
                    func_mapping=self.func_mapping,
                    version_bounds=self.version_bounds,
                    ptr_size=self.ptr_size,
                )
        return None
