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

from typing import Any, Dict, List, Type, Union

from lldb import SBDebugger

from commands.base_command import BaseCommand
from commands.base_container import BaseContainer
from commands.pattern import (
    PatternContainer,
    PatternCreateCommand,
    PatternSearchCommand,
)
from commands.context import ContextCommand

from handlers.stop_hook import StopHookHandler


def __lldb_init_module(debugger: SBDebugger, _: Dict[Any, Any]) -> None:
    commands: List[Union[Type[BaseCommand], Type[BaseContainer]]] = [
        PatternContainer,
        PatternCreateCommand,
        PatternSearchCommand,
        ContextCommand,
    ]

    handlers = [StopHookHandler]

    for command in commands:
        command.lldb_self_register(debugger, "llef")

    for handler in handlers:
        handler.lldb_self_register(debugger, "llef")
