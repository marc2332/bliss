from bliss.common.scans import *
from bliss.common.task_utils import task, cleanup, error_cleanup
from bliss.common.event import dispatcher

def load_config():
    import sys
    from bliss.config import static
    from bliss.shell.interpreter import globals

    cfg = static.get_config()

    for item_name in cfg.names_list:
        print "Initializing '%s`" % item_name
        try:
            o = cfg.get(item_name)
        except:
            sys.excepthook(*sys.exc_info())
        else:
            setattr(globals, item_name, o)
            del o

class InOut:
  def __init__(self, set_in=None, set_out=None, is_in=None, is_out=None, state=None):
    self.__set_in = set_in
    self.__set_out = set_out
    self.__is_in = is_in
    self.__is_out = is_out
    self.__in = None
    self.__out = None
    self.__state = state

  def set_in(self):
    self.__in = self.__set_in()
    dispatcher.send("state", self, "IN" if self.__in else "OUT")
    return self.__in
  def set_out(self):
    self.__out = self.__set_out()
    dispatcher.send("state", self, "OUT" if self.__out else "IN")
    return self.__out
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
    if self.__state is not None:
      return self.__state()
    else:
      if self.__in is None and self.__out is None:
        return "UNKNOWN"
      else:
        return "IN" if self.is_in() else "OUT"
