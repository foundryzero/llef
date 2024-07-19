"""i386 architecture definition."""
from arch.base_arch import BaseArch, FlagRegister


class I386(BaseArch):
    """
    These are currently hardcoded for i386.
    """

    bits = 32

    gpr_registers = [
        "eax",
        "ebx",
        "ecx",
        "edx",
        "edi",
        "esi",
        "ebp",
        "esp",
        "eip",
        "cs",
        "fs",
        "gs",
        "ss",
        "ds",
        "es",
    ]

    gpr_key = "general purpose"

    # Bitmasks used to extract flag bits from eflags register value
    _eflags_register_bit_masks = {
        "zero": 0x40,
        "carry": 0x1,
        "parity": 0x4,
        "adjust": 0x10,
        "sign": 0x80,
        "trap": 0x100,
        "interrupt": 0x200,
        "direction": 0x400,
        "overflow": 0x800,
        "resume": 0x10000,
        "virtual8086": 0x20000,
        "identification": 0x200000,
    }

    flag_registers = [
        FlagRegister("eflags", _eflags_register_bit_masks),
        FlagRegister("rflags", _eflags_register_bit_masks)
    ]
