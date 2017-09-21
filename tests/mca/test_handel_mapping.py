"""Test module for mapping mode helpers."""

from bliss.controllers.mca.handel.stats import Stats, stats_from_mapping_mode
from bliss.controllers.mca.handel.mapping import parse_mapping_buffer


def test_stats_from_mapping_mode():
    expected = Stats(
        realtime=0.032,
        livetime=0.016,
        triggers=100,
        events=50,
        icr=6250.0,
        ocr=1562.5,
        deadtime=0.75,
    )
    assert stats_from_mapping_mode([10e4, 5e4, 100, 50]) == expected


def test_parse_mapping_buffer():
    raw = [0] * 0x300
    # Header
    raw[0] = 0x55AA  # Token
    raw[1] = 0xAA55  # Token
    raw[2] = 0x100  # Header size
    raw[3] = 0x1  # Mapping mode
    raw[8] = 0x1  # Number of pixel
    raw[9] = 0x1  # Starting pixel
    raw[12] = 0x2  # First channel ID
    # Pixel header
    raw[0x100 + 0] = 0x33CC  # Token
    raw[0x100 + 1] = 0xCC33  # Token
    raw[0x100 + 2] = 0x100  # Pixel header size
    raw[0x100 + 3] = 0x1  # Mapping mode
    raw[0x100 + 4] = 0x1  # Pixel id
    raw[0x100 + 6] = 0x200  # Total spectrum size
    raw[0x100 + 8] = 0x100  # First channel spectrum size
    # Statistics
    raw[0x120 + 0 : 0x120 + 8 : 2] = [1, 2, 3, 4]
    # Spectrum
    raw[0x200:0x300] = range(256)
    # Test
    spectrums, stats = parse_mapping_buffer(raw)
    assert spectrums == {1: {2: list(range(256))}}
    assert stats == {1: {2: stats_from_mapping_mode([1, 2, 3, 4])}}
