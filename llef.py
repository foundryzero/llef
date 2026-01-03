#!/usr/bin/env python3
"""LLEF main handler."""

# ---------------------------------------------------------------------
# To use this in the embedded python interpreter using "lldb" just
# import it with the full path using the "command script import"
# command``
#   (lldb) command script import /path/to/cmdtemplate.py
#
# The __lldb_init_module function automatically loads the stop-hook-handler
# ---------------------------------------------------------------------

import platform
from typing import Any, Union

from lldb import SBDebugger

from commands.base_command import BaseCommand
from commands.base_container import BaseContainer
from commands.checksec import ChecksecCommand
from commands.color_settings import ColorSettingsCommand
from commands.context import ContextCommand
from commands.dereference import DereferenceCommand
from commands.golang import (
    GolangBacktraceCommand,
    GolangContainer,
    GolangFindFuncCommand,
    GolangGetTypeCommand,
    GolangReanalyseCommand,
    GolangUnpackTypeCommand,
)
from commands.hexdump import HexdumpCommand
from commands.pattern import (
    PatternContainer,
    PatternCreateCommand,
    PatternSearchCommand,
)
from commands.scan import ScanCommand
from commands.settings import SettingsCommand
from commands.xinfo import XinfoCommand
from common.state import LLEFState
from common.util import (
    lldb_version_to_clang,
    parse_apple_clang_version_string,
    parse_llvm_version_string,
)
from handlers.stop_hook import StopHookHandler


def __lldb_init_module(debugger: SBDebugger, _: dict[Any, Any]) -> None:
    commands: list[Union[type[BaseCommand], type[BaseContainer]]] = [
        PatternContainer,
        PatternCreateCommand,
        PatternSearchCommand,
        ContextCommand,
        SettingsCommand,
        ColorSettingsCommand,
        HexdumpCommand,
        ChecksecCommand,
        XinfoCommand,
        DereferenceCommand,
        ScanCommand,
        GolangContainer,
        GolangBacktraceCommand,
        GolangFindFuncCommand,
        GolangGetTypeCommand,
        GolangUnpackTypeCommand,
        GolangReanalyseCommand,
    ]

    handlers = [StopHookHandler]

    for command in commands:
        command.lldb_self_register(debugger, "llef")

    for handler in handlers:
        handler.lldb_self_register(debugger, "llef")

    LLEFState.platform = platform.system()
    if LLEFState.platform == "Darwin":
        # On Darwin, we have two possibilities:
        # - LLDB shipped with Apple Clang
        # - LLDB built from the LLVM sources
        # Those have different versioning schemes, and they need to be normalized to the Apple Clang version
        # to adhere to the assumptions taken in other places regarding LLDB on Darwin.
        if version := parse_apple_clang_version_string(debugger.GetVersionString()):
            LLEFState.version = version
        elif version := parse_llvm_version_string(debugger.GetVersionString()):
            LLEFState.version = lldb_version_to_clang(version)
        else:
            raise ValueError(
                f"Unable to parse LLDB version string: {debugger.GetVersionString()}"
            )
    else:
        if version := parse_llvm_version_string(debugger.GetVersionString()):
            LLEFState.version = version
        else:
            raise ValueError(
                f"Unable to parse LLDB version string: {debugger.GetVersionString()}"
            )
