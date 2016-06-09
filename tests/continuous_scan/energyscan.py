# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.continuous_scan import AcquisitionChain
from bliss.common.continuous_scan import Scan
from bliss.common.data_manager import DataManager
from bliss.acquisition.musst import MusstAcquisitionDevice
from bliss.acquisition.motor import MotorMaster

def energyscan(start,end,npoints):
  mstart = energy.controller.calc_to_real(start)
  mend = energy.controller.calc_to_real(end)
  delta = abs(mend - mstart)/float(npoints)*mono.encoder.steps_per_unit
  mdelta = int(delta/mono.encoder.steps_per_unit)
  npoints = (delta*npoints/int(delta)) - 1 

  chain = AcquisitionChain()
 
  musst_acq_dev = MusstAcquisitionDevice(musst, 
                                         program = "monoscan.mprg", 
                                         store_list = ["timer","ch2","ch3"],
                                         vars = {"e1": mstart * mono.encoder.steps_per_unit, 
                                                 "e2": mend * mono.encoder.steps_per_unit, 
                                                 "de": mdelta, 
                                                 "monoangle": mono.position() * mono.encoder.steps_per_unit,
                                                 "npoints": npoints})

  master = MotorMaster(mono, start, end)
  # in this case, prepare can be done in parallel, is it always the case?
  # if yes, the code can be optimized
  chain.add(master, musst_acq_dev)

  cscan = Scan(DataManager())
  cscan.set_acquisition_chain(chain)
  cscan.prepare()
  
  return cscan.start()
