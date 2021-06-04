# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from .pi_e51x import PI_E51X

"""
Bliss controller for ethernet PI E518 piezo controller.
This controller inherits all methods from PI_E51X.
Only the methods not common to E517 and E518 are redefined here:
   * gating.
"""


class PI_E518(PI_E51X):
    def __init__(self, *args, **kwargs):
        PI_E51X.__init__(self, *args, **kwargs)
        self.model = "E518"

    """
    CTO?

    1 1=+0000.1000    ???
    1 2=1             ???
    1 3=3             trigger mode
    1 4=0             ???
    1 5=+0000.0000    min threshold
    1 6=+0001.0000    max threshold
    1 7=1             polarity
    1 12=1            ???
    ...
    """

    def set_gate(self, axis, state):
        """
        CTO  [<TrigOutID> <CTOPam> <Value>]+
         - <TrigOutID> : {1, 2, 3}
         - <CTOPam> :
             - 3: trigger mode
                 - <Value>: {0, 2, 4, 6, 9, 11, 12}
                     - 0: position distance
                     - 2: OnTarget
                     - 4: Wave Generator
                     - 6: InMotion
                     - 9: GeneratorPulseTrigger
                     - 11: GeneratorEdgeTrigger
                     - 12: OnTargetSingleTrigger
             - 5:
             - 6:
             - 7: polarity
                 - Values:  {0, 1}


        ex :      ID  trigmod  polarity
              CTO 1   7        0
              CTO 1   7        1

        Args:
            - <state> : bool
        Returns:
            - None
        Raises:
            ?
        """

        # print "gate %s on axis channel %d  %f" % (state , self.gate_axis.channel, time.time())
        if state:
            _cmd = "CTO %d 7 1" % (axis.channel)
        else:
            _cmd = "CTO %d 7 0" % (axis.channel)

        self.command(_cmd)
