"""Arch module __init__.py"""
from typing import Type

from lldb import SBTarget

from arch.aarch64 import Aarch64
from arch.base_arch import BaseArch
from arch.x86_64 import X86_64
from common.constants import MSG_TYPE
from common.util import extract_arch_from_triple, print_message

supported_arch = {"x86_64": X86_64, "aarch64": Aarch64}


def get_arch(target: SBTarget) -> Type[BaseArch]:
    """Get the architecture of a given target"""
    arch = extract_arch_from_triple(target.triple)
    if arch in supported_arch:
        return supported_arch[arch]

    print_message(MSG_TYPE.ERROR, "Unknown Architecture")
    raise TypeError("Unknown target architecture")
