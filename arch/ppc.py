"""PowerPC architecture definition."""
from arch.base_arch import BaseArch, FlagRegister


class PPC(BaseArch):
    """
    These are currently hardcoded for PowerPC.
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
        "r13",
        "pc",  # program counter
        "msr",  # machine state register
        "lr",  # link register
        "ctr",  # counter
    ]

    gpr_key = "general purpose"

    _xer_register_bit_masks = {
        "summary_overflow": 0x80000000,
        "overflow": 0x40000000,
        "carry": 0x20000000,
    }

    _cr_register_bit_masks = {
        "cr0_lt": 0x80000000,
        "cr0_gt": 0x40000000,
        "cr0_eq": 0x20000000,
        "cr0_so": 0x10000000
    }

    flag_registers = [
        FlagRegister("cr", _cr_register_bit_masks),
        FlagRegister("xer", _xer_register_bit_masks)
    ]
