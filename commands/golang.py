"""Go-specific command classes."""

import argparse
import os
import shlex
from typing import Any, Union

from lldb import SBCommandReturnObject, SBDebugger, SBExecutionContext

from commands.base_command import BaseCommand
from commands.base_container import BaseContainer
from common.constants import MSG_TYPE
from common.context_handler import ContextHandler
from common.golang.constants import GO_TUNE_DEFAULT_UNPACK_DEPTH
from common.golang.data import GoDataBad
from common.golang.improvements import go_improve_backtrace
from common.golang.state import GoState
from common.golang.static import setup_go
from common.golang.type_getter import TypeGetter
from common.golang.types import ExtractInfo
from common.golang.util import go_calculate_bp, go_find_func, perform_go_functions
from common.output_util import output_line, print_message
from common.settings import LLEFSettings
from common.state import LLEFState
from common.util import check_process, check_version, hex_int, positive_int

GO_DISABLED_MSG = "Go support is disabled. Re-enable using `llefsettings set go_support_level auto`."


class GolangContainer(BaseContainer):
    """Creates a container for the Go command. Sub commands are implemented in inner classes"""

    container_verb: str = "go"

    @staticmethod
    def get_short_help() -> str:
        return "go (find-func|get-type|unpack-type|backtrace|reanalyse)"

    @staticmethod
    def get_long_help() -> str:
        return (
            "The subcommands use information from a Go binary to display information about functions and types and "
            "to unpack objects at runtime depending on their type."
        )


class GolangFindFuncCommand(BaseCommand):
    """Implements the 'find-func' subcommand"""

    program: str = "find-func"
    container: type[BaseContainer] = GolangContainer
    parser: argparse.ArgumentParser
    context_handler: ContextHandler
    settings: LLEFSettings

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "target",
            default=None,
            nargs="?",
            help="Either a code address, or a function name, or omitted",
        )
        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: go find-func [address|name]"

    @staticmethod
    def get_long_help() -> str:
        return (
            "If given an address, prints the Go function containing that address."
            + os.linesep
            + "If given a name, prints the address of the Go function with that name."
            + os.linesep
            + "If not given an argument, prints a table of all known functions. File addresses appear in parentheses."
            + os.linesep
            + GolangFindFuncCommand.get_command_parser().format_help()
        )

    def __init__(self, debugger: SBDebugger, _: dict[Any, Any]) -> None:
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.settings = LLEFSettings(debugger)

    @check_version("15.0.0")
    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'go find-func' command"""
        args = self.parser.parse_args(shlex.split(command))
        address_or_name = args.target

        self.context_handler.refresh(exe_ctx)

        if self.settings.go_support_level == "disable":
            print_message(MSG_TYPE.ERROR, GO_DISABLED_MSG)
        elif not perform_go_functions(self.settings):
            print_message(MSG_TYPE.ERROR, "The binary does not appear to be a Go binary.")
        else:

            if address_or_name is None:
                # Print a table
                output_line("LOAD_ADDRESS (FILE_ADDRESS) - NAME")
                for entry, f in LLEFState.go_state.pclntab_info.func_mapping:
                    output_line(f"{hex(entry)} ({hex(f.file_addr)}) - {f.name}")
            else:

                try:
                    # User has typed in a numeric address
                    address = int(address_or_name, 0)
                    record = go_find_func(address)
                    if record is not None:
                        (entry, gofunc) = record
                        output_line(f"{hex(entry)} - {gofunc.name} (file address = {hex(gofunc.file_addr)})")
                    else:
                        print_message(MSG_TYPE.ERROR, f"Could not find function containing address {hex(address)}")

                except ValueError:
                    # User has typed in a string name
                    name = address_or_name

                    success = False
                    for entry, f in LLEFState.go_state.pclntab_info.func_mapping:
                        if f.name == name:
                            output_line(f"{hex(entry)} - {name} (file address = {hex(f.file_addr)})")
                            success = True
                            # Don't break: there are potentially multiple matches.

                    if not success:
                        print_message(MSG_TYPE.ERROR, f"Could not find function called '{name}'")


class GolangGetTypeCommand(BaseCommand):
    """Implements the 'get-type' subcommand"""

    program: str = "get-type"
    container: type[BaseContainer] = GolangContainer
    parser: argparse.ArgumentParser
    context_handler: ContextHandler
    settings: LLEFSettings

    type_getter: Union[TypeGetter, None]

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "target",
            default=None,
            nargs="?",
            help="Either a type information structure address, or a type name, or omitted",
        )
        parser.add_argument(
            "-d",
            "--depth",
            type=positive_int,
            default=GO_TUNE_DEFAULT_UNPACK_DEPTH,
            help=f"Depth to unpack child types, default is {GO_TUNE_DEFAULT_UNPACK_DEPTH}",
        )

        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: go get-type [address|name] [--depth n]"

    @staticmethod
    def get_long_help() -> str:
        return (
            "If given an address, prints a deconstruction of the Go type struct at that address."
            + os.linesep
            + "If given a name, prints a deconstruction of the Go type with that name."
            + os.linesep
            + "If not given an argument, prints a table of all known types."
            + os.linesep
            + "The depth argument specifies how deeply to follow and unpack child types. "
            + f"It defaults to {GO_TUNE_DEFAULT_UNPACK_DEPTH}"
            + os.linesep
            + GolangGetTypeCommand.get_command_parser().format_help()
        )

    def __init__(self, debugger: SBDebugger, _: dict[Any, Any]) -> None:
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.settings = LLEFSettings(debugger)

        self.type_getter = None  # For now, and will be set when we have a context later.

    @check_version("15.0.0")
    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'go get-type' command"""
        args = self.parser.parse_args(shlex.split(command))
        address_or_name = args.target
        depth: int = args.depth

        self.context_handler.refresh(exe_ctx)

        if self.settings.go_support_level == "disable":
            print_message(MSG_TYPE.ERROR, GO_DISABLED_MSG)
        elif not perform_go_functions(self.settings):
            print_message(MSG_TYPE.ERROR, "The binary does not appear to be a Go binary.")
        elif LLEFState.go_state.moduledata_info is None:
            print_message(MSG_TYPE.ERROR, "No type information available in this Go binary.")
        else:
            # At this point, we're good to go with running the command.

            if address_or_name is None:
                # Print a table
                output_line("TYPE_POINTER - SHORT_NAME = DECONSTRUCTED_TYPE")
                for ptr, type_struct in LLEFState.go_state.moduledata_info.type_structs.items():
                    output_line(f"{hex(ptr)} - {type_struct.header.name} = {type_struct.get_underlying_type(depth)}")
            else:

                try:
                    # User has typed in a numeric address
                    address = int(address_or_name, 0)
                    type_lookup = LLEFState.go_state.moduledata_info.type_structs.get(address)
                    if type_lookup is not None:
                        output_line(
                            f"{hex(address)} - {type_lookup.header.name} = {type_lookup.get_underlying_type(depth)}",
                            never_truncate=True,
                        )
                        output_line(f"Size in bytes: {hex(type_lookup.header.size)}")
                    else:
                        print_message(
                            MSG_TYPE.ERROR, f"Could not find type information struct at address {hex(address)}"
                        )

                except ValueError:
                    # User has typed in a string name
                    name = address_or_name

                    if self.type_getter is None:
                        self.type_getter = TypeGetter(LLEFState.go_state.moduledata_info.type_structs)

                    parsed_type = self.type_getter.string_to_type(name)
                    if parsed_type is not None:
                        output_line(f"{name} = {parsed_type.get_underlying_type(depth)}", never_truncate=True)
                        output_line(f"Size in bytes: {hex(parsed_type.header.size)}")
                    else:
                        print_message(MSG_TYPE.ERROR, f"Could not parse type '{name}'")


