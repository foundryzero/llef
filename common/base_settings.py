"""A base class for global settings"""

import configparser
import os
from abc import abstractmethod

from common.output_util import output_line
from common.singleton import Singleton
from common.state import LLEFState


class BaseLLEFSettings(metaclass=Singleton):
    """
    Global settings class - loaded from file defined in `LLEF_CONFIG_PATH`
    """

    LLEF_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".llef")
    GLOBAL_SECTION = "LLEF"

    _RAW_CONFIG: configparser.ConfigParser = configparser.ConfigParser()

    @classmethod
    def _get_setting_names(cls):
        return [name for name, value in vars(cls).items() if isinstance(value, property)]

    def __init__(self):
        self.state = LLEFState()
        self.load()

    @abstractmethod
    def validate_settings(self, setting=None) -> bool:
        """
        Validate settings
        """

    def load_default_settings(self):
        """
        Reset settings and use default values
        """
        self._RAW_CONFIG = configparser.ConfigParser()
        self._RAW_CONFIG.add_section(self.GLOBAL_SECTION)

    def load(self, reset=False):
        """
        Load settings from file
        """
        if reset:
            self._RAW_CONFIG = configparser.ConfigParser()

        if not os.path.isfile(self.LLEF_CONFIG_PATH):
            self.load_default_settings()
            return

        output_line(f"Loading LLEF settings from {self.LLEF_CONFIG_PATH}")

        self._RAW_CONFIG.read(self.LLEF_CONFIG_PATH)

        if not self._RAW_CONFIG.has_section(self.GLOBAL_SECTION):
            self.load_default_settings()
            output_line("Settings file missing 'LLEF' section. Default settings loaded.")

        if not self.validate_settings():
            self.load_default_settings()
            output_line("Error parsing config. Default settings loaded.")

    def list(self):
        """
        List all settings and their current values
        """
        settings_names = self._get_setting_names()
        for setting_name in settings_names:
            output_line(f"{setting_name}={getattr(self, setting_name)}")

    def save(self):
        """
        Save LLEF setting to file defined in `LLEF_CONFIG_PATH`
        """
        with open(self.LLEF_CONFIG_PATH, "w") as configfile:
            self._RAW_CONFIG.write(configfile)

    def set(self, setting: str, value: str):
        """
        Set a LLEF setting
        """
        if not hasattr(self, setting):
            output_line(f"Invalid LLEF setting {setting}")

        restore_value = getattr(self, setting)
        self._RAW_CONFIG.set(self.GLOBAL_SECTION, setting, value)

        if not self.validate_settings(setting=setting):
            self._RAW_CONFIG.set(self.GLOBAL_SECTION, setting, str(restore_value))
        else:
            output_line(f"Set {setting} to {getattr(self, setting)}")
