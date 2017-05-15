# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import struct
from warnings import warn

from bliss.comm.util import get_comm, get_comm_type, SERIAL, TCP
from bliss.common.greenlet_utils import KillMask,protect_from_kill
OPIOM_PRG_ROOT='/users/blissadm/local/isg/opiom'

class Opiom:
    FSIZE = 256

    def __init__(self,name,config_tree):
        self.name = name

        comm_type = None
        try:
            comm_type = get_comm_type(config_tree)
            comm_config = config_tree
        except:
            if "serial" in config_tree:
                comm_type = SERIAL
                comm_config = dict(tcp=dict(url=config_tree['serial']))
                warn("'serial: <url>' is deprecated. " \
                     "Use 'serial: url: <url>' instead", DeprecationWarning)
            elif "socket" in config_tree:
                comm_type = TCP
                comm_config = dict(serial=dict(url=config_tree['socket']))
                warn("'socket: <url>' is deprecated. " \
                     "Use 'tcp: url: <url>' instead", DeprecationWarning)
            else:
                raise RuntimeError("opiom: need to specify a communication url")

        if comm_type not in (SERIAL, TCP):
            raise TypeError('opiom: invalid communication type %r' % comm_type)

        self._cnx = get_comm(comm_config, ctype=comm_type, timeout=3)
        self._cnx.flush()
        self.__program = config_tree['program']
        self.__base_path = config_tree.get('opiom_prg_root',OPIOM_PRG_ROOT)
        self.__debug = False
        try:
            msg = self.comm("?VER",timeout=50e-3)
        except serial.SerialTimeout:
            msg = self.comm("?VER",timeout=50e-3)
            
        if not msg.startswith('OPIOM') :
            raise IOError("No opiom connected at %s" % serial)
        self.comm("MODE normal")

    def __repr__(self) :
        return "Opiom : %s with program %s" % (self._cnx,self.__program)

    def setDebug(self, flag) :
        self.__debug = flag is True

    def getDebug(self):
        return self.__debug

    def __debugMsg(self, wr, msg):
        if self.__debug:
            print "%-5.5s on %s > %s"%(wr, self.name, msg)

    def info(self) :
        return self.comm("?INFO")

    def source(self) :
        return self.comm("?SRC")

    def prog(self) :
        info = self.info()
        for line in info.split('\n') :
            if line.startswith('PLD prog:') :
                return line.split(':')[1].strip('\n\t ')

    def error(self) :
        return self.comm("?ERR")

    def registers(self) :
        return {'IM':int(self.comm("?IM"),base=16),
                'IMA':int(self.comm("?IMA"),base=16)}

    def inputs_stat(self) :
        input_front = int(self.comm("?I"),base=16)
        input_back = int(self.comm("?IB"),base=16)

        self._display_bits('I',input_front)
        self._display_bits('IB',input_back)

    def outputs_stat(self) :
        output_front = int(self.comm("?O"),base=16)
        output_back = int(self.comm("?OB"),base=16)

        self._display_bits('O',output_front)
        self._display_bits('OB',output_back)

    def raw_write(self,msg) :
        self._cnx.write(msg)

    def raw_bin_write(self,binmsg):
        nb_block = len(binmsg) / self.FSIZE
        nb_bytes = len(binmsg) % self.FSIZE
        lrc = (nb_bytes + nb_block + sum([ord(x) for x in binmsg])) & 0xff
        rawMsg = struct.pack('BBB%dsBB' % len(binmsg),0xff,nb_block,nb_bytes,
                             binmsg,lrc,13)
        self._cnx.write(rawMsg)

    def comm_ack(self,msg) :
        return self.comm('#' + msg)

    @protect_from_kill
    def comm(self,msg,timeout = None) :
        self._cnx.open()
        with self._cnx._lock:
            self._cnx._write(msg + '\r\n')
            if msg.startswith('?') or msg.startswith('#') :
                msg = self._cnx._readline(timeout = timeout)
                if msg.startswith('$') :
                    msg = self._cnx._readline('$\r\n',timeout = timeout)
                self.__debugMsg("Read", msg.strip('\n\r'))
                return msg.strip('\r\n')
                

    def load_program(self) :
        pldid = self.comm("?PLDID")
        file_pldid,file_project = self._getFilePLDIDandPROJECT()
        if file_pldid and file_pldid != pldid:
            print "Load program:",self.__program
            srcsz = int(self.comm("?SRCSZ").split()[0])
            offsets,opmfile = self._getoffset()
            if((offsets["src_c"] - offsets["src_cc"]) < srcsz) :
                SRCST = offsets["src_cc"]
                srcsz = offsets["src_c"] - offsets["src_cc"]
            else:
                SRCST = offsets["src_c"]
                srcsz = offsets["jed"] - offsets["src_c"]
            binsz = offsets['size'] - offsets['jed']


            sendarray = opmfile[SRCST:SRCST+srcsz]
            sendarray += opmfile[offsets["jed"]:]

            if self.comm_ack("MODE program") != "OK" :
                raise IOError("Can't program opiom %s" % str(self))

            if self.comm_ack('PROG %d %d %d %d "%s"' % (binsz,srcsz,self.FSIZE,
                                                        int(file_pldid),
                                                        file_project)) != "OK" :
                self.comm("MODE normal")
                raise IOError("Can't start programming opiom %s" % str(self))

            for frame_n,index in enumerate(range(0,len(sendarray),self.FSIZE)) :
                with KillMask():
                    self.raw_write("#*FRM %d\r" % frame_n)
                    self.raw_bin_write(sendarray[index:index+self.FSIZE])
                    answer = self._cnx.readline('\r\n')
                    if(answer != "OK") : break

            #waiting end programming
            while 1:
                stat_num = self.comm("?PSTAT")
                self.__debugMsg("Load", stat_num)
                try:
                    stat,percent = stat_num.split()
                except ValueError:
                    stat = stat_num
                    break
            return stat == "DONE"
        
    def _display_bits(self,prefix,bits) :
        for i in range(1,9) :
            print "%s%d\t" % (prefix,i),
        print
        for i in range(8):
            if((bits >> i) & 0x1) :
                print "1\t",
            else:
                print "0\t",

        print

    def _getoffset(self) :
        f = file(os.path.join(self.__base_path,self.__program + '.opm'))
        line = f.read(14)
        f.seek(0)
        opmfile = f.read()
        size = f.tell()
        header,src,src_cc,src_c,jed = struct.unpack('<5H',line[3:13])
        return {'header' : header,'src' : src,
                'src_cc': src_cc,'src_c' : src_c,
                'jed' :jed,'size':size},opmfile

    def _getFilePLDIDandPROJECT(self) :
        TOKEN = '#pldid#'
        PROJECT_TOKEN= '#project#'

        f = file(os.path.join(self.__base_path,self.__program + '.opm'))
        begin = -1
        for line in f:
            begin = line.find(TOKEN)
            if begin > -1:
                break
        if begin > -1 :
            subline = line[begin + len(TOKEN):]
            end = subline.find(TOKEN)
            pldid = subline[:end]

            begin = line.find(PROJECT_TOKEN)
            subline = line[begin + len(PROJECT_TOKEN):]
            project = subline[:subline.find(PROJECT_TOKEN)]
            return pldid,project
