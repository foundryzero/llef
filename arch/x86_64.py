"""x86_64 architecture definition."""
import platform
from arch.base_arch import BaseArch


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

    flag_register = "eflags" if platform.system() == "Windows" else "rflags"

    # Bitmasks used to extract flag bits from rflags register value
    flag_register_bit_masks = {
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
