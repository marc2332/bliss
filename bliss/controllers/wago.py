# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import gevent
import types
import ctypes
import sys
import struct
import socket
from bliss.common.measurement import CounterBase
from bliss.common.utils import add_property
from bliss.comm.modbus import ModbusTcp

WAGO_CONTROLLERS = {}
DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT, N_CHANNELS, READING_TYPE, READING_INFO, WRITING_INFO = (0,1,2,3,4,5,6,7)
MODULES_CONFIG = { "750-402" : [4,0,0,0,4, "none"],
                   "750-408" : [4,0,0,0,4, "none"],
                   "750-409" : [4,0,0,0,4, "none"], 
                   "750-414" : [4,0,0,0,4, "none"],
                   "750-430" : [8,0,0,0,8, "none"],
                   "750-1417": [8,0,0,0,8, "none"],
                   "750-436" : [8,0,0,0,8, "none"],
                   "750-430" : [8,0,0,0,8, "none"],
                   "750-502" : [0,2,0,0,2, "none"],
                   "750-513" : [0,2,0,0,2, "none"],
                   "750-517" : [0,2,0,0,2, "none"],
                   "750-504" : [0,4,0,0,4, "none"],
                   "750-516" : [0,4,0,0,4, "none"],
                   "750-530" : [0,8,0,0,8, "none"], 
                   "750-1515": [0,8,0,0,8, "none"], 
                   "750-457" : [0,0,4,0,4, "fs10"],
                   "750-467" : [0,0,2,0,2, "fs10"],
                   "750-476" : [0,0,2,0,2, "fs10"],
                   "750-479" : [0,0,2,0,2, "fs10"],
                   "750-550" : [0,0,0,2,2, "fs10"],
                   "750-492" : [0,0,2,0,2, "fs4-20"],
                   "750-554" : [0,0,0,2,2, "fs4-20"],
                   "750-630" : [0,0,2,0,1, "ssi24"],
                   "750-461" : [0,0,2,0,2, "thc"],
                   "750-469" : [0,0,2,0,2, "thc"] }

def get_module_info(module_name):
  return MODULES_CONFIG[module_name]

# go through catalogue entries and update 'reading info'
for module_name, module_info in MODULES_CONFIG.iteritems():
    reading_info = {}
    module_info.append(reading_info)

    reading_type = module_info[READING_TYPE]
    if reading_type.startswith('fs'):
        module_info[READING_TYPE]="fs"
        try:
            fs_low, fs_high = map(int, reading_type[2:].split("-"))
        except:
            fs_low = 0
            fs_high = int(reading_type[2:])
        else:
            if fs_low != 0:
                fs_high -= fs_low
        
        reading_info["low"] = fs_low
        reading_info["high"] = fs_high
        if module_name.endswith("477"):
            reading_info["base"] = 20000
        elif module_name.endswith("562-UP"):
            reading_info["base"] = 65535
        else:
            reading_info["base"] = 32768       
    elif reading_type.startswith("ssi"):
        module_info[READING_TYPE]="ssi"
        reading_info["bits"] = int(reading_type[3:])
    elif reading_type.startswith("thc"):
        module_info[READING_TYPE]="thc"
        reading_info["bits"] = 16

def WagoController(host):
    """Return _WagoController instance, unique for a particular host"""

    with gevent.Timeout(3):
        fqdn = socket.getfqdn(host)

    try:
       wc = WAGO_CONTROLLERS[fqdn]
    except KeyError:
       wc = _WagoController(fqdn)
       WAGO_CONTROLLERS[fqdn]=wc

    return wc

