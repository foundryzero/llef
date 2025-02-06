from lldb import SBMemoryRegionInfo, SBProcess

from common.color_settings import LLEFColorSettings
from common.constants import MSG_TYPE
from common.util import print_message

color_settings = LLEFColorSettings()


def parse_address_ranges(process: SBProcess, region_name: str):
    """
    Parse a custom address range (e.g., 0x7fffffffe208-0x7fffffffe240)
    or extract address ranges from memory regions with a given name (e.g., libc).

    :param process: Running process of target executable.
    :param region_name: A name that can be found in the pathname of memory regions or a custom address range.
    :return: A list of address ranges.
    """
    address_ranges = []

    if "-" in region_name:
        region_start_end = region_name.split("-")
        if len(region_start_end) == 2:
            try:
                region_start = int(region_start_end[0], 16)
                region_end = int(region_start_end[1], 16)
                address_ranges.append([region_start, region_end])
            except ValueError:
                print_message(MSG_TYPE.ERROR, "Invalid address range.")
    else:
        address_ranges = find_address_ranges(process, region_name)

    return address_ranges


def find_address_ranges(process: SBProcess, region_name: str):
    """
    Extract address ranges from memory regions with @region_name.

    :param process: Running process of target executable.
    :param region_name: A name that can be found in the pathname of memory regions.
    :return: A list of address ranges.
    """

    address_ranges = []

    memory_regions = process.GetMemoryRegions()
    memory_region_count = memory_regions.GetSize()
    for i in range(memory_region_count):
        memory_region = SBMemoryRegionInfo()
        if (
            memory_regions.GetMemoryRegionAtIndex(i, memory_region)
            and memory_region.IsMapped()
            and memory_region.GetName() is not None
            and region_name in memory_region.GetName()
        ):
            region_start = memory_region.GetRegionBase()
            region_end = memory_region.GetRegionEnd()
            address_ranges.append([region_start, region_end])

    return address_ranges
