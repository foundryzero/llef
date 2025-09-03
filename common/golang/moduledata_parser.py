"""Class for extracting information from a Go moduledata structure."""

import struct
from typing import Union

from lldb import UINT32_MAX, SBData, SBError, SBProcess, SBTarget

from common.constants import pointer
from common.golang.constants import GO_MD_7_ONLY, GO_MD_8_TO_15, GO_MD_16_TO_17, GO_MD_18_TO_19, GO_MD_20_TO_24
from common.golang.interfaces import ModuleDataInfo
from common.golang.types import GoType, PopulateInfo, TypeHeader
from common.golang.util_stateless import file_to_load_address, read_varint
from common.state import LLEFState


class ModuleDataParser:
    """
    Stores information about the ModuleData context and parses type information from it.

    Latest ModuleData struct information found at: https://github.com/golang/go/blob/master/src/runtime/symtab.go.
    """

    section_offset: int

    # Start of the 'types' section pointed to by the Go moduledata struct. Name aligns with Go source.
    types: pointer

    # End of the 'types' section pointed to by the Go moduledata struct. Name aligns with Go source.
    etypes: pointer

    # typelinks is an array of offsets to these type information structures. The length is typelinks_len.
    # Name aligns with Go source.
    typelinks: int
    typelinks_len: int

    # A map holding successfully parsed GoType Python structures with their associated addresses.
    # Name aligns with Go source.
    __type_structs: dict[pointer, GoType]

    def __init__(self, section_offset: int) -> None:
        self.section_offset = section_offset
        self.__type_structs = {}

    def get_name(self, type_section: bytes, name_offset: int, header: TypeHeader) -> Union[str, None]:
        """
        Run the version-specific procedure for decoding the name of a type from memory.

        :param bytes type_section: Slice of program memory from self.types to self.etypes.
        :param int name_offset: The offset within the section to begin reading at.
        :param TypeHeader header: Information about this type, such as the tflag.
        :return Union[str, None]: If name_offset is valid, returns the decoded name. Otherwise, None.
        """

        name = None
        # Check that pointer + offset doesn't exceed the end pointer for the types section.
        if self.types + name_offset < self.etypes:
            # Module data layout depends on the Go version.
            (go_min_version, go_max_version) = LLEFState.go_state.pclntab_info.version_bounds
            if go_min_version >= 17:
                length, name_offset = read_varint(type_section, name_offset)
                if self.types + name_offset + length <= self.etypes:
                    name = type_section[name_offset : name_offset + length].decode("utf-8", "replace")
                    # Sometimes names start with an extraneous asterisk (*) - tflag tells us when.
                    if header.tflag & 2:
                        name = name[1:]

            elif go_max_version <= 16:
                (length,) = struct.unpack_from(">H", type_section, name_offset)
                name_offset += 2
                if self.types + name_offset + length <= self.etypes:
                    name = type_section[name_offset : name_offset + length].decode("utf-8", "replace")
                    if header.tflag & 2:
                        name = name[1:]

        return name

    def parse_type(self, type_section: bytes, type_offset: int) -> bool:
        """
        Decodes and adds to internal state an individual type information structure.

        :param bytes type_section: Slice of program memory from self.types to self.etypes.
        :param int offset: The offset within the section to begin parsing at.
        :return bool: If parsing the type (and all children/parent types) succeeds, returns True. Otherwise False.
        """
        type_address = self.types + type_offset
        if type_address in self.__type_structs:
            # Type already parsed.
            return True

        ptr_size = LLEFState.go_state.pclntab_info.ptr_size
        if ptr_size == 4:
            ptr_specifier = "I"
        else:
            # ptr_size == 8 here.
            ptr_specifier = "Q"

        # Send some useful information to populate().
        info = PopulateInfo(types=self.types, etypes=self.etypes, ptr_size=ptr_size, ptr_specifier=ptr_specifier)

        type_entry_width = ptr_size * 4 + 16
        # Check that struct.unpack_from() won't read outside bounds.
        if type_address + type_entry_width <= self.etypes:
            header = TypeHeader()

            # Luckily, this format has remained the same for all Go versions since inception.
            unpacker = "<" + ptr_specifier * 2 + "IBBBB" + ptr_specifier * 2 + "II"
            tup = struct.unpack_from(unpacker, type_section, type_offset)
            (
                header.size,  # usize
                header.ptrbytes,  # usize
                header.t_hash,  # uint32
                header.tflag,  # uint8
                header.align,  # uint8
                header.fieldalign,  # uint8
                header.kind,  # uint8
                _,  # (equal) usize
                _,  # (gcdata) usize
                name_offset,  # uint32
                ptr_to_this_offset,  # uint32
            ) = tup

            name_offset += 1
            name = self.get_name(type_section, name_offset, header)
            if name is not None:
                header.name = name

                go_type = GoType.make_from(header, LLEFState.go_state.pclntab_info.version_bounds)

                if go_type is not None:
                    # Each type has a corresponding populate() function.
                    type_struct_pointers = go_type.populate(type_section, type_offset + type_entry_width, info)

                    # If an error occurred during parsing: type_struct_pointers is None
                    # Otherwise, if simple data type: type_struct_pointers is []
                    # Otherwise, if complex data type: it's a list of pointers go walk over next (recursively).
                    if type_struct_pointers is not None:
                        self.__type_structs[type_address] = go_type

                        processing_valid = True
                        for type_addr in type_struct_pointers:
                            if self.types <= type_addr < self.etypes:
                                if not self.parse_type(type_section, type_addr - self.types):
                                    processing_valid = False
                                    break
                            else:
                                processing_valid = False
                                break

                        if processing_valid and ptr_to_this_offset not in (0, UINT32_MAX):
                            if not self.parse_type(type_section, ptr_to_this_offset):
                                processing_valid = False
                        return processing_valid

        return False

    def parse(self, proc: SBProcess, data: SBData, target: SBTarget) -> Union[ModuleDataInfo, None]:
        """
        Attempts to parse a candidate ModuleData, as located by self.section_offset.

        :param SBProcess proc: The process currently being debugged.
        :param SBData data: The buffer holding the candidate ModuleData structure.
        :param SBTarget target: The target associated with the process. Used for resolving file->load addresses.
        :return Union[ModuleDataInfo, None]: If run on a real ModuleData, and a supported Go version, then returns
                                             the parsed information as a data structure. Otherwise None.
        """

        offsets = None

        (min_go, max_go) = LLEFState.go_state.pclntab_info.version_bounds
        if min_go == 7 and max_go == 7:
            offsets = GO_MD_7_ONLY
        if min_go >= 8 and max_go <= 15:
            offsets = GO_MD_8_TO_15
        elif min_go >= 16 and max_go <= 17:
            offsets = GO_MD_16_TO_17
        elif min_go >= 18 and max_go <= 19:
            offsets = GO_MD_18_TO_19
        elif min_go >= 20 and max_go <= 24:
            offsets = GO_MD_20_TO_24

        module_data_info = None

        if offsets is not None:
            if LLEFState.go_state.pclntab_info.ptr_size == 4:
                reader = data.uint32[self.section_offset // 4 :]
            else:
                # ptr_size == 8 here.
                reader = data.uint64[self.section_offset // 8 :]

            # Use these fields as a sanity check, to ensure we really did find ModuleData.
            min_program_counter = reader[offsets.minpc]
            max_program_counter = reader[offsets.maxpc]
            first_function_address = LLEFState.go_state.pclntab_info.func_mapping[0][1].file_addr
            if (
                min_program_counter == first_function_address
                and max_program_counter == LLEFState.go_state.pclntab_info.max_pc_file
            ):
                self.types = file_to_load_address(target, reader[offsets.types])
                # -1 +1 so that we don't miss the end of the section by 1, and the file->load resolution then fails.
                self.etypes = file_to_load_address(target, reader[offsets.etypes] - 1) + 1
                self.typelinks = file_to_load_address(target, reader[offsets.typelinks])
                self.typelinks_len = reader[offsets.typelinks_len]

                err = SBError()
                type_section = proc.ReadMemory(self.types, self.etypes - self.types, err)
                if err.Success() and type_section is not None:
                    read_success = True
                    for i in range(self.typelinks_len):
                        err = SBError()
                        offset = proc.ReadUnsignedFromMemory(self.typelinks + i * 4, 4, err)
                        if err.Fail():
                            read_success = False
                        if not self.parse_type(type_section, offset):
                            read_success = False

                    # Now we have discovered everything, go and fill in links from type to type.
                    if read_success and len(self.__type_structs) > 0:
                        for go_type in self.__type_structs.values():
                            go_type.fixup_types(self.__type_structs)
                        module_data_info = ModuleDataInfo(type_structs=self.__type_structs)

        return module_data_info
