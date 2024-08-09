"""Global settings module"""
import os

from arch import supported_arch
from common.singleton import Singleton
from common.base_settings import BaseLLEFSettings


class LLEFSettings(BaseLLEFSettings, metaclass=Singleton):
    """
    Global general settings class - loaded from file defined in `LLEF_CONFIG_PATH`
    """

    LLEF_CONFIG_PATH = os.path.join(os.path.expanduser('~'), ".llef")
    GLOBAL_SECTION = "LLEF"

    @property
    def color_output(self):
        return self._RAW_CONFIG.getboolean(self.GLOBAL_SECTION, "color_output", fallback=True)

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

    def validate_settings(self, setting=None) -> bool:
        """
        Validate settings by attempting to retrieve all properties thus executing any ConfigParser coverters
        """
        settings_names = LLEFSettings._get_setting_names()

        if setting:
            if setting not in settings_names:
                print(f"Invalid LLEF setting {setting}")
                return False
            settings_names = [setting]

        valid = True
        for setting_name in settings_names:
            try:
                getattr(self, setting_name)
            except ValueError:
                valid = False
                raw_value = self._RAW_CONFIG.get(self.GLOBAL_SECTION, setting_name)
                print(f"Error parsing setting {setting_name}. Invalid value '{raw_value}'")
        return valid
