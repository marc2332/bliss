"""Parser for the specific XIA INI file format."""

from collections import OrderedDict


def parse_xia_ini_file(content):
    dct = OrderedDict()
    section, item = None, None
    # Loop over striped lines
    for line in content.splitlines():
        line = line.strip()
        # Comment
        if line.startswith("*"):
            pass
        # New section
        elif line.startswith("[") and line.endswith("]"):
            if item is not None:
                msg = "New section within section {} item {}"
                raise ValueError(msg.format(section, item))
            item = None
            section = line[1:-1].strip()
            dct[section] = []
        # New item
        elif line.startswith("START #"):
            if item is not None:
                msg = "New item within section {} item {}"
                raise ValueError(msg.format(section, item))
            item = int(line.split("#")[1])
            if section is None:
                msg = "Item {} outside of section"
                raise ValueError(msg.format(item))
            if item != len(dct[section]):
                msg = "Corrupted start (section {}, {} should be {})"
                msg = msg.format(section, item, len(dct[section]))
                raise ValueError(msg)
            dct[section].append(OrderedDict())
        # End item
        elif line.startswith("END #"):
            if item is None:
                msg = "End markup outside of item"
                raise ValueError(msg)
            item = int(line.split("#")[1])
            if item != len(dct[section]) - 1:
                msg = "Corrupted end (section {}, {} should be {})"
                msg = msg.format(section, item, len(dct[section]) - 1)
                raise ValueError(msg)
            item = None
        # New pair
        elif "=" in line:
            key, value = map(str.strip, line.split("="))
            if item is None:
                msg = "Key/value pair {} outside of item"
                raise ValueError(msg.format((key, value)))
            dct[section][item][key] = value
        # Error
        elif line:
            raise ValueError("Line not recognized: {!r}".format(line))
    # Return result
    return dct
