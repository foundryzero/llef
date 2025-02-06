"""Pattern command class."""

import argparse
import binascii
import os
import shlex
from typing import Any, Dict, Type

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_command import BaseCommand
from commands.base_container import BaseContainer
from common.constants import MSG_TYPE, TERM_COLORS
from common.de_bruijn import generate_cyclic_pattern
from common.state import LLEFState
from common.util import output_line, print_message


class PatternContainer(BaseContainer):
    """Creates a container for the Pattern command. Sub commands are implemented in inner classes"""

    container_verb: str = "pattern"

    @staticmethod
    def get_short_help() -> str:
        return "pattern (create|search)"

    @staticmethod
    def get_long_help() -> str:
        return """
                Generate or Search a De Bruijn Sequence of unique substrings of length N
                and a total length of LENGTH. The default value of N is set to match the
                currently loaded architecture.
                """


class PatternCreateCommand(BaseCommand):
    """Implements the 'create' subcommand"""

    program: str = "create"
    container: Type[BaseContainer] = PatternContainer
    state: LLEFState

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument("length", type=int, help="Length of desired output")
        parser.add_argument(
            "-n",
            "--cycle-length",
            type=int,
            help="The length of the De Bruijn Cycle",
        )
        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: pattern create L [-n]"

    @staticmethod
    def get_long_help() -> str:
        return (
            "Generate a De Bruijn Sequence of unique substrings of length N and a total length of LENGTH."
            + os.linesep
            + PatternCreateCommand.get_command_parser().format_help()
        )

    def __init__(self, _: SBDebugger, __: Dict[Any, Any]) -> None:
        """Class initializer."""
        self.parser = self.get_command_parser()
        self.state = LLEFState()

    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'pattern create' command"""
        args = self.parser.parse_args(shlex.split(command))
        length = args.length
        num_chars = args.cycle_length or 4  # Hardcoded default value.
        print_message(MSG_TYPE.INFO, f"Generating a pattern of {length} bytes (n={num_chars})")
        pattern = generate_cyclic_pattern(length, num_chars)
        output_line(pattern.decode("utf-8"))

        if exe_ctx.GetProcess().GetState() == 0:
            print_message(
                MSG_TYPE.ERROR,
                "Created pattern cannot be stored in a convenience variable as there is no running process",
            )
        else:
            value = exe_ctx.GetTarget().EvaluateExpression(f'"{pattern.decode("utf-8")}"')
            print_message(
                MSG_TYPE.INFO,
                f"Pattern saved in variable: {TERM_COLORS.RED.value}{value.GetName()}{TERM_COLORS.ENDC.value}",
            )
            self.state.created_patterns.append(
                {
                    "name": value.GetName(),
                    "pattern_bytes": pattern,
                    "pattern_string": pattern.decode("utf-8"),
                    "length": length,
                    "num_chars": num_chars,
                }
            )


class PatternSearchCommand(BaseCommand):
    """Implements the 'search' subcommand."""

    program = "search"
    container: Type[BaseContainer] = PatternContainer
    state: LLEFState

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument("pattern", help="The pattern of bytes to search for")
        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: pattern search <pattern>"

    @staticmethod
    def get_long_help() -> str:
        return (
            "Search a pattern (e.g. a De Bruijn Sequence) of unique substring."
            + os.linesep
            + PatternCreateCommand.get_command_parser().format_help()
        )

    def __init__(self, _: SBDebugger, __: Dict[Any, Any]) -> None:
        """Class initializer."""
        self.parser = self.get_command_parser()
        self.state = LLEFState()

    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'pattern create' command."""
        args = self.parser.parse_args(shlex.split(command))

        pattern = args.pattern
        if pattern.startswith("$"):
            pattern_value = exe_ctx.GetTarget().EvaluateExpression(pattern)
            pattern_array = pattern_value.GetData().uint8
            pattern = "".join([chr(x) for x in pattern_array])
            pattern = pattern.rstrip("\x00")
        elif pattern.startswith("0x"):
            pattern = binascii.unhexlify(pattern[2:]).decode()
        else:
            pass
        if pattern:
            for created_pattern in self.state.created_patterns:
                pattern_string = created_pattern.get("pattern_string")
                if pattern_string and pattern in pattern_string:
                    print_message(
                        MSG_TYPE.INFO,
                        f"Found in {created_pattern.get('name')} at index"
                        f" {pattern_string.index(pattern)} (little endian)",
                    )
                reverse_pattern = pattern[::-1]
                if pattern_string and reverse_pattern in pattern_string:
                    print_message(
                        MSG_TYPE.INFO,
                        f"Found in {created_pattern.get('name')} at index"
                        f" {pattern_string.index(reverse_pattern)} (big endian)",
                    )
