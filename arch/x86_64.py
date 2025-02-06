"""x86_64 architecture definition."""

from arch.base_arch import BaseArch, FlagRegister


class X86_64(BaseArch):
    """
    These are currently hardcoded for X86_64.
    """

    bits = 64

    gpr_registers = [
        "rax",
        "rbx",
        "rcx",
        "rdx",
        "rsp",
        "rbp",
        "rsi",
        "rdi",
        "rip",
        "r8",
        "r9",
        "r10",
        "r11",
        "r12",
        "r13",
        "r14",
        "r15",
    ]

    gpr_key = "general purpose"

    # Bitmasks used to extract flag bits from eflags register value
    _eflag_register_bit_masks = {
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
        "virtualx86": 0x20000,
        "identification": 0x200000,
    }

    # Whether LLDB exposes eflags or rflags varies depending on the platform
    # rflags and eflags bit masks are identical for the lower 32-bits
    flag_registers = [
        FlagRegister("rflags", _eflag_register_bit_masks),
        FlagRegister("eflags", _eflag_register_bit_masks),
    ]
