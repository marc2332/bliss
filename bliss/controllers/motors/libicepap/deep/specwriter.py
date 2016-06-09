#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import copy
import numpy
#from datetime.datetime import now
from time import time, ctime
from getpass import getuser

class SpecWriter(file):
    class Scan():
        index   = None
        number  = None
        name    = None
        count_t = None
        columns = 0
        labels  = []
        points  = 0
        data    = None
        
    scan = Scan()


    def __init__(self, fname, mode = "a", application = "unknown"):
        self.scanlist = []
        self.last_scan = 0
        if not mode in ["a", "r", "a+"]:
            raise ValueError("mode string must be 'a' or 'r', not '{0}'".\
                                                         format(mode))
        mode = "ab+" if mode[0] == "a" else "rb"
        file.__init__(self, fname, mode)
        self.seek(0, os.SEEK_END)
        if mode[0] == "a" and self.tell() == 0:   # new file
            self.write("#F {0}\n".format(os.path.abspath(fname)))
            self.write("#E {0}\n".format(int(time())))
            self.write("#D {0}\n".format(ctime()))
            self.write("#C {0}  User = {1}\n".format(application, getuser()))
        self.__scan_file()


    def __scan_file(self):
        self.seek(0)
        scan = 0
        while True:
            line = self.readline()
            if not line:    # EOF
               break
            elif line.startswith("#S"):
                if scan:     # store the previous scan values in scanlist
                    self.scanlist.append((scan, name, npoints, offset))
                offset = self.tell()
                line = line[3:].strip()
                scan, d, name = line.partition(" ")
                scan = int(scan)
                name = name.strip()
                npoints = 0
                if scan > self.last_scan:
                    self.last_scan = scan
            elif line.startswith("#") or not line.strip():
                continue
            else:
                npoints += 1

        if scan:     # store the last scan values in scanlist
            self.scanlist.append((scan, name, npoints, offset))


    def getlastscan(self):
        return(self.last_scan)

    def __get_scan_index(self, scan_n):
        n = int(scan_n)
        slist = [s[0] for s in self.scanlist]
        idx = 0 if n == 0 else \
              len(self.scanlist) + n if n < 0 else \
              slist.index(n)
        if n >= len(self.scanlist):
            raise IndexError, "scan index out of range"
        return idx

    def isscan(self, scan_n):
        try:
            self.__get_scan_index(scan_n)
            return True
        except:
            return False

    def getscan(self, scan_n):
        s = self.scan
        s.index = self.__get_scan_index(scan_n)
        s.number, s.name, s.points, s.offset = self.scanlist[s.index]
        s.count_t = None
        s.labels = None
        s.columns = None
        s.data = None
        self.seek(s.offset)
        for line in self:
            if line.startswith("#S"):
                break
            elif line.startswith("#T"):
                s.count_t = float(line.split()[1])
            elif line.startswith("#L"):
                s.labels = line[2:].strip().split("  ")
            elif line.startswith("#N"):
                s.columns = int(line[3:])
            elif line.startswith("#") or not line.strip():
                continue
            else:
                data = [float(i) for i in line.split()]
                if len(data) != s.columns:
                    raise ValueError("wrong number of data values")
                else:
                    s.data = numpy.zeros((s.points, s.columns))
                    s.data[0] = data
                    n = 1
                for line in self:
                    if line.startswith("#S"):
                        break
                    elif line.startswith("#") or not line.strip():
                        continue
                    else:
                        data = [float(i) for i in line.split()]
                        s.data[n] = data
                        n += 1
                break
        return copy.deepcopy(s)

    def startscan(self, name, columns, labels, count_t = None):
        if columns <= 0:
            raise ValueError("invalid number of columns")

        if columns != len(labels):
            raise ValueError("mismatch between number of labels and columns")

        self.last_scan += 1
        s = self.scan
        s.index = -1
        s.number = self.last_scan
        s.name = name
        s.count_t = count_t
        s.columns = columns
        s.labels = labels
        s.points = 0
        s.data = None
        self.seek(0, os.SEEK_END)
        self.write("\n#S {0}  {1}\n".format(s.number, name))
        s.offset = self.tell()
        self.write("#D {0}\n".format(ctime()))
        if count_t != None:
            self.write("#T {0}\n".format(count_t))
        self.write("#N {0}\n".format(columns))
        self.write("#L {0}".format(labels[0]))
        for i in range(1, columns):
            self.write("  {0}".format(labels[i]))
        self.write("\n")
        self.scanlist.append((s.number, s.name, s.points, s.offset))
        return(s.number)

    def addpoint(self, data):
        s = self.scan
        if s.index != -1:
            raise ValueError("data can be only added to new scans")
        if len(data) != s.columns:
            raise ValueError("wrong number of data values, it should be {0}"\
                                          .format(s.columns))
        self.seek(0, os.SEEK_END)
        self.write("{0}".format(data[0]))
        for i in range(1, len(data)):
            self.write(" {0}".format(data[i]))
        self.write("\n")
        s.points += 1
        self.scanlist[-1] = (s.number, s.name, s.points, s.offset)
        dataline = numpy.array(data)
        if s.data == None:
            s.data = dataline
        else:
            s.data = numpy.vstack((s.data, dataline))

    def endscan(self):
        self.scan.index = self.__get_scan_index(-1)


#a = SpecWriter("data/wago1")
#a.get_scan(5)

