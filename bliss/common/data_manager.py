from bliss.common.event import *
import datetime
import os

DM = None

def DataManager():
  global DM
  if DM is None:
    DM = DataManager()
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

  def write_header(self, scannable, counters_list):
    self.file_obj.write("\n#S %d\n#D %s\n" % (self.scan_n, datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")))
    self.file_obj.write("#N %d\n" % len(counters_list))
    motors  = "  ".join([m.name for m in scannable])
    self.file_obj.write("#L %s  %s\n" % (motors, "  ".join([c.name for c in counters_list])))
    self.file_obj.flush()

  def write_timeheader(self, counters_list):
    self.file_obj.write("\n#S %d\n#D %s\n" % (self.scan_n, datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")))
    self.file_obj.write("#N %d\n" % len(counters_list))
    self.file_obj.write("#L Time  %s\n" % ("  ".join([c.name for c in counters_list])))

  def write(self, data):
    self.file_obj.write(data)
    self.file_obj.flush()

  def close(self):
    self.file_obj.write("\n\n")
    self.file_obj.close()

class Scan:
  def __init__(self, filename, scannable, npoints, counters_list, save_flag):
    self.save_flag = save_flag
    if self.save_flag:
        self.scanfile = ScanFile(filename)
        if scannable == 'time':
            self.scanfile.write_timeheader(counters_list)
        else:
            self.scanfile.write_header(scannable, counters_list)
    dispatcher.send("scan_new", DM, id(self), filename if save_flag else None, scannable, npoints, counters_list)
    
  def add(self, values_list):
    if self.save_flag:
        self.scanfile.write("%s\n" % (" ".join(map(str, values_list))))
    dispatcher.send("scan_data", DM, id(self), values_list)

  def end(self):
    if self.save_flag:
        self.scanfile.close()
    dispatcher.send("scan_end", DM, id(self))

class Timescan(Scan):
  def __init__(self, filename, counters_list, save_flag):
    Scan.__init__(self, filename, 'time', None, counters_list, save_flag)

class DataManager:
  def __init__(self):
    pass 

  def new_scan(self, filename, motor,  npoints, counters_list, save_flag=True):
    return Scan(filename, motor, npoints, counters_list, save_flag)

  def new_timescan(self, filename, counters_list, save_flag=True):
    return Timescan(filename, counters_list, save_flag)
