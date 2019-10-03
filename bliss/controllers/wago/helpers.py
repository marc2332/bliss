import struct
from typing import Union


def splitlines(iterable):
    """
    If a string is given it returns one line at a time
    otherwise it returns one element at a time

    Returns:
        iterator
    """
    if isinstance(iterable, str):
        for line in iterable.splitlines():
            if line:
                yield line
    else:
        for element in iterable:
            yield element


def remove_comments(iterable):
    """
    Args:
        iterable: an iterable of strings

    Returns: iterable of string epurated from:
                * comments(everything after the first #)
                * empty strings
    """
    for line in iterable:
        if "#" in line:
            l = line[: line.find("#")].rstrip()
            if l.strip():  # if is not only whitespace
                yield l
        else:
            l = line.rstrip()
            if l:
                yield l


def to_signed(num: int) -> int:
    """convert a 16 bit number to a signed representation"""
    if num >> 15:  # if is negative
        calc = -((num ^ 0xffff) + 1)  # 2 complement
        return calc
    return num


def to_unsigned(num: int) -> int:
    return num & ((1 << 16) - 1)


def word_to_2ch(in_: int) -> bytes:
    """from a 16bit word to 2 char string"""
    return bytes([in_ >> 8, in_ & 0xff]).decode()


def doubleword_to_32bit(in_):
    raise NotImplementedError


def wordarray_to_bytestring(wordarray: Union[tuple, list]) -> bytes:
    return struct.pack(f"<{str(len(wordarray))}H", *wordarray)


def bytestring_to_wordarray(bytestring: Union[None, bytes]) -> list:
    if bytestring is None:
        return []
    if isinstance(bytestring, str):
        bytestring = bytestring.encode()
    if len(bytestring) % 2:
        bytestring += b"\0"
    return struct.unpack(f">{len(bytestring)//2}H", bytestring)


def pretty_float(in_: Union[int, float]) -> Union[int, float]:
    """Converts floats to int if they are equivalent"""
    if int(in_) == in_:
        return int(in_)
    else:
        return in_
