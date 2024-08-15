"""Color settings module"""
import configparser
import os

from typing import List

from common.singleton import Singleton
from common.constants import TERM_COLORS
from common.base_settings import BaseLLEFSettings
from common.util import output_line


class LLEFColorSettings(BaseLLEFSettings, metaclass=Singleton):
    """
    Color settings class - loaded from file defined in `LLEF_CONFIG_PATH`
    """
    LLEF_CONFIG_PATH = os.path.join(os.path.expanduser('~'), ".llef_colors")
    GLOBAL_SECTION = "LLEF"

    supported_colors: List[str] = []

    @property
    def register_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "register_color", fallback="BLUE").upper()

    @property
    def modified_register_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "modified_register_color", fallback="RED").upper()

    @property
    def code_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "code_color", fallback="RED").upper()

    @property
    def heap_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "heap_color", fallback="GREEN").upper()

    @property
    def stack_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "stack_color", fallback="PINK").upper()

    @property
    def string_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "string_color", fallback="YELLOW").upper()

    @property
    def stack_address_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "stack_address_color", fallback="CYAN").upper()

    @property
    def function_name_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "function_name_color", fallback="GREEN").upper()

    @property
    def instruction_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "instruction_color", fallback="GREY").upper()

    @property
    def highlighted_instruction_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "highlighted_instruction_color", fallback="GREEN").upper()

    @property
    def line_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "line_color", fallback="GREY").upper()

    @property
    def rebased_address_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "rebased_address_color", fallback="GREY").upper()

    @property
    def section_header_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "section_header_color", fallback="BLUE").upper()

    @property
    def highlighted_index_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "highlighted_index_color", fallback="GREEN").upper()

    @property
    def index_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "index_color", fallback="PINK").upper()

    @property
    def dereferenced_value_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "dereferenced_value_color", fallback="GREY").upper()

    @property
    def dereferenced_register_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "dereferenced_register_color", fallback="BLUE").upper()

    @property
    def frame_argument_name_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "frame_argument_name_color", fallback="YELLOW").upper()
    
    @property
    def read_memory_address_color(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "read_memory_address_color", fallback="CYAN").upper()

    def __init__(self):
        self.supported_colors = [color.name for color in TERM_COLORS]
        self.supported_colors.remove(TERM_COLORS.ENDC.name)
        super().__init__()

    def validate_settings(self, setting=None) -> bool:
        """
        Validate settings by attempting to retrieve all properties thus executing any ConfigParser coverters
        Check all colors are valid options
        """
        settings_names = LLEFColorSettings._get_setting_names()

        if setting:
            if setting not in settings_names:
                output_line(f"Invalid LLEF setting {setting}")
                return False
            settings_names = [setting]

        valid = True
        for setting_name in settings_names:
            try:
                value = getattr(self, setting_name)
                if value not in self.supported_colors:
                    raise ValueError
            except ValueError:
                valid = False
                raw_value = self._RAW_CONFIG.get(self.GLOBAL_SECTION, setting_name)
                output_line(f"Error parsing setting {setting_name}. Invalid value '{raw_value}'")
        return valid

    def list(self):
        """
        List all color settings and their current values, colored appropriately
        """
        supported_colours_strings = []
        for color in self.supported_colors:
            supported_colours_strings.append(f"{TERM_COLORS[color].value}{color}{TERM_COLORS.ENDC.value}")
        output_line(f"Supported Colors: {', '.join(supported_colours_strings)}\n")

        settings_names = self._get_setting_names()
        for setting_name in settings_names:
            color = getattr(self, setting_name)
            output_line(f"{setting_name}={TERM_COLORS[color].value}{color}{TERM_COLORS.ENDC.value}")
