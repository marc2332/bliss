#!/usr/bin/env python
import re
import sys

replaces = [
    ("\._set_position\(\)", "._set_position"),
    ("\.measured_position\(\)", ".measured_position"),
    ("\.dial_measured_position\(\)", ".dial_measured_position"),
    ("\.dial\(\)", ".dial"),
    (r"\.dial\((.+?)\)", r".dial = \1"),
    ("\.position\(\)", ".position"),
    (r"\.position\((.+?)\)", r".position = \1"),
    ("\.state\(\)", ".state"),
    ("\.state\(read_hw=True\)", ".hw_state"),
    ("\._hw_position\(\)", "._hw_position"),
    # velocity
    ("\.velocity\(\)", ".velocity"),
    ("\.velocity\(from_config=True\)", ".config_velocity"),
    (r"\.velocity\(new_velocity=(.+?)\)", r".velocity = \1"),
    (r"\.velocity\((.+?)\)", r".velocity = \1"),
    # acceleration
    ("\.acceleration\(\)", ".acceleration"),
    ("\.acceleration\(from_config=True\)", ".config_acceleration"),
    (r"\.acceleration\(new_acc=(.+?)\)", r".acceleration = \1"),
    (r"\.acceleration\((.+?)\)", r".acceleration = \1"),
    # acctime
    ("\.acctime\(\)", ".acctime"),
    ("\.acctime\(from_config=True\)", ".config_acctime"),
    (r"\.acctime\(new_acctime=(.+?)\)", r".acctime = \1"),
    (r"\.acctime\((.+?)\)", r".acctime = \1"),
    # limits
    ("\.limits\(\)\[0\]", ".low_limit"),
    ("\.limits\(\)\[1\]", ".high_limit"),
    ("\.limits\(\)", ".limits"),
    ("\.limits\(from_config=True\)", ".config_limits"),
    (r"\.limits\(low_limit=(.+?), +high_limit=(.+?)\)", r".limits = \1,\2"),
    (r"\.limits\((.+?), +(.+?)\)", r".limits = \1,\2"),
    (r"\.limits\(low_limit=(.+?)\)", r".low_limit = \1"),
    (r"\.limits\(high_limit=(.+?)\)", r".high_limits = \1"),
    (r"\.limits\(new_limits=(.+?)\)", r".limits = \1"),
    (r"\.limits\((.+?)\)", r".limits = \1"),
]
if not sys.argv[1:]:
    print(
        "Usage %s <file_names>\n\n"
        "This script will sed all axis methods "
        "which change to properties" % sys.argv[0]
    )

for filename in sys.argv[1:]:
    with open(filename, "rb") as f:
        lines = [l.decode() for l in f.readlines()]
    with open(filename, "w") as f:
        for line in lines:
            for pattern, repl in replaces:
                line = re.sub(pattern, repl, line)
            f.write(line)
