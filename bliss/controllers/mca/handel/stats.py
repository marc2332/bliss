"""Statistics handling."""

from warnings import warn
from collections import namedtuple

CLOCK_TICK = 320e-9

Stats = namedtuple("Stats", "realtime livetime triggers events icr ocr deadtime")


def stats_from_normal_mode(array):
    realtime = float(array[0])
    livetime = float(array[1])
    triggers = int(array[3])
    events = int(array[4])
    icr = float(array[5])
    ocr = float(array[6])
    underflows = int(array[7])
    overflows = int(array[8])
    total_events = events + underflows + overflows

    # Double check the ICR computation
    expected_icr = triggers / livetime if livetime != 0 else 0.0
    if expected_icr != icr:
        msg = "ICR buffer inconsistency: {} != {} (expected)"
        warn(msg.format(icr, expected_icr))

    # Double check the OCR computation
    expected_ocr = total_events / realtime if realtime != 0 else 0.0
    if expected_ocr != ocr:
        msg = "OCR buffer inconsistency: {} != {} (expected)"
        warn(msg.format(ocr, expected_ocr))

    # Note that the OCR reported by handel include underflows and overflows,
    # while the computed OCR in the returned statistics does not.
    return make_stats(realtime, livetime, triggers, events)


def stats_from_mapping_mode(array):
    realtime = array[0] * CLOCK_TICK
    livetime = array[1] * CLOCK_TICK
    triggers = int(array[2])
    events = int(array[3])
    return make_stats(realtime, livetime, triggers, events)


def make_stats(realtime, livetime, triggers, events):
    # ICR/OCR computation
    icr = triggers / livetime if livetime != 0 else 0.0
    ocr = events / realtime if realtime != 0 else 0.0
    # Deadtime computation
    # It's unclear whether icr=ocr=0 should result in a 0.0 or 1.0 deadtime
    # Prospect uses 0% so 0. it is.
    deadtime = 1 - float(ocr) / icr if icr != 0 else 0.0
    return Stats(realtime, livetime, triggers, events, icr, ocr, deadtime)
