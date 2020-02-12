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


def to_signed(num: int, bits=16) -> int:
    """convert a 16 bit number to a signed representation"""
    if num >> (bits - 1):  # if is negative
        calc = -((num ^ ((1 << bits) - 1)) + 1)  # 2 complement
        return calc
    return num


def to_unsigned(num: int, bits=16) -> int:
    return num & ((1 << bits) - 1)


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


def register_type_to_int(type_str: Union[str, bytes, int]) -> int:
    try:
        return int(type_str)
    except ValueError:
        pass
    if isinstance(type_str, str):
        type_str = type_str.encode()
    if type_str not in (b"IW", b"IB", b"OW", b"OB"):
        raise TypeError("Given type should be one of these: 'IB' 'OB' 'IW' 'OW'")
    return (type_str[0] << 8) + type_str[1]


def int_to_register_type(word: Union[str, int]) -> str:
    if word == 0x4942:
        return "IB"  # input binary
    elif word == 0x4f42:
        return "OB"  # output binary
    elif word == 0x4f57:
        return "OW"  # output word
    elif word == 0x4957:
        return "IW"  # input word
    elif word in ("IB", "OB", "OW", "IW"):
        return word
    else:
        raise RuntimeError("Wrong I/O type: (ex: ('I'<<8 + 'W') )")
