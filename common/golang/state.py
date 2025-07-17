"""Go state module."""

from typing import Union

from common.golang.constants import GO_TUNE_STRING_GUESS_CAPACITY, GO_TUNE_TYPE_GUESS_CAPACITY
from common.golang.interfaces import ModuleDataInfo, PCLnTabInfo
from common.golang.util_stateless import LeastRecentlyAddedDictionary


class GoState:
    """
    State class, encapsulated by global LLEF state - stores Go-specific analysis.
    """

    is_go_binary: bool  # set once, based on static analysis

    analysed: bool  # ensures we only run the analysis once

    moduledata_info: Union[ModuleDataInfo, None]  # moduledata_info might be None, e.g. legacy Go version
    pclntab_info: PCLnTabInfo  # if is_go_binary is True, then pclntab_info is always valid

    # maps a raw pointer to its guessed datatype
    type_guesses: LeastRecentlyAddedDictionary  # dict[int, GoType]
    # maps a string base address to its guessed length
    string_guesses: LeastRecentlyAddedDictionary  # dict[int, int]

    prev_func: int  # the entry address of the function executing in the previous stop

    def __init__(self) -> None:
        self.is_go_binary = False
        self.analysed = False
        self.moduledata_info = None
        self.type_guesses = LeastRecentlyAddedDictionary(capacity=GO_TUNE_TYPE_GUESS_CAPACITY)
        self.string_guesses = LeastRecentlyAddedDictionary(capacity=GO_TUNE_STRING_GUESS_CAPACITY)
        self.prev_func = 0
