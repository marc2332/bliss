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

import numpy
from six import print_
from blessings import Terminal

from bliss import setup_globals
from bliss.config import static
from bliss.scanning import scan
from bliss.common.event import dispatcher

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


class ScanListener:
    '''listen to scan events and compose output'''

    HEADER = "Total {npoints} points, {total_acq_time} seconds\n\n" + \
             "Scan {scan_nb} {start_time_str} {root_path} " + \
             "{session_name} user = {user_name}\n" + \
             "{title}\n\n" + \
             "{column_header}"

    DEFAULT_WIDTH = 12

    def __init__(self):
        dispatcher.connect(self.__on_scan_new, 'scan_new', scan)
        dispatcher.connect(self.__on_scan_data, 'scan_data', scan)
        dispatcher.connect(self.__on_scan_end, 'scan_end', scan)

    def __on_scan_new(self, scan_info):
        scan_info = dict(scan_info)
        self.term = term = Terminal(scan_info.get('stream'))
        
        motors = scan_info['motors']
        counters = scan_info['counters']
        nb_points = scan_info['npoints']
        col_labels = ['#']
        real_motors = []
        for motor in motors:
            motor_name = motor.name
            # replace time_stamp with elapsed_time
            if motor_name == 'timestamp':
                motor_name = 'dt'
                unit = 's'
            else:
                real_motors.append(motor)
                if term.is_a_tty:
                    dispatcher.connect(self.__on_motor_position_changed,
                                       signal='position', sender=motor)
                unit = motor.config.get('unit', default=None)
            motor_label = motor_name
            if unit:
                motor_label += '({0})'.format(unit)
            col_labels.append(motor_label)

        for counter in counters:
            counter_label = counter.name
            unit = counter.config.get('unit', None)
            if unit:
                counter_label += '({0})'.format(unit)
            col_labels.append(counter_label)
        
        self.col_labels = col_labels
        self.real_motors = real_motors
        self._point_nb = 0

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
            if self.term.is_a_tty:
                print_(self.term.clear_bol + '\r', end='')
            print_(line)

    def __on_scan_end(self, scan_info):
        if scan_info['type'] == 'ct':
            return

        for motor in self.real_motors:
            dispatcher.disconnect(self.__on_motor_position_changed, 
                                  signal='position', sender=motor)

    def __on_motor_position_changed(self, position, signal=None, sender=None):
        labels = []
        for motor in self.real_motors:
            position = '{0:.03f}'.format(motor.position())
            unit = motor.config.get('unit', default=None)
            if unit:
                position += unit
            labels.append('{0}: {1}'.format(motor.name, position))

        print_(self.term.clear_bol + '\r', end='')
        print_(*labels, sep=', ', end='', flush=True)
