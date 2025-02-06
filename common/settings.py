"""Global settings module"""

import os

from lldb import SBDebugger

from arch import supported_arch
from common.base_settings import BaseLLEFSettings
from common.constants import MSG_TYPE
from common.output_util import output_line, print_message
from common.singleton import Singleton


class LLEFSettings(BaseLLEFSettings, metaclass=Singleton):
    """
    Global general settings class - loaded from file defined in `LLEF_CONFIG_PATH`
    """

    LLEF_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".llef")
    GLOBAL_SECTION = "LLEF"
    DEFAUL_OUTPUT_ORDER = "registers,stack,code,threads,trace"
    debugger: SBDebugger = None

    @property
    def color_output(self):
        default = False
        if self.debugger is not None:
            default = self.debugger.GetUseColor()
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "color_output", fallback=default)

    @property
    def register_coloring(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "register_coloring", fallback=True)

    @property
    def show_legend(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "show_legend", fallback=True)

    @property
    def show_registers(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "show_registers", fallback=True)

    @property
    def show_stack(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "show_stack", fallback=True)

    @property
    def show_code(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "show_code", fallback=True)

    @property
    def show_threads(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "show_threads", fallback=True)

    @property
    def show_trace(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "show_trace", fallback=True)

    @property
    def force_arch(self):
        arch = self._RAW_CONFIG.get(self.GLOBAL_SECTION, "force_arch", fallback=None)
        return None if arch not in supported_arch else arch

    @property
    def rebase_addresses(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "rebase_addresses", fallback=True)

    @property
    def rebase_offset(self):
        return self._RAW_CONFIG.getint(self.GLOBAL_SECTION, "rebase_offset", fallback=0x100000)

    @property
    def show_all_registers(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "show_all_registers", fallback=False)

    @property
    def output_order(self):
        return self._RAW_CONFIG.get(self.GLOBAL_SECTION, "output_order", fallback=self.DEFAUL_OUTPUT_ORDER)

    @property
    def truncate_output(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "truncate_output", fallback=True)

    def validate_output_order(self, value: str):
        default_sections = self.DEFAUL_OUTPUT_ORDER.split(",")
        sections = value.split(",")
        if len(sections) != len(default_sections):
            raise ValueError(f"Requires {len(default_sections)} elements: '{','.join(default_sections)}'")

        missing_sections = []
        for section in default_sections:
            if section not in sections:
                missing_sections.append(section)

        if len(missing_sections) > 0:
            raise ValueError(f"Missing '{','.join(missing_sections)}' from output order.")

    def validate_settings(self, setting=None) -> bool:
        """
        Validate settings by attempting to retrieve all properties thus executing any ConfigParser coverters
        """
        settings_names = LLEFSettings._get_setting_names()

        if setting:
            if setting not in settings_names:
                output_line(f"Invalid LLEF setting {setting}")
                return False
            settings_names = [setting]

        valid = True
        for setting_name in settings_names:
            try:
                value = getattr(self, setting_name)
                if (
                    setting_name == "color_output"
                    and value is True
                    and self.debugger is not None
                    and self.debugger.GetUseColor() is False
                ):
                    raise ValueError("Colour is not supported by your terminal")

                elif setting_name == "output_order":
                    self.validate_output_order(value)
            except ValueError as e:
                valid = False
                print_message(MSG_TYPE.ERROR, f"Invalid value for {setting_name}. {e}")
        return valid

    def __init__(self, debugger: SBDebugger):
        super().__init__()
        self.debugger = debugger

    def set(self, setting: str, value: str):
        super().set(setting, value)

        if setting == "color_output":
            self.state.change_use_color(self.color_output)
        elif setting == "truncate_output":
            self.state.change_truncate_output(self.truncate_output)

    def load(self, reset=False):
        super().load(reset)
        self.state.change_use_color(self.color_output)
        self.state.change_truncate_output(self.truncate_output)