class _WagoController:
    def __init__(self, host):
        self.client = ModbusTcp(host)
        self.modules = []
        self.firmware = { "date": None, "version":None }
        self.coupler = False
        self.mapping = []
        self.lock = gevent.lock.Semaphore()

    def connect(self):
        with self.lock:
          # check if we have a coupler or a controller
          reply = self.client.read_input_registers(0x2012, 'H')
          self.coupler = reply < 800
          if not self.coupler:
              # get firmware date and version
              reply = self.client.read_input_registers(0x2010,'H')
              self.firmware['version'] = reply
              reply = struct.pack('16H',*self.client.read_input_registers(0x2022,'16H'))
              self.firmware['date'] = '/'.join((x for x in reply.split('\x00') if x))

    def close(self):
      with self.lock:
          self.client.close()
      
    def set_mapping(self, mapping_str, ignore_missing=False):
        i = 0
        digi_out_base = 0
        ana_out_base = 0
        self.mapping = []
        self.modules = []
        for line in mapping_str.split("\n"):
            items = [item.strip() for item in filter(None, line.split(","))]
            if items:
                module_name = items[0]
                if not module_name in MODULES_CONFIG:
                    raise RuntimeError("Unknown module: %r" % module_name)
                self.modules.append(module_name)
                channels = items[1:]
                channels_map = []
                module_info = get_module_info(module_name)
                if channels:
                    # if channels are specified, check it corresponds to the number
                    # of available channels
                    if module_info[N_CHANNELS] != len(channels):
                        if not ignore_missing:
                            raise RuntimeError("Missing mapped channels on module %d: %r" % (i+1, module_name))
                    for j in (DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT):
                        channels_map.append([])
                        for k in range(module_info[j]):
                            if module_info[N_CHANNELS] == 1:
                              channels_map[-1].append(channels[0])
                            else:
                              try:
                                channels_map[-1].append(channels.pop(0))
                              except IndexError:
                                if ignore_missing:
                                    pass
                                else:
                                    raise
                self.mapping.append({"module": module_name,
                                     "channels": channels_map,
                                     "writing_info": { DIGI_OUT: digi_out_base, ANA_OUT: ana_out_base },
                                     "n_channels": module_info[N_CHANNELS]})
                digi_out_base += module_info[DIGI_OUT]
                ana_out_base += module_info[ANA_OUT]
                i+=1

    def _read_fs(self, raw_value, low=0, high=10, base=32768):
      # full-scale conversion
      value = ctypes.c_short(raw_value).value
      return (value * high / float(base)) + low

    def _read_ssi(self, raw_value, bits=24):
      #reading is two words, 16 bits each
      #the return value is 24 bits precision, signed float
      value = raw_value[0] + raw_value[1]*(1L<<16)
      value &= ((1L<<bits)-1)
      if (value & (1L<<(bits-1))):
        value -= (1L<<bits)
      return [float(value)]

    def _read_thc(self, raw_value, bits=16):
      #the return value is signed float
      value = ctypes.c_ushort(raw_value).value
      value &= ((1L<<bits)-1)
      if (value & (1L<<(bits-1))):
            value -= (1L<<bits)
      return value/10.0

    def _read_value(self, raw_value, read_table):
        reading_type = read_table[READING_TYPE]
        reading_info = read_table[READING_INFO]
        if reading_type == "fs":
            return self._read_fs(raw_value, **reading_info)
        elif reading_type == "ssi":
            return self._read_ssi(raw_value, **reading_info)
        elif reading_type == "thc":
            return self._read_thc(raw_value, **reading_info)
        return raw_value
  
    def read_phys(self, modules_to_read):
        # modules_to_read has to be a sorted list
        ret = []; read_table = []
        total_digi_in, total_digi_out, total_ana_in, total_ana_out = 0,0,0,0
        read_digi_in, read_digi_out, read_ana_in, read_ana_out = False,False,False,False

        for module_index, module in enumerate(self.mapping):
            module_name = module["module"]
            try:
                module_info = get_module_info(module_name)
            except KeyError:
                raise RuntimeError("Cannot read module %d: unknown module %r" % (module_index, module_name))
            n_digi_in = module_info[DIGI_IN]
            n_digi_out = module_info[DIGI_OUT]
            n_ana_in = module_info[ANA_IN]
            n_ana_out = module_info[ANA_OUT]

            if module_index in modules_to_read:
                read_table.append({ DIGI_IN: None, 
                                    DIGI_OUT: None, 
                                    ANA_IN: None, 
                                    ANA_OUT: None,
                                    READING_TYPE: module_info[READING_TYPE],
                                    READING_INFO: module_info[READING_INFO] })

                if n_digi_in > 0:
                    read_table[-1][DIGI_IN]=(total_digi_in, n_digi_in)
                    read_digi_in = True
                if n_digi_out > 0:
                    read_table[-1][DIGI_OUT]=(total_digi_out, n_digi_out)
                    read_digi_out = True
                if n_ana_in > 0:
                    read_table[-1][ANA_IN]=(total_ana_in, n_ana_in)
                    read_ana_in = True
                if n_ana_out > 0:
                    read_table[-1][ANA_OUT]=(total_ana_out, n_ana_out)
                    read_ana_out = True

            total_digi_in += n_digi_in
            total_digi_out += n_digi_out
            total_ana_in += n_ana_in
            total_ana_out += n_ana_out

        if read_digi_in:
            digi_in_reading = self.client.read_coils( 0, total_digi_in)
        if total_digi_out > 0:
            digi_out_reading = self.client.read_coils(0x200, total_digi_out)
        if total_ana_in > 0:
            ana_in_reading = self.client.read_input_registers(0, total_ana_in * 'H')
        if total_ana_out > 0:
            ana_out_reading = self.client.read_input_registers(0x200, total_ana_in * 'H')
        
        for module_read_table in read_table:
            readings = []

            try:
                i, n = module_read_table[DIGI_IN]
            except:
                readings.append(None)
            else:
                readings.append(tuple(digi_in_reading[i:i+n])) 
            
            try:
                i, n = module_read_table[DIGI_OUT]
            except:
                readings.append(None)
            else:
                readings.append(tuple(digi_out_reading[i:i+n])) 

            try:
                i, n = module_read_table[ANA_IN]
            except:
                readings.append(None)
            else:
                raw_values = ana_in_reading[i:i+n]
                if module_read_table[READING_TYPE] == 'ssi':
                  readings.append(tuple(self._read_value(raw_values, module_read_table)))
                else:
                  readings.append(tuple((self._read_value(x, module_read_table) for x in raw_values)))
 
            try:
                i, n = module_read_table[ANA_OUT]
            except:
                readings.append(None)
            else:
                raw_values = ana_out_reading[i:i+n]
                readings.append(tuple((self._read_value(x, module_read_table) for x in raw_values))) 

            ret.append(tuple(readings))

        return tuple(ret)

    def get(self, *channel_names):
        modules_to_read = set()
        channels_to_read = []
        ret = []
        for channel_name in channel_names:
            # find module(s) corresponding to given channel name
            # if multiple channels have the same name, they will all be retrieved
            for i, mapping_info in enumerate(self.mapping):
                channels_map = mapping_info["channels"]
                if channels_map:
                    for j in (DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT):
                        if channel_name in channels_map[j]:
                            modules_to_read.add(i)
                            channels_to_read.append([])
                            if mapping_info["n_channels"] == 1:
                              channels_map[j] = [channels_map[j][0]]
                            for k, chan in enumerate(channels_map[j]):
                                if chan == channel_name:
                                    channels_to_read[-1].append((i, j, k))
        modules_to_read_list = list(modules_to_read)
        modules_to_read_list.sort()
        # read from the wago
        with self.lock:
            readings = self.read_phys(modules_to_read_list)

        if len(readings ) == 0:
          return None

        # deal with read values
        for channel_to_read in channels_to_read:
            values = []
            for i, j, k in channel_to_read:
                i = modules_to_read_list.index(i)
                values.append(readings[i][j][k])
            if len(channel_to_read) > 1:
                ret.append(values)
            else:
                ret += values
        # the return value type depends on what is returned;
        # this is evil! But it gives more friendly results
        # when used from the command line interface
        if len(ret) == 0:
            return None
        elif len(ret) == 1:
            return ret[0]
        else:
            return ret
        
    def _write_fs(self, value, low=0, high=10, base=32768):
        return int(((value - low) * base / float(high)))& 0xffff

    def write_phys(self, write_table):
        # write_table is a dict of module_index: [(type_index, channel_index, value_to_write), ...]
        for module_index, write_info in write_table.iteritems():
            module_info = get_module_info(self.modules[module_index])
            for type_index, channel_index, value2write in write_info:
                if type_index == DIGI_OUT:
                    addr = self.mapping[module_index]["writing_info"][DIGI_OUT]+channel_index
                    write_value = True if value2write else False
                    self.client.write_coil(addr, write_value) 
                elif type_index == ANA_OUT:
                    addr = self.mapping[module_index]["writing_info"][ANA_OUT]+channel_index
                    writing_type = module_info[READING_TYPE]
                    if writing_type == "fs":
                        write_value = self._write_fs(value2write, **module_info[READING_INFO])
                    else:
                        raise RuntimeError("Writing %r is not supported" % writing_type)
                    self.client.write_register(addr,'H',write_value)

    def set(self, *args):
        # args should be list or pairs: channel_name, value
        # or a list with channel_name, val1, val2, ..., valn
        # or a combination of the two
        channels_to_write = []
        current_list = channels_to_write
        for x in args:
            if type(x) in (types.StringType, types.UnicodeType):
                # channel name
                current_list = [str(x)]
                channels_to_write.append(current_list)
            else:
                # value
                current_list.append(x)

        for i in range(len(channels_to_write)):
            x = channels_to_write[i]
            if len(x) > 2:
                # group values for channel with same name
                # in a list
                channels_to_write[i]=[x[0], x[1:]]

        write_table = {}
        n_chan = 0
        for channel_name, value in channels_to_write:
            for i, mapping_info in enumerate(self.mapping):
                channel_map = mapping_info["channels"]
                if not channel_map:
                    continue
                for j in (DIGI_IN, DIGI_OUT, ANA_IN, ANA_OUT):
                    n_channels = channel_map[j].count(channel_name)
                    if n_channels:
                        if not j in (DIGI_OUT, ANA_OUT):
                            raise RuntimeError("Cannot write: %r is not an output" % channel_name)
                        if type(value) == types.ListType:
                            if n_channels > len(value):
                                raise RuntimeError("Cannot write: not enough values for channel %r: expected %d, got %d" % (channel_name, n_channels, len(value)))
                            else:
                                idx = -1
                                for k in range(n_channels):
                                    idx = channel_map[j].index(channel_name, idx+1)

                                    write_table.setdefault(i, []).append((j, idx, value[n_chan+k]))
                        else:
                            if n_channels > 1:
                                raise RuntimeError("Cannot write: only one value given for channel %r, expected: %d" % (channel_name, n_channels))
                            k = channel_map[j].index(channel_name)
                            write_table.setdefault(i, []).append((j, k, value))
                        n_chan += n_channels
        with self.lock:
            return self.write_phys(write_table)

    def print_plugged_modules(self):
      modules = self.client.read_holding_registers(0x2030,"65H")
      for m in modules:
        if not m: break
        if(m & 0x8000):         # digital in/out
          direction  = 'input' if m & 0x1 else 'output'
          mod_size = (m & 0xf00) >> 8
          print 'Module digital %s %s(s)' % (mod_size,direction)
        else:
          print 'Module %d' % (m)

