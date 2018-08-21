# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.musst import musst

config = {
    "gpib_url": "prologix://148.79.215.54:1234",
    "gpib_pad": 13,
    "gpib_timeout": 8.0,
    "gpib_eos": "\r\n",
}
for i in range(10):
    dev = musst("bm26_musst", config)
    print "Loop ", i
    print dev.STATE
    print dev.TMRCFG
    print dev.DBINFO
    print dev.INFO
    program = "// The internal timebase is set to 1 MHz\nUNSIGNED USEC\nPROG\nTIMER = 0\nCTSTART TIMER\nFOR USEC FROM 10 TO 10000000 STEP 10\n@TIMER = USEC\nAT TIMER DO ATRIG\nENDFOR\nENDPROG"
    dev.upload_program(program)
    print dev.STATE
    print dev.LISTVAR
    print dev.get_event_buffer_size()
    print dev.get_event_memory_pointer()
    print dev.NAME
    print dev.TIMER
