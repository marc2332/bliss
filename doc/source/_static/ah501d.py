# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""AH501D: dont forget to document"""

from bliss.controllers.emulator import BaseDevice


class AH501D(BaseDevice):
    """The AH501D Bliss emulator device"""

    DEFAULT_NEWLINE='\n'

    #: Baudrate command default value
    BDR = '921600'

    def handle_line(self, line):
        try:
            return self.__handle_line(line)
        except:
            self._log.error('Unrecognized command: %r', line)
            return 'NAK\r\n'

    def __handle_line(self, line):
        self._log.debug('received: %r', line)

        line = line.strip()
        pars = line.split()
        cmd = pars[0].upper()
        if pars[-1] == '?':  # get parameter
            value = getattr(self, cmd)
            result = '{0} {1}'.format(cmd, value)
        else:                # set parameter
            setattr(self, cmd, pars[1])
            result = 'ACK'
        result += '\r\n'

	self._log.debug('answering with: %r', result)
	return result
