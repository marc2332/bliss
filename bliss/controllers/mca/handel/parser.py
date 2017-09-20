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


def dword(array, index, bitsize=16):
    return array[index] | array[index + 1] << bitsize


def parse_mapping_buffer(raw):
    spectrums, statistics = {}, {}

    # Header advance
    header = raw[0:256]
    current = 256

    # Header parsing
    assert header[0] == 0x55AA
    assert header[1] == 0xAA55
    assert header[2] == 0x100
    mapping_mode = header[3]
    buffer_index = dword(header, 4)
    buffer_id = header[7]
    pixel_number = header[8]
    starting_pixel = dword(header, 9)
    module_serial_number = header[11]
    channel_ids = header[12:20:2]
    channel_detector_ids = header[13:20:2]

    # Checks
    assert mapping_mode == 1  # MCA mapping mode
    assert starting_pixel == dword(raw, 256 + 4)
    assert buffer_id in (0, 1)

    # Unused information, should we do something with it?
    buffer_index, module_serial_number, channel_detector_ids

    # Iterate over pixels
    for _ in range(pixel_number):

        # Pixel header advance
        pixel_header = raw[current : current + 256]
        current += 256

        # Pixel header parsing
        assert pixel_header[0] == 0x33CC
        assert pixel_header[1] == 0xCC33
        assert pixel_header[2] == 0x100
        assert pixel_header[3] == mapping_mode
        pixel = dword(pixel_header, 4)
        total_size = dword(pixel_header, 6)
        sizes = pixel_header[8:12]

        # Statistics block
        stats_block = [
            [dword(pixel_header, 32 + 8 * i + 2 * j) for j in range(4)]
            for i in range(4)
        ]

        # Iterate over channels
        spectrums[pixel] = {}
        statistics[pixel] = {}
        remaining = total_size - 256
        for index, channel_id, size in zip(range(4), channel_ids, sizes):

            # Update remaining size
            assert remaining >= 0
            if remaining == 0:
                break
            remaining -= size

            # Sectrum Advance
            spectrum = raw[current : current + size]
            current += size

            # Set data
            spectrums[pixel][channel_id] = spectrum
            statistics[pixel][channel_id] = tuple(stats_block[index])

        # Checks
        assert remaining == 0

    # Return results
    return spectrums, statistics