class GolangUnpackTypeCommand(BaseCommand):
    """Implements the 'unpack-type' subcommand"""

    program: str = "unpack-type"
    container: type[BaseContainer] = GolangContainer
    parser: argparse.ArgumentParser
    context_handler: ContextHandler
    settings: LLEFSettings

    type_getter: Union[TypeGetter, None]

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "address",
            type=hex_int,
            help="The pointer to the start of this data structure",
        )
        parser.add_argument(
            "type",
            help="Either a type information structure address or a type name",
        )
        parser.add_argument(
            "-d",
            "--depth",
            type=positive_int,
            default=GO_TUNE_DEFAULT_UNPACK_DEPTH,
            help=f"Depth to unpack child objects, default is {GO_TUNE_DEFAULT_UNPACK_DEPTH}",
        )
        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: go unpack-type address type [--depth n]"

    @staticmethod
    def get_long_help() -> str:
        return (
            "Unpacks a Go object at an address using supplied type information."
            + os.linesep
            + "The type can either be a string or a pointer to a type information structure."
            + os.linesep
            + "The depth argument specifies how deeply to follow and unpack child objects. "
            + f"It defaults to {GO_TUNE_DEFAULT_UNPACK_DEPTH}"
            + os.linesep
            + GolangUnpackTypeCommand.get_command_parser().format_help()
        )

    def __init__(self, debugger: SBDebugger, _: dict[Any, Any]) -> None:
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.settings = LLEFSettings(debugger)

        self.type_getter = None  # For now, and will be set when we have a context later.

    @check_version("15.0.0")
    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'go unpack-type' command"""
        args = self.parser.parse_args(shlex.split(command))
        object_pointer: int = args.address
        type_name_or_pointer: str = args.type
        depth: int = args.depth

        self.context_handler.refresh(exe_ctx)

        if self.settings.go_support_level == "disable":
            print_message(MSG_TYPE.ERROR, GO_DISABLED_MSG)
        elif not perform_go_functions(self.settings):
            print_message(MSG_TYPE.ERROR, "The binary does not appear to be a Go binary.")
        elif LLEFState.go_state.moduledata_info is None:
            print_message(MSG_TYPE.ERROR, "No type information available in this Go binary.")
        else:
            # At this point, we're good to go with running the command.

            # First, decode the type struct.
            type_struct = None
            try:
                # User has typed in a numeric address for type pointer
                type_ptr = int(type_name_or_pointer, 0)
                type_struct = LLEFState.go_state.moduledata_info.type_structs.get(type_ptr)
                if type_struct is None:
                    print_message(MSG_TYPE.ERROR, f"Could not find type information struct at address {hex(type_ptr)}")

            except ValueError:
                # User has typed in a string name
                name = type_name_or_pointer

                if self.type_getter is None:
                    self.type_getter = TypeGetter(LLEFState.go_state.moduledata_info.type_structs)

                type_struct = self.type_getter.string_to_type(name)
                if type_struct is None:
                    print_message(MSG_TYPE.ERROR, f"Could not parse type '{name}'")

            # Now, unpack the object.
            if type_struct is not None:
                info = ExtractInfo(
                    proc=exe_ctx.GetProcess(),
                    ptr_size=LLEFState.go_state.pclntab_info.ptr_size,
                    type_structs=LLEFState.go_state.moduledata_info.type_structs,
                )
                py_obj = type_struct.extract_at(info, object_pointer, set(), depth)

                if isinstance(py_obj, GoDataBad):
                    # Print a custom error message, otherwise the user would just see "?"
                    err = "Couldn't unpack from that address (impossible data or non-existent memory)."
                    print_message(MSG_TYPE.ERROR, err)
                else:
                    # This can span multiple lines of output, as it's normally used to get full information
                    # after a truncated version was displayed inline in the context viewer.
                    output_line(str(py_obj), never_truncate=True)


class GolangBacktraceCommand(BaseCommand):
    """Implements the 'backtrace' subcommand"""

    program: str = "backtrace"
    container: type[BaseContainer] = GolangContainer
    parser: argparse.ArgumentParser
    context_handler: ContextHandler
    settings: LLEFSettings

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-d",
            "--depth",
            type=positive_int,
            default=10,
            help="The number of lines of backtrace to display, default is 10",
        )
        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: go backtrace [--depth n]"

    @staticmethod
    def get_long_help() -> str:
        return (
            "Displays a backtrace from the current function up the call stack."
            + os.linesep
            + "The depth argument specifies how many functions to traverse back. The default is 10."
            + os.linesep
            + GolangBacktraceCommand.get_command_parser().format_help()
        )

    def __init__(self, debugger: SBDebugger, _: dict[Any, Any]) -> None:
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.settings = LLEFSettings(debugger)

    @check_version("15.0.0")
    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'go backtrace' command"""
        args = self.parser.parse_args(shlex.split(command))
        depth: int = args.depth

        self.context_handler.refresh(exe_ctx)

        if self.settings.go_support_level == "disable":
            print_message(MSG_TYPE.ERROR, GO_DISABLED_MSG)
        elif not perform_go_functions(self.settings):
            print_message(MSG_TYPE.ERROR, "The binary does not appear to be a Go binary.")
        else:
            # At this point, we're good to go with running the command.

            bt = go_improve_backtrace(
                exe_ctx.GetProcess(),
                exe_ctx.GetFrame(),
                self.context_handler.arch,
                self.context_handler.color_settings,
                depth,
            )
            if bt is not None:
                output_line(bt)
            else:
                print_message(MSG_TYPE.ERROR, "Go traceback failed. Try using LLDB's `bt` command.")


