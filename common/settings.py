"""Global settings module"""
import configparser
import os

from common.singleton import Singleton

LLEF_CONFIG_PATH = os.path.join(os.path.expanduser('~'), ".llef")
GLOBAL_SECTION = "LLEF"


class LLEFSettings(metaclass=Singleton):
    """
    Global settings class - loaded from file defined in `LLEF_CONFIG_PATH`
    """
    _RAW_CONFIG: configparser.ConfigParser = configparser.ConfigParser()

    @property
    def color_output(self):
        return self._RAW_CONFIG.getboolean(GLOBAL_SECTION, "color_output", fallback=True)

    @classmethod
    def _get_setting_names(cls):
        return [name for name, value in vars(cls).items() if isinstance(value, property)]

    def __init__(self):
        self.load()

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
                raw_value = self._RAW_CONFIG.get(GLOBAL_SECTION, setting_name)
                print(f"Error parsing setting {setting_name}. Invalid value '{raw_value}'")
        return valid

    def load_default_settings(self):
        """
        Reset settings and use default values
        """
        self._RAW_CONFIG = configparser.ConfigParser()
        self._RAW_CONFIG.add_section(GLOBAL_SECTION)

    def load(self, reset=False):
        """
        Load settings from file
        """
        if reset:
            self._RAW_CONFIG = configparser.ConfigParser()

        if not os.path.isfile(LLEF_CONFIG_PATH):
            self.load_default_settings()
            return

        print(f"Loading LLEF settings from {LLEF_CONFIG_PATH}")

        self._RAW_CONFIG.read(LLEF_CONFIG_PATH)

        if not self._RAW_CONFIG.has_section(GLOBAL_SECTION):
            self.load_default_settings()
            print("Settings file missing 'LLEF' section. Default settings loaded.")

        if not self.validate_settings():
            self.load_default_settings()
            print("Error parsing config. Default settings loaded.")

    def list(self):
        """
        List all settings and their current values
        """
        settings_names = LLEFSettings._get_setting_names()
        for setting_name in settings_names:
            print(f"{setting_name}={getattr(self, setting_name)}")

    def save(self):
        """
        Save LLEF setting to file defined in `LLEF_CONFIG_PATH`
        """
        with open(LLEF_CONFIG_PATH, "w") as configfile:
            self._RAW_CONFIG.write(configfile)

    def set(self, setting: str, value: str):
        """
        Set a LLEF setting
        """
        if not hasattr(self, setting):
            print(f"Invalid LLEF setting {setting}")

        restore_value = getattr(self, setting)
        self._RAW_CONFIG.set(GLOBAL_SECTION, setting, value)

        if not self.validate_settings(setting=setting):
            self._RAW_CONFIG.set(GLOBAL_SECTION, setting, str(restore_value))
        else:
            print(f"Set {setting} to {getattr(self, setting)}")

