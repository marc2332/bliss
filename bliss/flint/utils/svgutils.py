# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy


def parse_path(string: str):
    """
    Parse a path definition and convert it to a list of polygonal chain.

    It does not support commands C, S, Q, T, A.

    Returns:
        - A list of polygonal chain
    """
    polylines = []
    points = None
    previous_point = numpy.array([0, 0])
    tokens = string.split(" ")
    while len(tokens) > 0:
        token = tokens.pop(0)
        char = token[0]
        if "A" <= char <= "z":
            code = char
            if len(token) > 1:
                tokens.insert(0, token[1:])

            if code in ["z", "Z"]:
                points.append(points[0])
                continue

            point = tokens.pop(0)
        else:
            point = token

        point = [float(p) for p in point.split(",")]
        point = numpy.array(point)
        if code == "M":
            points = []
            polylines.append(points)
            new_point = point
            code = "L"
        elif code == "m":
            points = []
            polylines.append(points)
            new_point = point
            code = "l"
        elif code == "H":
            new_point = previous_point.copy()
            new_point[0] = point[0]
        elif code == "h":
            new_point = previous_point.copy()
            new_point[0] += point[0]
        elif code == "V":
            new_point = previous_point.copy()
            new_point[1] = point[0]
        elif code == "v":
            new_point = previous_point.copy()
            new_point[1] += point[0]
        elif code == "L":
            new_point = point
        elif code == "l":
            new_point = previous_point.copy()
            new_point += point
        else:
            raise ValueError("Unsupported command '%s'" % code)
        points.append(new_point)
        previous_point = new_point
    return polylines
