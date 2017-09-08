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
            section = line[1:-1].strip()
            dct[section] = []
        # New item
        elif line.startswith("START #"):
            item = int(line.split("#")[1])
            if item != len(dct[section]):
                msg = "Corrupted start (section {}, {} != {})"
                msg = msg.format(section, item, len(dct[section]))
                raise ValueError(msg)
            if section is None:
                msg = "Item {} outside of section"
                raise ValueError(msg.format(item))
            dct[section].append(OrderedDict())
        # End item
        elif line.startswith("END #"):
            item = int(line.split("#")[1])
            if item != len(dct[section]) - 1:
                msg = "Corrupted end (section {}, {} != {})"
                msg = msg.format(section, item, len(dct[section]) - 1)
                raise ValueError(msg)
            if section is None:
                msg = "Item {} outside of section"
                raise ValueError(msg.format(item))
            item = None
        # New pair
        elif "=" in line:
            key, value = map(str.strip, line.split("="))
            if section is None:
                msg = "Key/value pair {} outside of section"
                raise ValueError(msg.format((key, value)))
            if item is None:
                msg = "Key/value pair {} outside of item"
                raise ValueError(msg.format((key, value)))
            dct[section][item][key] = value
        # Error
        elif line:
            raise ValueError("Line not recognized: {!r}".format(line))
    # Return result
    return dct
