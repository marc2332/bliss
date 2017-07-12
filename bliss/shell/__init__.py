# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

'''Shell (:term:`CLI` and Web based)'''

import os
import yaml
import sys
import logging
import functools
from six import print_
import numpy
import datetime

from bliss import setup_globals
from bliss.scanning import scan
from bliss.common import event

try:
    from bliss.config import static
except ImportError:
    sys.excepthook(*sys.exc_info())

try:
    from tabulate import tabulate
except ImportError:
    pass

_log = logging.getLogger('bliss.shell')

def initialize(*session_names):
    config = static.get_config()
    user_ns = { "config": config }
    sessions = list()

    for sname in session_names:
        session = config.get(sname)

        print "%s: Executing setup..." % session.name
        
        try:
            session.setup(env_dict = user_ns, verbose = True)
        except Exception:
            sys.excepthook(*sys.exc_info())

        sessions.append(session)

    print "Done."

    return user_ns,sessions

class ScanListener:
    '''listen to scan events and compose output'''

    HEADER = "Total {npoints} points, {total_acq_time} seconds\n\n" + \
             "Scan {scan_nb} {start_time_str} {root_path} " + \
             "{session_name} user = {user_name}\n" + \
             "{title}\n\n" + \
             "{column_header}"

    def __init__(self):
        event.connect(scan, 'scan_new', self.__on_scan_new)
        event.connect(scan, 'scan_data', self.__on_scan_data)
        event.connect(scan, 'scan_end', self.__on_scan_end)

    def __on_scan_new(self, scan_info, filename, motor_names, nb_points, counter_names):
        if scan_info['type'] == 'ct':
            return
        if isinstance(motor_names, str):
            motor_names = [motor_names]
        col_names = motor_names + counter_names
        point_nb_col_len = len(str(nb_points-1)) + 1 if nb_points else 6
        col_lens = map(len, col_names)
        col_templs = ["{{0:>{0}}}".format(min(col_len, 8)) for col_len in col_lens]
        col_names.insert(0, '#')
        col_templs.insert(0, "{{0:>{0}}}".format(point_nb_col_len))
        col_header = "  ".join([col_templs[i].format(m) for i, m in enumerate(col_names)])
        header = self.HEADER.format(column_header=col_header,**scan_info)
        self.col_templs = ["{{0:>{0}g}}".format(min(col_len, 8)) for col_len in col_lens]
        self.col_templs.insert(0, "{{0:>{0}g}}".format(point_nb_col_len))
        self._point_nb = 0
        print_(header)

    def __on_scan_data(self, scan_info, values):
        if scan_info['type'] == 'ct':
            # ct is actually a timescan(npoints=1).
            names, values = scan_info['counter_names'], values
            # First value is elapsed time since timescan started. We don't need it here
            values = values[1:]
            norm_values = numpy.array(values) / scan_info['count_time']
            col_len = max(map(len, names)) + 2
            template = '{{0:>{0}}} = {{1: 10g}} ({{2: 10g}}/s)'.format(col_len)
            lines = "\n".join([template.format(name, v, nv)
                               for name, v, nv in zip(names, values, norm_values)])
            end_time_str = datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")
            msg = '\n{0}\n\n{1}'.format(end_time_str, lines)
            print_(msg)
        else:
            values = [self._point_nb] + values
            self._point_nb += 1
            line = "  ".join([self.col_templs[i].format(v) for i, v in enumerate(values)])
            print_(line)

    def __on_scan_end(self, scan_info):
        pass

