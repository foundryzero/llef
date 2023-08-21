"""arm architecture definition."""

from arch.base_arch import BaseArch


class Arm(BaseArch):
    """
    arm support file
    """

    bits = 32

    gpr_registers = [
        "r0",
        "r1",
        "r2",
        "r3",
        "r4",
        "r5",
        "r6",
        "r7",
        "r8",
        "r9",
        "r10",
        "r11",
        "r12",
        "sp",
        "lr",
        "pc",
    ]

    gpr_key = "general"

    flag_register = "cpsr"

    # Bitmasks used to extract flag bits from cpsr register value
    flag_register_bit_masks = {
        "n": 0x80000000,
        "z": 0x40000000,
        "c": 0x20000000,
        "v": 0x10000000,
        "q": 0x8000000,
        "j": 0x1000000,
        "ge": 0xF0000,
        "e": 0x200,
        "a": 0x100,
        "i": 0x80,
        "f": 0x40,
        "t": 0x20,
    }
