"""De Bruijn sequence utilities."""

import itertools
from collections.abc import Iterator


def de_bruijn(alphabet: bytearray, n: int) -> Iterator[int]:
    """
    Generate De Bruijn sequence for alphabet and subsequences of length n (for compatibility. w/ pwnlib).
    Taken from GEF gef.py L3728 (2022.06).
    """

    k = len(alphabet)
    a = [0] * k * n

    def db(t: int, p: int) -> Iterator[int]:
        if t > n:
            if n % p == 0:
                for j in range(1, p + 1):
                    yield alphabet[a[j]]
        else:
            a[t] = a[t - p]
            yield from db(t + 1, p)

            for j in range(a[t - p] + 1, k):
                a[t] = j
                yield from db(t + 1, t)

    return db(1, 1)


def generate_cyclic_pattern(length: int, cycle: int = 4) -> bytearray:
    """
    Create a @length byte bytearray of a de Bruijn cyclic pattern.
    Taken from GEF gef.py L3749 (2022.06)
    """
    charset = bytearray(b"abcdefghijklmnopqrstuvwxyz")
    return bytearray(itertools.islice(de_bruijn(charset, cycle), length))
