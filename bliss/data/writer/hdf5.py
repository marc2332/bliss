import os, errno
import h5py
from bliss.data.writer.common import FileWriter, \
    AcquisitionMasterEventReceiver, AcquisitionDeviceEventReceiver



class Hdf5MasterEventReceiver(AcquisitionMasterEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionMasterEventReceiver.__init__(self, *args, **kwargs)

        self.dataset = None

    def on_event(self, event_dict, signal, device):
        if signal == 'start':
            shape = self.master.shape
            maxshape = [None] + list(shape)[1:]
            dtype = device.dtype
            self.dataset = self.parent.create_dataset(device.name,
                                                      shape=shape,
                                                      dtype=dtype,
                                                      compression='gzip',
                                                      maxshape=maxshape)
        elif signal == 'new_data':
            pass


class Hdf5DeviceEventReceiver(AcquisitionDeviceEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionDeviceEventReceiver.__init__(self, *args, **kwargs)

        self.dataset = dict()
        
    def on_event(self, event_dict, signal, device):
        if signal == 'start':
            for channel in device.channels:
                maxshape = tuple([None] + list(channel.shape))
                npoints = device.npoints
                shape = tuple([npoints] + list(channel.shape))
                self.dataset[channel.name] = self.parent.create_dataset(device.name+':'+channel.name,
                                                                        shape=shape, 
                                                                        dtype=channel.dtype,
                                                                        compression='gzip',
                                                                        maxshape=maxshape)
                self.dataset[channel.name].last_point_index = 0
        elif signal == 'new_data':
            for channel_name, data in event_dict['channel_data'].iteritems():
                dataset = self.dataset[channel_name]
                last_point_index = dataset.last_point_index

                if len(data.shape) == 1:
                    # this is to make h5py happy
                    data.shape = (-1,1)
                
                new_point_index = dataset.last_point_index + data.shape[0]
                
                if dataset.shape[0] < new_point_index:
                    dataset.resize(new_point_index, axis = 0)

                dataset[last_point_index:new_point_index] = data

                dataset.last_point_index += data.shape[0]


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
        self.file = h5py.File(os.path.join(scan_file_dir, 'data.h5'))
        self.scan_entry = self.file.create_group(scan_recorder.name)
        self.scan_entry.attrs['NX_class'] = 'NXentry'
        self.measurement = self.scan_entry.create_group('measurement')

    def new_master(self, master, scan):
        return self.measurement.create_group(master.name + '_master')
                
