"""Helpers specific to the mapping mode."""

from .stats import stats_from_mapping_mode


def dword(array, index, bitsize=16):
    """Extract a dword value from two words starting at the given index."""
    return array[index] | array[index + 1] << bitsize


def parse_mapping_buffer(raw):
    """Parse the given mapping buffer and return a (spectrums, statistics) tuple.

    Both results are dictionaries of dictionaries, first indexed by pixel,
    then channels:
    - spectrums: <pixel: <channel: spectrum (1D array)>
    - statistics: <pixel: <channel: stats (Stats object)>
    """
    spectrums, statistics = {}, {}

    # XMAP/Mercury parsing
    if raw[1] == 0:
        raw = raw[::2]
        spectrum_type = "uint16"
    # FalconX parsing
    else:
        spectrum_type = "uint32"

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
            spectrum.dtype = spectrum_type
            current += size

            # Discard garbage
            if channel_id in spectrums[pixel]:
                continue

            # Set data
            stats = stats_from_mapping_mode(stats_block[index])
            spectrums[pixel][channel_id] = spectrum
            statistics[pixel][channel_id] = stats

        # Checks
        assert remaining == 0

    # Return results
    return spectrums, statistics
