# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import struct
import numpy
from PyTango.gevent import DeviceProxy
from bliss.common.data_manager import DataNode
from bliss.config.settings import QueueObjSetting
from bliss.config.conductor import client
from bliss.config import channels
import gevent

class LimaDataNode(DataNode):
    class DataChannel(object):
        def __init__(self,dataset):
            self._dataset = dataset
            self._device_proxy = None
            self._image_mode = {
                0 : numpy.uint8,
                1 : numpy.uint16,
                2 : numpy.uint32,
                4 : numpy.int8,
                5 :numpy.int16 ,
                6 : numpy.int32 ,
            }        
  
        def get(self,from_index,to_index = None):
            cnx = self._dataset._data._cnx()
            url = self._dataset._data.url_server
            if url is None:     # data is no more available
                raise RuntimeError('dataset is no more available')

            current_lima_acq = int(cnx.get(url))
            
            (lima_acq_nb,acq_nb_buffer,
             LastImageAcquired,LastCounterReady,
             LastImageSaved) = [int(x) for x in cnx.hmget(self.db_name,
                                                          'lima_acq_nb',
                                                          'acq_nb_buffer',
                                                          'LastImageAcquired',
                                                          'LastCounterReady',
                                                          'LastImageSaved')]
            if to_index is None:
                
                #first we try to get image directly from the server
                if current_lima_acq == lima_acq_nb and DeviceProxy: # current acquisition
                    if LastImageAcquired < from_index: # image is not yet available
                        raise RuntimeError('image is not yet available')
                    #should be still in server memory
                    if acq_nb_buffer > LastImageAcquired - from_index:
                        try:
                            if self._device_proxy is None:
                                self._device_proxy = DeviceProxy(url)
                            raw_msg = self._device_proxy.readImage(from_index)
                            return self._tango_unpack(raw_msg[-1])
                        except: 
                            # As it's asynchronous, image seams to be no
                            # more available so read it from file
                            return self._read_from_file(from_index)
                else:
                    return self._read_from_file(from_index)
            else:
                raise NotImplementedError('Not yet done')

    def _tango_unpack(self,msg):
        struct_format = '<IHHIIHHHHHHHHHHHHHHHHHHIII'
        header_size = struct.calcsize(struct_format)
        values = struct.unpack(msg[:header_size])
        if values[0] != 0x44544159:
            raise RuntimeError('Not a lima data')
        header_offset = values[2]
        data = numpy.fromstring(msg[header_offset:],data=self._image_mode.get(values[4]))
        data.shape = values[8],values[7]
        return data

    def _read_from_file(self,from_index):
        #@todo should read file from any format?????
        for saving_parameters in self._dataset._saving_params:
            pass

    def __init__(self,name,**keys):
        DataNode.__init__(self,'lima',name,**keys)
        saving_params_name = '%s_saving_params' % self.db_name()
        self._saving_params = QueueObjSetting(saving_params_name, connection=self.db_connection)
        self._storage_task = None

    def channel_name(self):
        return 'image'

    #@brief update image status
    #
    def update_status(self,image_status):
        cnx = self._data._cnx()
        db_name = self.db_name()

        pipeline = cnx.pipeline()
        for key,value in image_status.iteritems():
            pipeline.hset(db_name,key,value)
        pipeline.execute()

    def _end_storage(self):
        self._new_image_status = None
        if self._storage_task is not None:
            self._new_image_status_event.set()
            self._storage_task.join()
            
    def _do_store(self):
        while True:
            self._new_image_status_event.wait()
            self._new_image_status_event.clear()
            if self._new_image_status is None:
                break
            self.db_connection.hmset(self.db_name(), self._new_image_status)
            #TODO: remove the comment, for use without simulator
            #gevent.idle()

    def store(self, signal, event_dict):
        if signal == 'start':
            self._end_storage()
            self._new_image_status_event = gevent.event.Event()
            self._storage_task = gevent.spawn(self._do_store)
        elif signal == 'end':
            self._end_storage()
        else:
            local_dict = dict(event_dict)
            data_type = local_dict.pop('type')
            if data_type == 'lima/image':
                self._new_image_status = local_dict
                self._new_image_status_event.set()


    #@brief set the number of buffer for this acquisition
    def set_nb_buffer(self,acq_nb_buffer):
        self._data.acq_nb_buffer = acq_nb_buffer

    #@brief set the server url and 
    #calculate an unique id for this acquisition
    def set_server_url(self,url):
        self._data.url_server = url
        
        cnx = self._data._cnx()
        self._data.lima_acq_nb = cnx.incr(url)
        
    def set_acq_parameters(self,acq_params):
        self.set_info('acq_params',acq_params)

    #@brief saving parameters
    def add_saving_parameters(self,parameters):
        self._saving_params.append(parameters)
        if self._ttl > 0:
            self._saving_params.ttl(self._ttl)

    #@brief this methode should retrives all files
    #references for this data set
    def get_file_references(self):
        #take the last in list because it's should be the final
        final_params = self._saving_params[-1]
        acq_params = self._info['acq_params']
        #in that case only one reference will be return
        overwritePolicy = final_params['overwritePolicy'].lower()
        if overwritePolicy == 'multiset':
            last_file_number = final_params['nextNumber'] + 1
        else:
            nb_files = int(math.ceil(float(acq_params['acqNbFrames']) / 
                                     final_params['framesPerFile']))
            last_file_number = final_params['nextNumber'] + nb_files

        format = '%s%s%s%s' % (final_params['directory'],
                               final_params['prefix'],
                               final_params['indexFormat'],
                               final_params['suffix'])
        references = []
        file_format = final_params['fileFormat'].lower()
        for nextNumber in xrange(final_params['nextNumber'],
                                 last_file_number):
            full_path = format % nextNumber
            if file_format == 'hdf5':
                #@todo see what's is needed for hdf5 dataset link
                pass
            references.append(full_path)
        return references

    
    #@brief for now lima has only on data channel
    #we will provide in a second time all counters (roi_counters,roi_spectrum...)
    def get_channel(self,**keys):
        return DatasetLima.DataChannel(self)
