"""aarch64 architecture definition."""

from arch.base_arch import BaseArch, FlagRegister


class Aarch64(BaseArch):
    """
    aarch64 support file
    """

    bits = 64

    gpr_registers = [
        "x0",
        "x1",
        "x2",
        "x3",
        "x4",
        "x5",
        "x6",
        "x7",
        "x8",
        "x9",
        "x10",
        "x11",
        "x12",
        "x13",
        "x14",
        "x15",
        "x16",
        "x17",
        "x18",
        "x19",
        "x20",
        "x21",
        "x22",
        "x23",
        "x24",
        "x25",
        "x26",
        "x27",
        "x28",
        "x29",
        "x30",
        "fp",
        "lr",
        "sp",
        "pc",
    ]

    gpr_key = "general"

    # Bitmasks used to extract flag bits from cpsr register value
    _cpsr_register_bit_masks = {
        "n": 0x80000000,
        "z": 0x40000000,
        "c": 0x20000000,
        "v": 0x10000000,
        "q": 0x8000000,
        "ssbs": 0x800000,
        "pan": 0x400000,
        "dit": 0x200000,
        "ge": 0xF0000,
        "e": 0x200,
        "a": 0x100,
        "i": 0x80,
        "f": 0x40,
        "m": 0xF,
    }

    flag_registers = [FlagRegister("cpsr", _cpsr_register_bit_masks)]
