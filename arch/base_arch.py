"""Base arch abstract class definition."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class FlagRegister:
    """FlagRegister dataclass to store register name / bitmask associations"""
    name: str
    bit_masks: Dict[str, int]


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
    def flag_registers(self) -> List[FlagRegister]:
        """List of flag registers with associated bit masks"""
