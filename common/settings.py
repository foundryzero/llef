"""Global settings module"""
import configparser
import os

from common.singleton import Singleton

LLEF_CONFIG_PATH = f"{os.path.expanduser('~')}/.llef"
GLOBAL_SECTION = "LLEF"


class LLEFSettings(metaclass=Singleton):
    """
    Global settings class - loaded from file defined in `LLEF_CONFIG_PATH`
    """
    _RAW_CONFIG: configparser.ConfigParser = configparser.ConfigParser()

    @property
    def colour_output(self):
        return self._RAW_CONFIG.getboolean(GLOBAL_SECTION, "colour_output", fallback=True)

    def __init__(self):
        if not os.path.isfile(LLEF_CONFIG_PATH):
            return

        print(f"Loading LLEF settings from {LLEF_CONFIG_PATH}")

        self._RAW_CONFIG.read(LLEF_CONFIG_PATH)

        if not self._RAW_CONFIG.has_section(GLOBAL_SECTION):
            print("Settings file missing 'LLEF' section. No settings loaded.")

    def set(self, setting: str, value: str):
        """
        Set a LLEF setting
        """
        if not hasattr(self, setting):
            print(f"Invalid LLEF setting {setting}")

        # TODO add type checking here otherwise an unrecoverable exception
        # loop occurs if the wrong type is parsed from the provided string

        self._RAW_CONFIG.set(GLOBAL_SECTION, setting, value)
        print(f"Set {setting} to {getattr(self, setting)}")

    def save(self):
        """
        Save LLEF setting to file defined in `LLEF_CONFIG_PATH`
        """
        with open(LLEF_CONFIG_PATH, "w") as configfile:
            self._RAW_CONFIG.write(configfile)
