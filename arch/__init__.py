"""Arch module __init__.py"""

from typing import Type

from lldb import SBTarget

from arch.aarch64 import Aarch64
from arch.arm import Arm
from arch.base_arch import BaseArch
from arch.i386 import I386
from arch.ppc import PPC
from arch.x86_64 import X86_64
from common.constants import MSG_TYPE
from common.util import extract_arch_from_triple, print_message

# macOS devices running arm chips identify as arm64.
# aarch64 and arm64 backends have been merged, so alias arm64 to aarch64.
# There's also arm64e architecture, which is basically ARMv8.3
# but includes pointer authentication and for now is Apple-specific.
supported_arch = {
    "arm": Arm,
    "i386": I386,
    "x86_64": X86_64,
    "aarch64": Aarch64,
    "arm64": Aarch64,
    "arm64e": Aarch64,
    "powerpc": PPC,
}


def get_arch(target: SBTarget) -> Type[BaseArch]:
    """Get the architecture of a given target"""
    arch = extract_arch_from_triple(target.triple)
    return get_arch_from_str(arch)


def get_arch_from_str(arch: str) -> Type[BaseArch]:
    """Get the architecture class from string"""
    if arch in supported_arch:
        return supported_arch[arch]

    print_message(MSG_TYPE.ERROR, f"Unknown Architecture: {arch}")
    raise TypeError(f"Unknown target architecture: {arch}")
