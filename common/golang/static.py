"""Functions that do (short) one-shot static analysis of a loaded Go binary."""

import struct
from dataclasses import dataclass
from typing import Iterator, Union

from lldb import SBData, SBError, SBModule, SBProcess, SBTarget, eByteOrderLittle

from common.constants import MSG_TYPE, pointer
from common.golang.constants import GO_MAGICS, GO_NOPTRDATA_NAMES, GO_PCLNTAB_NAMES
from common.golang.interfaces import ModuleDataInfo
from common.golang.moduledata_parser import ModuleDataParser
from common.golang.pclntab_parser import PCLnTabParser
from common.output_util import print_message
from common.settings import LLEFSettings
from common.state import LLEFState


def parse_pclntab(proc: SBProcess, target: SBTarget, buf: SBData, file_addr: int) -> bool:
    """
    Attempts to parse the PCLNTAB from a Go binary.

    :param SBProcess proc: The process object associated with the target.
    :param SBTarget target: The target program running under the debugger, for resolving file->load addresses.
    :param SBData buf: Binary buffer containing gopclntab.
    :param int file_addr: The file address at which the PCLNTAB's magic bytes are found.
    :return bool: Returns True if parsing succeeded (high confidence of actual Go binary).
    """

    err = SBError()
    first8bytes = buf.ReadRawData(err, 0, 8)
    if err.Success() and first8bytes is not None:
        (magic, pad, min_instr_size, ptr_size) = struct.unpack("<IHBB", first8bytes)

        parser = PCLnTabParser(file_addr, magic, pad, min_instr_size, ptr_size)

        pclntab_info = parser.parse(proc, target, buf)
        if pclntab_info is not None:
            LLEFState.go_state.pclntab_info = pclntab_info
            return True

    return False


def parse_moduledata(
    proc: SBProcess, module: SBModule, target: SBTarget, pclntab_base: int
) -> Union[ModuleDataInfo, None]:
    """
    Attempts to parse the ModuleData structure from a Go binary. This analysis must not be run before parse_pclntab.

    :param SBProcess proc: The process object associated with the target.
    :param SBModule module: The debugger module associated with the target. Used for finding sections.
    :param SBTarget target: The target program running under the debugger, for resolving file->load addresses.
    :param int pclntab_base: The address of the PCLNTAB, to aid searching for ModuleData.

    :return Union[ModuleDataInfo, None]: If parsing was successful, returns a completed ModuleDataInfo. Else None.
    """

    # The search value (pclntab_address) is the address of the PCLNTAB section encoded at the same
    # width as a pointer, and assumed Little-Endian since LLEF only currently supports LE.
    if LLEFState.go_state.pclntab_info.ptr_size == 4:
        pclntab_address = struct.pack("<I", pclntab_base)
    else:
        # ptr_size == 8 here
        pclntab_address = struct.pack("<Q", pclntab_base)

    md_info = None
    for noptrdata_name in GO_NOPTRDATA_NAMES:
        noptrdata = module.FindSection(noptrdata_name)
        if noptrdata.IsValid():
            data = noptrdata.GetSectionData()
            err = SBError()
            section_bytes = data.ReadRawData(err, 0, data.GetByteSize())

            if err.Success() and section_bytes is not None:
                start = 0

                # Guaranteed to terminate: start is strictly increasing, until no further matches then -1.
                while md_info is None:
                    start = section_bytes.find(pclntab_address, start)
                    if start == -1:
                        break

                    # ensure an aligned pointer
                    if start % LLEFState.go_state.pclntab_info.ptr_size != 0:
                        continue

                    mdp = ModuleDataParser(start)
                    md_info = mdp.parse(proc, data, target)
                    # If parsing successful, while-loop will terminate, then for-loop will break.

                    start += 1
            break

    return md_info


@dataclass(frozen=True)
class CandidatePCLnTab:
    """
    One possible PCLNTAB location.
    """

    buffer: SBData
    file_address: int
    load_address: pointer


