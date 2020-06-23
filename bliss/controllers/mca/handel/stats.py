"""Statistics handling."""

from warnings import warn
from collections import namedtuple

CLOCK_TICK = 320e-9

Stats = namedtuple(
    "Stats",
    "realtime trigger_livetime energy_livetime triggers events icr ocr deadtime",
)

# trigger_livetime = fast channel livetime (input)
# energy_livetime = slow channel livetime (output)


def stats_from_normal_mode(array):
    realtime = float(array[0])
    trigger_livetime = float(array[1])
    energy_livetime = float(array[2])
    triggers = int(array[3])
    events = int(array[4])  # without under/over flows
    icr = float(array[5])
    ocr = float(array[6])
    underflows = int(array[7])
    overflows = int(array[8])
    total_events = events + underflows + overflows

    # Double check the ICR computation
    expected_icr = triggers / trigger_livetime if trigger_livetime != 0 else 0.0
    if expected_icr != icr:
        msg = "ICR buffer inconsistency: {} != {} (expected/handel)"
        warn(msg.format(icr, expected_icr))

    # Double check the OCR computation
    expected_ocr = total_events / realtime if realtime != 0 else 0.0
    if expected_ocr != ocr:
        msg = "OCR buffer inconsistency: {} != {} (expected/handel)"
        warn(msg.format(ocr, expected_ocr))

    # Double check the energy_livetime computation
    expected_e_livetime = events / icr if icr != 0 else 0.0
    if expected_e_livetime != energy_livetime:
        msg = "Energy_Livetime inconsistency: {} != {}  (expected/handel)"
        warn(msg.format(energy_livetime, expected_e_livetime))

    # Note that the OCR reported by handel includes underflows and overflows,
    # while the computed OCR in the returned statistics does not.
    return make_stats(realtime, trigger_livetime, triggers, events)


def stats_from_mapping_mode(array):
    realtime = array[0] * CLOCK_TICK
    trigger_livetime = array[1] * CLOCK_TICK
    triggers = int(array[2])
    events = int(array[3])  # does not include over / undef flows ???

    return make_stats(realtime, trigger_livetime, triggers, events)


def make_stats(realtime, trigger_livetime, triggers, events):
    # ICR/OCR computation
    icr = triggers / trigger_livetime if trigger_livetime != 0 else 0.0
    ocr = events / realtime if realtime != 0 else 0.0
    # Deadtime computation
    # It's unclear whether icr=ocr=0 should result in a 0.0 or 1.0 deadtime
    # Prospect uses 0% so 0. it is.
    deadtime = 1 - float(ocr) / icr if icr != 0 else 0.0

    # no icr -> 0 ?
    energy_livetime = events / icr if icr != 0 else 0.0

    return Stats(
        realtime,
        trigger_livetime,
        energy_livetime,
        triggers,
        events,
        icr,
        ocr,
        deadtime,
    )
