# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import datetime
from bliss.common.data_manager import DataNode,to_timestamp
import pickle

def _transform_dict_obj(dict_object) :
    return_dict = dict()
    for key,value in dict_object.iteritems():
        return_dict[key] = _transform(value)
    return return_dict

def _transform_iterable_obj(iterable_obj):
    return_list = list()
    for value in iterable_obj:
        return_list.append(_transform(value))
    return return_list

def _transform_obj_2_name(obj):
    return obj.name if hasattr(obj,'name') else obj

def _transform(var):
    if isinstance(var,dict):
        var = _transform_dict_obj(var)
    elif isinstance(var,(tuple,list)):
        var = _transform_iterable_obj(var)
    else:
        var = _transform_obj_2_name(var)
    return var
        
def pickle_dump(var):
    var = _transform(var)
    return pickle.dumps(var)


class Scan(DataNode):
    def __init__(self,name,create=False,**keys):
        DataNode.__init__(self,'scan',name,create=create,**keys)
        self.__create = create
        if create:
            self._data.start_time = start_time = datetime.datetime.now()
            self._data.start_time_str = start_time.strftime("%a %b %d %H:%M:%S %Y")
            self.start_time_stamp = to_timestamp(start_time)
        self._info._write_type_conversion = pickle_dump

    def end(self):
        if self.__create:
            end_time = datetime.datetime.now()
            self._data.end_time = end_time
            self._data.end_time_str = end_time.strftime("%a %b %d %H:%M:%S %Y")
            self._data.end_time_stamp = to_timestamp(end_time)