def pclntab_candidates(module: SBModule, target: SBTarget, settings: LLEFSettings) -> Iterator[CandidatePCLnTab]:
    """
    An iterator through possible PCLNTAB locations. Tries specific section names at first and falls back to a byte scan
    for the magic value.
    This is an iterator, rather than returning a list, because the suggestions are ordered in progressive order of
    computational intensity. Iterators are lazy so we don't have to do the expensive ones if a cheap one succeeds.

    :param SBModule module: The process object associated with the target.
    :param SBTarget target: The target program running under the debugger.
    :return Iterator[Candidate]: An iterator over results, each consisting of the containing buffer and location info.
    """

    # ELF and Mach-O formats
    for pclntab_name in GO_PCLNTAB_NAMES:
        section = module.FindSection(pclntab_name)
        if section is not None and section.IsValid():
            section_data = section.GetSectionData()
            if section_data is not None and section_data.IsValid():
                yield CandidatePCLnTab(
                    buffer=section_data,
                    file_address=section.GetFileAddress(),
                    load_address=section.GetLoadAddress(target),
                )

    # Check if Windows
    windows = False
    header = module.GetSectionAtIndex(0)
    if header is not None and header.IsValid():
        header_data = header.GetSectionData()
        if header_data is not None and header_data.IsValid():
            first_two_bytes = header_data.uint8[0:2]
            # 'MZ' or 'ZM' magic number.
            if first_two_bytes in ([0x4D, 0x5A], [0x5A, 0x4D]):
                windows = True

    read_only_data = None
    rdata_sect = None
    if windows:
        # ***********************************************************************************
        # Upon reaching this point, we're about to do some heavy static scanning of the binary.
        # This is okay if the user has explicitly forced Go mode, but otherwise (auto) we should
        # quit and wait for the user to do that later on.
        # ***********************************************************************************
        if settings.go_support_level == "auto":
            settings.set("go_support_level", "disable")
            LLEFState.go_state.analysed = False
            return

        # Heavy scanning permitted from here.
        # Obtain read-only data as Python bytes
        rdata_sect = module.FindSection(".rdata")
        if rdata_sect is not None and rdata_sect.IsValid():
            rdata = rdata_sect.GetSectionData()
            if rdata is not None and rdata.IsValid():
                err = SBError()
                rdata_bytes = rdata.ReadRawData(err, 0, rdata.GetByteSize())
                if err.Success() and rdata_bytes is not None:
                    read_only_data = rdata_bytes

    # read_only_data not None implies rdata_sect not None, but the type checker doesn't know this.
    if read_only_data is not None and rdata_sect is not None:
        # If successful, initiate a manual search for PCLNTAB over each value it could start with.
        print_message(MSG_TYPE.INFO, "PE binary detected. Scanning for Golang...")
        ptr_size = module.GetAddressByteSize()
        # struct.iter_unpack requires that read_only_data be a multiple of 4 bytes. We just ensure our local copy is
        # a multiple of the pointer size (which will be 4 or 8) for easier alignment.
        while len(read_only_data) % ptr_size != 0:
            read_only_data += b"\x00"

        for magic in GO_MAGICS:
            search_pattern = struct.pack("<IH", magic, 0)
            start = 0

            # Guaranteed to terminate: start is strictly increasing, until no further matches then -1.
            while True:
                start = read_only_data.find(search_pattern, start)
                if start == -1 or len(read_only_data) - start < 8:
                    break

                # All PCLNTABs must have the following properties, so check them early.
                if (
                    start % ptr_size != 0
                    or read_only_data[start + 6] not in (1, 2, 4)
                    or read_only_data[start + 7] != ptr_size
                ):
                    start += 1
                    continue

                buffer = SBData.CreateDataFromUInt32Array(
                    eByteOrderLittle,
                    module.GetAddressByteSize(),
                    list(map(lambda x: x[0], struct.iter_unpack("<I", read_only_data[start:]))),
                )
                yield CandidatePCLnTab(
                    buffer=buffer,
                    file_address=rdata_sect.GetFileAddress() + start,
                    load_address=rdata_sect.GetLoadAddress(target) + start,
                )
        print_message(MSG_TYPE.INFO, "Scan complete.")


def setup_go(proc: SBProcess, target: SBTarget, settings: LLEFSettings) -> None:
    """
    Called once for a newly-loaded binary. Sets up go_state.
    settings.go_support_level is either auto or force, and go_state.analysed is False.

    :param SBProcess proc: The process object associated with the target.
    :param SBTarget target: The target program running under the debugger.
    """
    LLEFState.go_state.analysed = True

    # The executable has always been observed at module 0.
    module = target.GetModuleAtIndex(0)

    if module.IsValid():
        for candidate in pclntab_candidates(module, target, settings):
            LLEFState.go_state.is_go_binary = parse_pclntab(proc, target, candidate.buffer, candidate.load_address)
            if LLEFState.go_state.is_go_binary:
                print_message(MSG_TYPE.SUCCESS, "Golang detected. Parsing type information...")
                LLEFState.go_state.moduledata_info = parse_moduledata(proc, module, target, candidate.file_address)
                if LLEFState.go_state.moduledata_info is not None:
                    print_message(MSG_TYPE.SUCCESS, "Type information found.")

                else:
                    print_message(MSG_TYPE.ERROR, "No type information available.")
                break
