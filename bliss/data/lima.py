# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import struct
import math
import weakref
import numpy
import gevent
from bliss.common.tango import DeviceProxy
from bliss.data.node import DataNode
from bliss.config.settings import HashSetting, QueueObjSetting

try:
    import EdfFile
except ImportError:
    EdfFile = None
try:
    import h5py
except ImportError:
    h5py = None


class LimaImageChannelDataNode(DataNode):
    class _GetView(object):
        def __init__(self, ref_status, parameters, acq_params,
                     from_index, to_index):
            self.ref_status = ref_status
            self.parameters = parameters
            self.acq_params = acq_params
            self._update()
            self.from_index = from_index
            self.to_index = to_index
            self._image_mode = {
                0: numpy.uint8,
                1: numpy.uint16,
                2: numpy.uint32,
                4: numpy.int8,
                5: numpy.int16,
                6: numpy.int32,
            }

        @property
        def last_index(self):
            """ evaluate the last image index
            """
            if self.to_index >= 0:
                return self.to_index
            return self.last_image_acquired

        @property
        def current_lima_acq(self):
            """ return the current server acquisition number
            """
            return int(self.ref_status.db_connection.get(self.url_server, -1))

        def __iter__(self):
            self._update()
            proxy = DeviceProxy(self.url_server) if self.url_server else None
            for image_nb in range(self.from_index, self.last_index):
                data = self._get_from_server_memory(proxy, image_nb)
                if not data:
                    yield self._get_from_file(image_nb)
                else:
                    yield data
                self._update()

        def __len__(self):
            self._update()
            return self.to_index - self.from_index

        def _update(self):
            """ update view status
            """
            (self.url_server, self.lima_acq_nb, self.acq_nb_buffer,
             self.last_image_acquired, self.last_image_ready,
             self.last_counter_ready, self.last_image_saved) = self.ref_status.fromkeys(
                 'url_server', 'lima_acq_nb', 'acq_nb_buffer', 'LastImageAcquired',
                 'LastImageReady', 'LastCounterReady', 'LastImageSaved')

        def _get_from_server_memory(self, proxy, image_nb):
            if self.current_lima_acq == self.lima_acq_nb:  # current acquisition is this one
                if self.last_image_ready < image_nb:      # image not yet available
                    raise RuntimeError('image is not yet available')
                # should be in memory
                if self.acq_nb_buffer > (self.last_image_ready - image_nb):
                    try:
                        raw_msg = proxy.readImage(image_nb)
                    except:
                        # As it's asynchronous, image seams to be no
                        # more available so read it from file
                        return None
                    else:
                        return self._tango_unpack(raw_msg[-1])

        def _get_from_file(self, image_nb):
            for parameters in self.parameters:
                filename, path_in_file, image_index, file_format = \
                    self._get_filename(parameters, image_nb)
                if file_format in ('EDF', 'EDFGZ', 'EDFConcat'):
                    if EdfFile is not None:
                        f = EdfFile.EdfFile(filename)
                        return f.GetData(image_index)
                    else:
                        raise RuntimeError("EdfFile module is not available,"
                                           "Can't return image data")
                elif file_format == 'HDF5':
                    if h5py is not None:
                        with h5py.File(filename) as f:
                            dataset = f[path_in_file]
                            return dataset[image_index]
                else:
                    raise RuntimeError("Format net yet managed")
            else:
                raise RuntimeError(
                    "Can't retrieved image %d from file" % image_nb)

        def _tango_unpack(self, msg):
            struct_format = '<IHHIIHHHHHHHHHHHHHHHHHHIII'
            header_size = struct.calcsize(struct_format)
            values = struct.unpack(msg[:header_size])
            if values[0] != 0x44544159:
                raise RuntimeError('Not a lima data')
            header_offset = values[2]
            data = numpy.fromstring(
                msg[header_offset:], data=self._image_mode.get(values[4]))
            data.shape = values[8], values[7]
            return data

    class MergeB4Store(object):
        """
        This class merge lima ref event to redis database.

        Actually the real update is done on idle state of gevent loop so,
        we can have several update (update_status) before a real store (_do_store).
        """

        def __init__(self, cnt):
            self._new_image_status_event = gevent.event.Event()
            self._new_image_status = dict()
            self._storage_task = gevent.spawn(self._do_store)
            self._cnt = weakref.proxy(cnt, self.stop)
            self._stop_flag = False

        def _do_store(self):
            while True:
                succeed = self._new_image_status_event.wait(1)
                if succeed:
                    self._new_image_status_event.clear()
                else:           # test if cnt is still alive
                    try:
                        self._cnt._ref_status
                        continue
                    except ReferenceError:
                        break

                local_dict = self._new_image_status
                self._new_image_status = dict()
                if local_dict:
                    self._cnt._ref_status.update(local_dict)
                if self._stop_flag:
                    break
                gevent.idle()

        def update_status(self, new_status):
            """
            Post the update of lima reference
            """
            self._new_image_status.update(new_status)
            self._new_image_status_event.set()

        def stop(self):
            """
            This method should be called to stop the store task.
            """
            self._stop_flag = True
            if self._storage_task is not None:
                self._new_image_status_event.set()
                self._storage_task.join()

    def __init__(self, name, **keys):
        DataNode.__init__(self, 'lima', name, **keys)

        cnx = self.db_connection
        self._ref_status = HashSetting('%s_ref' % self.db_name, connection=cnx)
        self.params = QueueObjSetting('%s_parameters' % self.db_name,
                                      connection=cnx)
        self._merge_store = self.MergeB4Store(self)

    def get(self, from_index, to_index=None):
        """
        return a view on data references.

        **from_index** from which image index you want to get
        **to_index** to which index you want images
            if to_index is None => only one image which as index from_index
            if to_index < 0 => to the end of acquisition
        """
        return self._GetView(self._ref_status, self.params,
                             self.info['acq_params'], from_index,
                             to_index if to_index is not None else from_index + 1)

    def store(self, signal, event_dict):
        if signal == 'new_ref':
            local_dict = dict(event_dict)
            data_type = local_dict.pop('type')
            if data_type == 'lima/image':
                self._merge_store.update_status(event_dict)
        elif signal == 'new_data':
            local_dict = dict(event_dict)
            data_type = local_dict.pop('type')
            if data_type == 'lima/parameters':
                self.add_parameters(local_dict)
            elif data_type == 'lima/server_url':
                self.set_server_url(local_dict['url'])

    def set_nb_buffer(self, acq_nb_buffer):
        """set the number of buffer for this acquisition
        """
        self._ref_status['acq_nb_buffer'] = acq_nb_buffer

    def set_server_url(self, url):
        """set the server url and calculate an
        unique id for this acquisition
        """
        cnx = self.db_connection
        self._ref_status.update({'url_server': url,
                                 'lima_acq_nb': cnx.incr(url)})

    def add_parameters(self, parameters):
        """ saving parameters in database
        """
        self.params.append(parameters)

    def get_file_references(self):
        """
        this methode should retrives all files
        references for this data set
        """
        # take the last in list because it's should be the final
        final_params = self.params[-1]
        # in that case only one reference will be return
        overwrite_policy = final_params['overwritePolicy'].lower()
        if overwrite_policy == 'multiset':
            last_file_number = final_params['nextNumber'] + 1
        else:
            nb_files = int(math.ceil(float(final_params['acqNbFrames']) /
                                     final_params['framesPerFile']))
            last_file_number = final_params['nextNumber'] + nb_files

        path_format = '%s%s%s%s' % (final_params['directory'],
                                    final_params['prefix'],
                                    final_params['indexFormat'],
                                    final_params['suffix'])
        references = []
        file_format = final_params['fileFormat'].lower()
        for next_number in xrange(final_params['nextNumber'],
                                  last_file_number):
            full_path = path_format % next_number
            if file_format == 'hdf5':
                #@todo see what's is needed for hdf5 dataset link
                pass
            references.append(full_path)
        return references

    def _get_db_names(self):
        db_name = DataNode._get_db_names(self)
        db_name.extend(['%s%s' % self.db_name + suffix
                        for suffix in ['_ref', '_parameters']])
        url = self._ref_status.get('url_server')
        if url is not None:
            db_name.append(url)
        return db_name
