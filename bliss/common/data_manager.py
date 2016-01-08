from bliss.common.event import *
import datetime
import os
import numpy

DM = None

def DataManager():
    global DM
    if DM is None:
        DM = _DataManager()
    return DM


class ScanFile:

    def __init__(self, filename):
        self.scan_n = 1

        # find next scan number
        if os.path.exists(filename):
            with file(filename) as f:
                for line in iter(f.readline, ''):
                    if line.startswith("#S"):
                        self.scan_n += 1

        self.file_obj = file(filename, "a+")

    def write_header(self, scan_actuators, counters_list):
        motors_str = "  ".join([m.name for m in scan_actuators])
        cnt_str = "  ".join(["  ".join(c.name) if isinstance(c.name, list) else c.name for c in counters_list])

        self.file_obj.write(
            "\n#S %d ascan %s\n#D %s\n" %
            (self.scan_n, motors_str, datetime.datetime.now().strftime(
                "%a %b %d %H:%M:%S %Y")))
        #self.file_obj.write("#N %d\n" % (len(scan_actuators) +len(counters_list)))
        self.file_obj.write("#L %s  %s\n" % (motors_str, cnt_str))
        self.file_obj.flush()

    def write_timeheader(self, counters_list):
        cnt_str = "  ".join(["  ".join(c.name) if isinstance(c.name, list) else c.name for c in counters_list])

        self.file_obj.write(
            "\n#S %d  timescan  %s\n#D %s\n" %
            (self.scan_n, cnt_str, datetime.datetime.now().strftime(
                "%a %b %d %H:%M:%S %Y")))
        self.file_obj.write("#L Time  %s\n" % cnt_str)

    def write(self, data):
        self.file_obj.write(data)
        self.file_obj.flush()

    def close(self):
        self.file_obj.write("\n\n")
        self.file_obj.close()


class Scan:

    def __init__(
            self, filename, scan_actuators, npoints, counters_list, save_flag):
        self.n_cols = len(counters_list)+len(scan_actuators)
        self.raw_data = []
        self.save_flag = save_flag
        if self.save_flag:
            self.scanfile = ScanFile(filename)
            if scan_actuators == 'time':
                self.scanfile.write_timeheader(counters_list)
            else:
                self.scanfile.write_header(scan_actuators, counters_list)
        dispatcher.send(
            "scan_new", DataManager(),
            id(self),
            filename if save_flag else None, 'Time' if scan_actuators=='time' else [m.name for m in scan_actuators],
            npoints, [c.name for c in counters_list])

    def add(self, values_list):
        self.raw_data.append(values_list)

        if self.save_flag:
            self.scanfile.write("%s\n" % (" ".join(map(str, values_list))))
        dispatcher.send("scan_data", DataManager(), id(self), values_list)

    def end(self):
        data = numpy.array(self.raw_data, numpy.float)
        data.shape = (len(self.raw_data), self.n_cols)
        self.raw_data = []
        DataManager()._last_scan_data = data

        if self.save_flag:
            self.scanfile.close()

        dispatcher.send("scan_end", DataManager(), id(self))


class Timescan(Scan):

    def __init__(self, filename, counters_list, save_flag):
        Scan.__init__(self, filename, 'time', None, counters_list, save_flag)
        self.n_cols = len(counters_list)+1


class _DataManager(object):

    def __init__(self):
        self._last_scan_data = None

    def new_scan(self, filename, motor, npoints, counters_list, save_flag=True):
        return Scan(filename, motor, npoints, counters_list, save_flag)

    def new_timescan(self, filename, counters_list, save_flag=True):
        return Timescan(filename, counters_list, save_flag)

    def last_scan_data(self):
        return self._last_scan_data
        
