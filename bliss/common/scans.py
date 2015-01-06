from bliss.common.task_utils import *
import numpy
import gevent
from .data_manager import DataManager
import time
import logging

SCANFILE = "/dev/null"

def set_scanfile(filename):
  global SCANFILE
  SCANFILE = filename

def ascan(motor, start, stop, npoints, count_time, *counters, **kwargs):
  save_flag = kwargs.get("save", True)
  raw_data = []
    
  dm = DataManager()
  dm.set_save_flag(save_flag)

  filename = kwargs.get("filename", SCANFILE)

  logging.getLogger().info("Scanning %s from %f to %f in %d points" % \
                               (motor.name, start, stop, npoints))

  motors = [motor]
  scan = dm.new_scan(filename, motors, npoints, counters)
  
  start_pos = motor.position()
  def scan_cleanup():
    print "Returning motor %s to %f" % (motor.name, start_pos)
    motor.move(start_pos)
    scan.end()

  motor.move(start)
  ipoint = 0
  countlabellen = len("{0:d}".format(npoints))
  countformatstr = "{0:"+ "{0:d}".format(countlabellen) +"d}"
  
  with error_cleanup(scan_cleanup):
    for position in numpy.linspace(start, stop, npoints):
      ipoint = ipoint +1
      countlabel = "("+ "{0:3d}".format(ipoint) +"/"+ "{0:3d}".format(npoints) +")"
      countlabel = "("+ countformatstr.format(ipoint) +"/"+ countformatstr.format(npoints) +")"
      #print "  ", countlabel, "moving", motor.name, "to", '{0:+.6f}'.format(position), ":",
      motor.move(float(position))

      acquisitions = []
      values = [position]
      for counter in counters:
        acquisitions.append(gevent.spawn(counter.read, count_time))

      gevent.joinall(acquisitions)

      values.extend([a.get() for a in acquisitions])
      raw_data.append(values)
      #print values
      scan.add(values) 
 
  scan.end()
  
  data = numpy.array(raw_data, numpy.float)
  data.shape = (len(raw_data), len(counters)+1)
  return data

def dscan(motor, start, stop, npoints, count_time, *counters, **kwargs):

  oldpos = motor.position()
  scandat = ascan(motor, oldpos+start, oldpos+stop, npoints, count_time, *counters, **kwargs)

  return scandat

def a2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time, *counters, **kwargs):
  save_flag = kwargs.get("save", True)
  raw_data = []
    
  dm = DataManager()
  dm.set_save_flag(save_flag)
  filename = kwargs.get("filename", SCANFILE)

  logging.getLogger().info("Scanning %s from %f to %f and %s from %f to %f in %d points" % (motor1.name, start1, stop1, motor2.name, start2, stop2, npoints))

  motors = [motor1, motor2]
  scan = dm.new_scan(filename, motors, npoints, counters)
  start_pos1 = motor1.position()
  start_pos2 = motor2.position()
  def scan_cleanup():
    logging.getLogger().info("Returning motor %s to %f and motor %s to %f" % (motor1.name, start_pos1, motor2.name, start_pos2))
    motor1.move(start_pos1)
    motor2.move(start_pos2)
    scan.end()

  motor1.move(start1)
  motor2.move(start2)
  ipoint = 0
  countlabellen = len("{0:d}".format(npoints))
  countformatstr = "{0:"+ "{0:d}".format(countlabellen) +"d}"

  s1 = numpy.linspace(start1, stop1, npoints)
  s2 = numpy.linspace(start2, stop2, npoints)
  with error_cleanup(scan_cleanup):
      for ii in range(npoints):
          ipoint = ipoint +1
          motor1.move(s1[ii], wait=False)
          motor2.move(s2[ii], wait=False)
          motor1.wait_move()
          motor2.wait_move()
 
          acquisitions = []
          values = [m.position() for m in (motor1,motor2)]
          for counter in counters:
              acquisitions.append(gevent.spawn(counter.read, count_time))

          gevent.joinall(acquisitions)
          values.extend([a.get() for a in acquisitions])
          raw_data.append(values)
          #print values
          scan.add(values) 
 
  scan.end()
  
  data = numpy.array(raw_data, numpy.float)
  data.shape = (len(raw_data), len(counters)+2)
  return data

def d2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time, *counters, **kwargs):

  oldpos1 = motor1.position()
  oldpos2 = motor2.position()

  scandat = a2scan(motor1, oldpos1+start1, oldpos1_stop1, motor2, oldpos2+start2, oldpos2+stop2, npoints, count_time, *counters, **kwargs)
  return scandat

def timescan(*counters, **kwargs):
  save_flag = kwargs.get("save", True)
  raw_data = []
    
  dm = DataManager()
  dm.set_save_flag(save_flag)
  filename = kwargs.get("filename", SCANFILE)

  count_time = kwargs.get("count_time", 1)
  sleep_time = kwargs.get("sleep_time", 0)
  npoints = kwargs.get("npoints", 0)
  
  logging.getLogger().info("Doing timescan ")
  scan = dm.new_timescan(filename, counters)

  def scan_cleanup():
    scan.end()

  t0 = time.time()
  with error_cleanup(scan_cleanup):
    while True: 
      acquisitions = []
      tt = time.time() - t0
      values = [tt]
      for counter in counters:
        acquisitions.append(gevent.spawn(counter.read, count_time))

      gevent.joinall(acquisitions)

      values.extend([a.get() for a in acquisitions])
      raw_data.append(values)
      scan.add(values)
      npoints -= 1
      if npoints == 0:
        break
      time.sleep(sleep_time)

  scan.end()
  
  data = numpy.array(raw_data, numpy.float)
  data.shape = (len(raw_data), len(counters)+1)
  return data

