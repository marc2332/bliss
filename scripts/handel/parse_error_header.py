"""Generate error dict from the handel error header."""

import re
import sys
import pprint


def parse(filename="handel_errors.h"):
    with open(filename) as f:
        header = f.read()
    error_dct = {}
    pattern = r"#define(\s+)XIA_(\w+)(\s+)(\w+)(\s+)"
    for m in re.finditer(pattern, header):
        value, key = m.group(2, 4)
        error_dct[int(key)] = (value, None)
    pattern = r"#define(\s+)XIA_(\w+)(\s+)(\w+)(\s+)\/\*\*(\s+)([^\*]*)\*\/"
    for m in re.finditer(pattern, header):
        value, key, msg = m.group(2, 4, 7)
        msg = " ".join(filter(None, msg.split()))
        error_dct[int(key)] = (value, msg)
    return error_dct


def main(args=None):
    if args is None or len(args) < 2:
        dct = parse()
    else:
        dct = parse(args[1])
    pprint.pprint(dct)


if __name__ == "__main__":
    main(sys.argv)
