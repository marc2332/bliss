# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motors.TacoMaxe import TacoMaxe

class Aerotech_Taco(TacoMaxe):
    """
    Specialisation of TacoMaxe with special command
    to control aerotech controller A3200
    """
    
    ENCODER_DIVIDER_PARAMETER = 209
    
    def __init__(self, name, config, axes, encoders):
        TacoMaxe.__init__(self, name, config, axes, encoders)
        
    def initialize_hardware(self):
        #enable encoder output
        self.device.DevWriteProg("ENCODER OUT X ON 7,8")
        self.device.DevExecProg(0)

    def initialize_hardware_axis(self, axis):
        encoder_divider = axis.config.get("encoder_divider",int)
        self.device.DevSetParam((axis.channel,
                                 self.ENCODER_DIVIDER_PARAMETER,
                                 0,encoder_divider))
        axis.encoder_divider = encoder_divider

    def start_jog(self, axis, velocity, direction):
        acceleration = axis.acceleration()
        self.device.DevSetContinuous((axis.channel,
                                      1,
                                      direction,
                                      velocity,
                                      acceleration))

    def stop_jog(self, axis):
        self.device.DevSetContinuous((axis.channel,
                                      0,
                                      0,
                                      0,
                                      0))
