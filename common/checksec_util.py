from lldb import SBError, SBTarget

from arch import get_arch
from common.constants import ARCH_BITS
from common.util import read_program_int

PROGRAM_HEADER_OFFSET_32BIT_OFFSET = 0x1C
PROGRAM_HEADER_SIZE_32BIT_OFFSET = 0x2A
PROGRAM_HEADER_COUNT_32BIT_OFFSET = 0x2C
PROGRAM_HEADER_PERMISSION_OFFSET_32BIT_OFFSET = 0x18

PROGRAM_HEADER_OFFSET_64BIT_OFFSET = 0x20
PROGRAM_HEADER_SIZE_64BIT_OFFSET = 0x36
PROGRAM_HEADER_COUNT_64BIT_OFFSET = 0x38
PROGRAM_HEADER_PERMISSION_OFFSET_64BIT_OFFSET = 0x04


def get_executable_type(target: SBTarget):
    """
    Get executable type for a given @target ELF file.

    :param target: The target object file.
    :return: An integer representing the executable type.
    """
    return read_program_int(target, 0x10, 2)


def get_program_header_permission(target: SBTarget, target_header_type: int):
    """
    Get value of the permission field from a program header entry.

    :param target: The target object file.
    :param target_header_type: The type of the program header entry.
    :return: An integer between 0 and 7 representing the permission. Returns 'None' if program header is not found.
    """
    arch = get_arch(target).bits

    if arch == ARCH_BITS.BITS_32:
        program_header_offset = read_program_int(target, PROGRAM_HEADER_OFFSET_32BIT_OFFSET, 4)
        program_header_entry_size = read_program_int(target, PROGRAM_HEADER_SIZE_32BIT_OFFSET, 2)
        program_header_count = read_program_int(target, PROGRAM_HEADER_COUNT_32BIT_OFFSET, 2)
        program_header_permission_offset = PROGRAM_HEADER_PERMISSION_OFFSET_32BIT_OFFSET
    else:
        program_header_offset = read_program_int(target, PROGRAM_HEADER_OFFSET_64BIT_OFFSET, 8)
        program_header_entry_size = read_program_int(target, PROGRAM_HEADER_SIZE_64BIT_OFFSET, 2)
        program_header_count = read_program_int(target, PROGRAM_HEADER_COUNT_64BIT_OFFSET, 2)
        program_header_permission_offset = PROGRAM_HEADER_PERMISSION_OFFSET_64BIT_OFFSET

    permission = None
    for i in range(program_header_count):
        program_header_type = read_program_int(target, program_header_offset + program_header_entry_size * i, 4)
        if program_header_type == target_header_type:
            permission = read_program_int(
                target, program_header_offset + program_header_entry_size * i + program_header_permission_offset, 4
            )
            break

    return permission


def get_dynamic_entry(target: SBTarget, target_entry_type: int):
    """
    Get value for a given entry type in the .dynamic section table.

    :param target: The target object file.
    :param target_entry_type: The type of the entry in the .dynamic table.
    :return: Value of the entry. Returns 'None' if entry type not found.
    """
    target_entry_value = None
    # Executable has always been observed at module 0, but isn't specifically stated in docs.
    module = target.GetModuleAtIndex(0)
    section = module.FindSection(".dynamic")
    entry_count = int(section.GetByteSize() / 16)
    for i in range(entry_count):
        entry_type = section.GetSectionData(i * 16, 8).GetUnsignedInt64(SBError(), 0)
        entry_value = section.GetSectionData(i * 16 + 8, 8).GetUnsignedInt64(SBError(), 0)

        if target_entry_type == entry_type:
            target_entry_value = entry_value
            break

    return target_entry_value
