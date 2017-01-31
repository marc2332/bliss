import os, errno
import h5py
import numpy
from bliss.data.writer.common import FileWriter, \
    AcquisitionMasterEventReceiver, AcquisitionDeviceEventReceiver

def _on_event(obj, event_dict, signal, device):
    if signal == 'start':
        for channel in device.channels:
            maxshape = tuple([None] + list(channel.shape))
            npoints = device.npoints or 1
            shape = tuple([npoints] + list(channel.shape))
            if channel.name not in obj.dataset:
                obj.dataset[channel.name] = obj.parent.create_dataset(device.name.replace('/','_') +
                                                                      ':'+channel.name,
                                                                      shape=shape, 
                                                                      dtype=channel.dtype,
                                                                      compression='gzip',
                                                                      maxshape=maxshape)
                obj.dataset[channel.name].last_point_index = 0
    elif signal == 'new_data':
        for channel_name, data in event_dict['channel_data'].iteritems():
            dataset = obj.dataset[channel_name]
            last_point_index = dataset.last_point_index

            if len(data.shape) == 1:
                # this is to make h5py happy
                data.shape = (-1,1)
            elif not data.shape: # not an array
                data = numpy.array(data)
                data.shape = (1,1)

            data_len = data.shape[0]
            new_point_index = dataset.last_point_index + data_len

            if dataset.shape[0] < new_point_index:
                dataset.resize(new_point_index, axis = 0)

            dataset[last_point_index:new_point_index] = data

            dataset.last_point_index += data_len



class Hdf5MasterEventReceiver(AcquisitionMasterEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionMasterEventReceiver.__init__(self, *args, **kwargs)

        self.dataset = dict()

    def on_event(self, event_dict, signal, device):
        return _on_event(self, event_dict, signal, device)


class Hdf5DeviceEventReceiver(AcquisitionDeviceEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionDeviceEventReceiver.__init__(self, *args, **kwargs)

        self.dataset = dict()
        
    def on_event(self, event_dict, signal, device):
        return _on_event(self, event_dict, signal, device)


class Writer(FileWriter):
    def __init__(self,root_path,**keys):
        FileWriter.__init__(self, root_path, 
                            master_event_receiver=Hdf5MasterEventReceiver,
                            device_event_receiver=Hdf5DeviceEventReceiver,
                            **keys)

        self.file = None
        self.scan_entry = None
        self.measurement = None
        
    def new_file(self, scan_file_dir, scan_recorder):
        self.file = h5py.File(os.path.join(scan_file_dir,'..','data.h5'))
        self.scan_entry = self.file.create_group(scan_recorder.name)
        self.scan_entry.attrs['NX_class'] = 'NXentry'
        self.measurement = self.scan_entry.create_group('measurement')

    def new_master(self, master, scan):
        return self.measurement.create_group(master.name.replace('/','_') + '_master')
                
