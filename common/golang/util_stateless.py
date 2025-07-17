"""Various utility functions used for Go analysis that don't require importing LLEFState.
Mainly used for avoiding circular imports."""

import itertools
import math
from typing import Any, Iterator, Union

from lldb import UINT32_MAX, SBTarget


def file_to_load_address(target: SBTarget, addr: int) -> int:
    """
    Converts an in-file address into an in-memory address.

    :param SBTarget target: The target associated with the current process.
    :param int addr: The address as described in the binary.
    :return int: The corresponding address as it has been mapped in memory.
    """
    return target.ResolveFileAddress(addr).GetLoadAddress(target)


def read_varint(bytebuf: Any, offset: int) -> tuple[int, int]:
    """
    Reads a variable-length unsigned integer (varint) as per Go's encoding.

    :param Any bytebuf: An array-like object supporting the extraction of bytes by indexing.
    :param int offset: The offset to start reading the variable-length integer at.
    :return tuple[int, int]: A pair of the decoded value and the first unread offset (for chaining calls).
    """
    value = 0
    shift = 0

    # The number is split into 7-bit groups and encoded with the least significant group first.
    # The 8th bit tells us whether another group is coming.
    # The number is never more than 32 bits long, so 5 iterations is enough.
    # https://docs.google.com/document/d/1lyPIbmsYbXnpNj57a261hgOYVpNRcgydurVQIyZOz_o/pub
    for _ in range(5):
        b = bytebuf[offset]
        offset += 1

        # Mask off the continuation-indicating bit.
        value |= (b & 0b01111111) << shift

        if b & 0b10000000 == 0:
            break
        shift += 7
    return value & UINT32_MAX, offset


def entropy(bitstring: str) -> float:
    """
    Calculates the entropy of a short string consisting only of 0s and 1s. The string should be no more than
    1000 characters long, otherwise overly-large numbers will be generated during the calculation.
    The method examines the number of bit flips while reading left to right.

    :param str bitstring: A string over '0' and '1' of length up to 1000.
    :return float: The probability of seeing the number of bit flips (or a more unlikely result)
                   if the input were drawn from a unifom random distribution.
    """
    n = len(bitstring) - 1
    bit_changes = 0
    for i in range(1, n + 1):
        if bitstring[i - 1] != bitstring[i]:
            bit_changes += 1

    if bit_changes > n // 2:
        bit_changes = n - bit_changes
    coeffs = 0.0
    power = 0.5 ** (n - 1)
    for x in range(bit_changes + 1):
        coeffs += math.comb(n, x)
    return coeffs * power


def rate_candidate_length(length: int, threshold: float, softness: float) -> float:
    """
    Dynamic datatypes that encode their length as a field are normally not too long. If the decoded length is extremely
    large, then we probably mistook this memory for a type other than the one it actually is. This function grades the
    length of a slice or string, with an ultimately inversely proportional relationship between length and return value.

    :param int length: The candidate length of this datatype.
    :param float threshold: The maximum length that can be awarded a score of 1.0.
    :param float softness: The resistance of the returned score to decrease - higher means a longer tail in the curve.
    :return float: A float between 0.0 and 1.0.
    """

    k = threshold * softness
    return min(1.0, k / (length + k - threshold))


class LeastRecentlyAddedDictionary:
    """
    A form of least-recently-added mapping datastructure.
    The first entry to be evicted is the one that was added/modified last.
    The keys are integers in this implementation.
    """

    length: int
    capacity: int
    addition_uid: Iterator[int]

    # (key, addition_id, value). None means empty slot.
    store: list[Union[tuple[int, int, Any], None]]

    def __init__(self, capacity: int = 128):
        self.capacity = capacity
        self.store = []
        for _ in range(capacity):
            self.store.append(None)
        self.length = 0
        self.addition_uid = itertools.count()

    def __get_idx(self, key: int) -> Union[int, None]:
        """
        Internal linear search for a record with matching key.

        :param int key: The search key.
        :return Union[int, None]: If found, the index in the store. Otherwise None.
        """
        for i in range(self.capacity):
            record = self.store[i]
            if record is not None and record[0] == key:
                return i
        return None

    def __get_lra(self) -> int:
        """
        Precondition: self.length > 0.
        Finds the least-recently-added entry in the store.

        :return int: The index of the least-recently-added entry.
        """
        # Precondition: self.length > 0
        lowest_uid: Union[int, None] = None
        lowest_uid_index = None
        for i in range(self.capacity):
            record = self.store[i]
            if record is not None and (lowest_uid is None or record[1] < lowest_uid):
                lowest_uid = record[1]
                lowest_uid_index = i

        # lowest_uid_index is always not None by precondition.
        if lowest_uid_index is not None:
            return lowest_uid_index
        else:
            return 0

    def add(self, key: int, val: Any) -> None:
        """
        Equivalent to Python's dict[key] = val. Will silently overwrite a LRA entry if out of room.

        :param int key: The key to add the value against.
        :param Any val: The value to add against the key.
        """
        uid = next(self.addition_uid)
        record = (key, uid, val)

        if self.length == 0:
            # Empty dict
            self.store[0] = record
            self.length += 1
        else:
            # Other entries in dict
            index = self.__get_idx(key)
            if index is not None:
                # Already present: overwrite but bump the added time
                self.store[index] = record
            else:
                # Not already present.
                if self.length < self.capacity:
                    # There's a free space somewhere
                    spot = self.store.index(None)
                    self.store[spot] = record
                    self.length += 1
                else:
                    # At capacity: evict the LRA.
                    lra_index = self.__get_lra()
                    self.store[lra_index] = record

    def delete(self, key: int) -> None:
        """
        Equivalent to Python's del dict[key]. Fails silently if key not in dict.

        :param int key: The key to delete.
        """
        position = self.__get_idx(key)
        if position is not None:
            self.store[position] = None
            self.length -= 1

    def search(self, key: int, default: Any = None) -> Any:
        """
        Equivalent to Python's dict.get(key, default=...).
        Will try to lookup the key, falling back to default if not present.

        :param int key: The key to search for.
        :param Any default: The value to return if the key could not be found, defaults to None
        :return Any: The value next to the given key, otherwise the default value if it could not be found.
        """
        position = self.__get_idx(key)
        if position is not None:
            # Next line is well-typed because self.__get_idx(key) ensures self.store[position] is not None.
            return self.store[position][2]  # type: ignore[index]
        else:
            return default