class GolangReanalyseCommand(BaseCommand):
    """Implements the 'reanalyse' subcommand"""

    program: str = "reanalyse"
    container: type[BaseContainer] = GolangContainer
    parser: argparse.ArgumentParser
    context_handler: ContextHandler
    settings: LLEFSettings

    @classmethod
    def get_command_parser(cls) -> argparse.ArgumentParser:
        """Get the command parser."""
        parser = argparse.ArgumentParser()
        return parser

    @staticmethod
    def get_short_help() -> str:
        return "Usage: go reanalyse"

    @staticmethod
    def get_long_help() -> str:
        return (
            "Clears the internal Go-specific analysis and performs it again according to the support level."
            + os.linesep
            + "'auto' - performs most analysis."
            + os.linesep
            + "'force' - includes heavier analysis such as scanning Windows binaries to detect Go."
            + os.linesep
            + GolangReanalyseCommand.get_command_parser().format_help()
        )

    def __init__(self, debugger: SBDebugger, _: dict[Any, Any]) -> None:
        self.parser = self.get_command_parser()
        self.context_handler = ContextHandler(debugger)
        self.settings = LLEFSettings(debugger)

    @check_version("15.0.0")
    @check_process
    def __call__(
        self,
        debugger: SBDebugger,
        command: str,
        exe_ctx: SBExecutionContext,
        result: SBCommandReturnObject,
    ) -> None:
        """Handles the invocation of 'reanalyse' command"""
        _ = self.parser.parse_args(shlex.split(command))

        self.context_handler.refresh(exe_ctx)

        if self.settings.go_support_level == "disable":
            print_message(MSG_TYPE.ERROR, GO_DISABLED_MSG)
        else:
            LLEFState.go_state = GoState()
            setup_go(exe_ctx.GetProcess(), exe_ctx.GetTarget(), self.settings)
            go_calculate_bp.cache_clear()
            go_find_func.cache_clear()