class WagoCounter(CounterBase):
  def __init__(self, parent, name, index=None):

    if index is None:
      CounterBase.__init__(self, parent, name)
    else:
      CounterBase.__init__(self, parent, parent.name+'.'+name)
    self.index = index
    self.parent = parent
    self.cntname = name

  def __call__(self, *args, **kwargs):
    return self
 
  def read(self):
    data = self.parent._cntread()
    if isinstance(self.cntname, str):
      data = data[self.parent.cnt_dict[self.cntname]]
    return data

  def gain(self, gain=None, name=None):
    name = name or self.cntname
    try:
      name = [x for x in self.parent.counter_gain_names if str(name) in x][0]
    except IndexError:
      #raise RuntimeError"Cannot find %s in the %s mapping" % (name, self.parent.name))
      return None

    if gain:
      valarr = [False]*3
      valarr[gain-1] = True 
      self.parent.set(name,valarr)
    else:
      valarr = self.parent.get(name)
      if isinstance(valarr, list) and True in valarr:
        return (valarr.index(True)+1)
      else:
        return 0


class wago(object):
  def __init__(self, name, config_tree):

    self.name = name
    self.wago_ip = config_tree["controller_ip"]
    self.controller = None
    self.mapping = ""
    mapping = []
    for module in config_tree["mapping"]:
      module_type = module["type"]
      logical_names = module["logical_names"]
      mapping.append("%s,%s" % (module_type, logical_names))
    self.mapping = "\n".join(mapping)

    self.cnt_dict = {}
    self.cnt_names = []
    self.cnt_gain_names = []
    
    try:
      self.counter_gain_names = config_tree["counter_gain_names"].replace(" ","").split(',')
    except:
      pass

    try:
      self.cnt_names = config_tree["counter_names"].replace(" ","").split(',')
    except:
      pass
    else:
      for i, name in enumerate(self.cnt_names):
        self.cnt_dict[name] = i
        add_property(self, name, WagoCounter(self, name, i))

  def connect(self):
    self.controller = WagoController(self.wago_ip)
    self.controller.set_mapping(self.mapping)

  def _safety_check(self, *args):
    return True

  def set(self, *args, **kwargs):
    if not self._safety_check(*args):
      return
    if self.controller is None:
      self.connect()
    return self.controller.set(*args, **kwargs)

  def get(self, *args, **kwargs):
    if self.controller is None:
      self.connect()
    return self.controller.get(*args, **kwargs)

  @property
  def counters(self):
    counters_list = []
    for cnt_name in self.cnt_names: 
      counters_list.append(getattr(self, cnt_name))
    return counters_list

  def _cntread(self, acq_time=None):
    if len(self.cnt_names) == 1:
      return [self.get(*self.cnt_names)]
    else:
      return self.get(*self.cnt_names)

  def read_all(self,*counter_name):
    cnt_name = [n.replace(self.name + '.','') for n in counter_name]
    result = self.get(*cnt_name)
    return result if isinstance(result,list) else [result]
