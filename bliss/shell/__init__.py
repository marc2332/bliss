# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

'''Shell (:term:`CLI` and Web based)'''

import os
import sys
import time
import logging
import datetime
import functools

import louie
import numpy
from six import print_

from bliss import setup_globals
from bliss.common import event
from bliss.config import static
from bliss.scanning import scan


_log = logging.getLogger('bliss.shell')


def initialize(*session_names):
    config = static.get_config()
    user_ns = { "config": config }
    sessions = list()
    error_flag = False

    for sname in session_names:
        session = config.get(sname)

        print "%s: Executing setup..." % session.name
        
        try:
            session.setup(env_dict = user_ns, verbose = True)
        except Exception:
            error_flag = True
            sys.excepthook(*sys.exc_info())

        sessions.append(session)

    if error_flag:
        print "Warning: error(s) happened during setup, setup may not be complete."
    else:
        print "Done."

    return user_ns,sessions


def _obj_unit(name):
    config = static.get_config()
    if isinstance(name, (str, unicode)):
        try:
            obj = config.get(name)
        except:
            return ''
    else:
        obj = name
        name = obj.name
    try:
        return obj.unit or ''
    except AttributeError:
        obj_config = config.get_config(name)
        return obj_config.get('unit', '')
    

class ScanListener:
    '''listen to scan events and compose output'''

    HEADER = "Total {npoints} points, {total_acq_time} seconds\n\n" + \
             "Scan {scan_nb} {start_time_str} {root_path} " + \
             "{session_name} user = {user_name}\n" + \
             "{title}\n\n" + \
             "{column_header}"

    DEFAULT_WIDTH = 12

    def __init__(self):
        event.connect(scan, 'scan_new', self.__on_scan_new)
        event.connect(scan, 'scan_data', self.__on_scan_data)
        event.connect(scan, 'scan_end', self.__on_scan_end)

    def __on_scan_new(self, scan_info, filename, motor_names, nb_points, counter_names):
        scan_info = dict(scan_info)
        if isinstance(motor_names, str):
            motor_names = [motor_names]
        col_labels = ['#']
        for motor_name in motor_names:
            # replace time_stamp with elapsed_time
            if motor_name == 'timestamp':
                motor_name = 'dt'
                unit = 's'
            else:
                unit = _obj_unit(motor_name)
            motor_label = motor_name
            if unit:
                motor_label += '({0})'.format(unit)
            col_labels.append(motor_label)
        for counter_name in counter_names:
            counter_label = counter_name
            unit = _obj_unit(counter_name)
            if unit:
                counter_label += '({0})'.format(unit)
            col_labels.append(counter_label)
        
        self.col_labels = col_labels

        if not scan_info['save']:
            scan_info['root_path'] = '<no file>'

        if scan_info['type'] == 'ct':
            return

        col_lens = map(lambda x: max(len(x), self.DEFAULT_WIDTH), col_labels)
        h_templ = ["{{0:>{width}}}".format(width=col_len)
                   for col_len in col_lens]
        header = "  ".join([templ.format(label)
                            for templ, label in zip(h_templ, col_labels)])
        header = self.HEADER.format(column_header=header, **scan_info)
        self.col_templ = ["{{0: >{width}}}".format(width=col_len) 
                          for col_len in col_lens]
        self._point_nb = 0
        print_(header)

    def __on_scan_data(self, scan_info, values):
        elapsed_time = time.time() - scan_info['start_time_stamp']
        values = [elapsed_time] + values[1:]
        if scan_info['type'] == 'ct':
            # ct is actually a timescan(npoints=1).
            
            norm_values = numpy.array(values) / scan_info['count_time']
            col_len = max(map(len, self.col_labels)) + 2
            template = '{{label:>{0}}} = {{value: >12}} ({{norm: 12}}/s)'.format(col_len)
            lines = "\n".join([template.format(label=label, value=v, norm=nv)
                               for label, v, nv in zip(self.col_labels[1:], 
                                                      values, norm_values)])
            end_time_str = datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")
            msg = '\n{0}\n\n{1}'.format(end_time_str, lines)
            print_(msg)
        else:
            values.insert(0, self._point_nb)
            self._point_nb += 1
            line = "  ".join([self.col_templ[i].format(v) for i, v in enumerate(values)])
            print_(line)

    def __on_scan_end(self, scan_info):
        pass

