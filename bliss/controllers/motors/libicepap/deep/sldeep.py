#import pySerial



# --------------------------------------------------------------------------
#
class SLDeep:

  # ------------------------------------------------------------------------
  #
  def __init__(self, sl, verbose=1):
    self.log("object created, serial line: \"%s\""%sl)

    # at this point we should have every thing we need
    self.sl_name  = sl

    # get options TODO: check their value
    self.verbose = verbose

    # TODO: try to open the serial line and raise an exception otherwise
    raise IOError,"unable to open serial line \"%s\""%sl



  # ------------------------------------------------------------------------
  #
  def log(self,msg):
    print "      %s: %s"%(__name__,msg)



  # ------------------------------------------------------------------------
  #
  def __del__(self):
    self.log("object deleted, serial line: \"%s\""%self.sl_name)
    



