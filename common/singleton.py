"""Singleton module"""

from typing import Any


class Singleton(type):
    """
    Singleton class implementation. Use with metaclass=Singleton.
    """

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
