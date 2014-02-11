from bliss.controllers.motor import CalcController
from bliss.common.task_utils import task, error_cleanup, cleanup

class Slits(CalcController):
  def __init__(self, *args, **kwargs):
    CalcController.__init__(self, *args, **kwargs)


  def calc_from_real(self, positions_dict):
    return { "hoffset": (positions_dict["back"] - positions_dict["front"]) / 2.0,
             "hgap": positions_dict["back"] + positions_dict["front"],
             "voffset": (positions_dict["up"] - positions_dict["down"]) / 2.0,
             "vgap": positions_dict["up"] + positions_dict["down"] }

  
  def prepare_move(self, axis, position, delta):
    if axis.match_tag("hoffset"):
      pass

