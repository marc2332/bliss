import gevent
from bliss.common.event import dispatcher

class Actuator:
  def __init__(self, set_in=None, set_out=None, is_in=None, is_out=None):
    self.__set_in = set_in
    self.__set_out = set_out
    self.__is_in = is_in
    self.__is_out = is_out
    self.__in = False
    self.__out = False

  def set_in(self,timeout=5):
    # this is to know which command was asked for,
    # in case we don't have a return (no 'self.__is_in' or out)
    self.__in = True
    self.__out = False
    try:
        with gevent.Timeout(timeout):
            while True:
                self.__set_in()
                if self.is_in():
                    break
                else:
                    gevent.sleep(0.5)
    finally:
        dispatcher.send("state", self, self.state())
  def set_out(self, timeout=5):
    self.__out = True
    self.__in = False
    try:
        with gevent.Timeout(timeout):
            while True:
                self.__set_out()
                if self.is_out():
                    break
                else:
                    gevent.sleep(0.5)
    finally:
        dispatcher.send("state", self, self.state())
  def is_in(self):
    if self.__is_in is not None:
      return self.__is_in()
    else:
      if self.__is_out is not None:  
        return not self.__is_out()
      else:
        return self.__in
  def is_out(self):
    if self.__is_out is not None:
      return self.__is_out()
    else:
      if self.__is_in is not None:
        return not self.__is_in()
      else:
        return self.__out
  def state(self):
      state = ""
      if self.is_in():
          state += "IN"
      if self.is_out():
          state += "OUT"
      if not state or state == "INOUT":
          return "UNKNOWN"
      return state

class Shutter:
  def __init__(self, open=None, close=None, state=None):
    self.__open = open
    self.__close = close
    self.__state = state
    self.__opened = False
    self.__closed = False

  def open(self,timeout=5):
    # this is to know which command was asked for,
    # in case we don't have a return
    self.__opened = True
    self.__closed = False
    try:
        with gevent.Timeout(timeout):
            while True:
                self.__open()
                if self.state() == 'OPENED':
                    break
                else:
                    gevent.sleep(0.5)
    finally:
        dispatcher.send("state", self, self.state())
  def close(self, timeout=5):
    self.__opened = False
    self.__closed = True
    try:
        with gevent.Timeout(timeout):
            while True:
                self.__close()
		if self.state() == 'CLOSED':
                    break
                else:
                    gevent.sleep(0.5)
    finally:
        dispatcher.send("state", self, self.state())
  def state(self):
      if self.__state is not None:
	  return self.__state()
      else:
	  if self.__opened:
	      return "OPENED"
	  elif self.__closed:
	      return "CLOSED"
	  else:
	      return "UNKNOWN"
