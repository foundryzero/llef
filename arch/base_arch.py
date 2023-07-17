"""Base arch abstract class definition."""

from abc import ABC, abstractmethod
from typing import Dict, List


class BaseArch(ABC):
    """BaseArch abstract class definition."""

    @property
    @abstractmethod
    def bits(self) -> int:
        """Bit count property"""

    @property
    @abstractmethod
    def gpr_registers(self) -> List[str]:
        """GPR register property"""

    @property
    @abstractmethod
    def gpr_key(self) -> str:
        """GPR key property"""

    @property
    @abstractmethod
    def flag_register(self) -> str:
        """Flag register property"""

    @property
    @abstractmethod
    def flag_register_bit_masks(self) -> Dict[str, int]:
        """Flag register bit mask property"""
