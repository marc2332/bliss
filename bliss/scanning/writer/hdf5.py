import os
import errno
import h5py
import numpy
import time
import datetime
from .file import FileWriter, \
    AcquisitionMasterEventReceiver, AcquisitionDeviceEventReceiver


def _on_event(obj, event_dict, signal, sender):
    device = sender
    if signal == 'start':
        for channel in device.channels:
            maxshape = tuple([None] + list(channel.shape))
            npoints = device.npoints or 1
            shape = tuple([npoints] + list(channel.shape))
            if not channel.reference and channel.name not in obj.dataset:
                obj.dataset[channel.name] = obj.parent.create_dataset(device.name.replace('/', '_') +
                                                                      ':' + channel.name,
                                                                      shape=shape,
                                                                      dtype=channel.dtype,
                                                                      compression='gzip',
                                                                      maxshape=maxshape)
                obj.dataset[channel.name].last_point_index = 0
    elif signal == 'new_data':
        channel = device
        data = event_dict.get('data')

        channel_name = channel.name
        dataset = obj.dataset.get(channel_name)
        if dataset is None:
            return
        elif not dataset.id.valid:
            print('writer is closed. Spurious data point ignored')
            return

        last_point_index = dataset.last_point_index

        data_len = data.shape[0]
        new_point_index = dataset.last_point_index + data_len

        if dataset.shape[0] < new_point_index:
            dataset.resize(new_point_index, axis=0)

        dataset[last_point_index:new_point_index] = data

        dataset.last_point_index += data_len


class Hdf5MasterEventReceiver(AcquisitionMasterEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionMasterEventReceiver.__init__(self, *args, **kwargs)

        self.dataset = dict()

    def on_event(self, event_dict=None, signal=None, sender=None):
        return _on_event(self, event_dict, signal, sender)


class Hdf5DeviceEventReceiver(AcquisitionDeviceEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionDeviceEventReceiver.__init__(self, *args, **kwargs)

        self.dataset = dict()

    def on_event(self, event_dict=None, signal=None, sender=None):
        return _on_event(self, event_dict, signal, sender)


class Writer(FileWriter):
    def __init__(self, root_path, **keys):
        FileWriter.__init__(self, root_path,
                            master_event_receiver=Hdf5MasterEventReceiver,
                            device_event_receiver=Hdf5DeviceEventReceiver,
                            **keys)

        self.file = None
        self.scan_entry = None
        self.measurement = None

    def new_file(self, scan_file_dir, scan_recorder):
        self.close()
        self.file = h5py.File(os.path.join(scan_file_dir, '..', 'data.h5'))
        self.scan_entry = self.file.create_group(scan_recorder.name)
        self.scan_entry.attrs['NX_class'] = 'NXentry'
        scan_title = scan_recorder.scan_info.get("title", "untitled")
        utf8_dt = h5py.special_dtype(vlen=unicode)
        self.scan_entry['title'] = scan_title.encode('utf-8')
        timestamp = scan_recorder.scan_info.get("start_timestamp")
        local_time = datetime.datetime.fromtimestamp(timestamp).isoformat()
        utc_time = local_time+'%+03d:00' % (time.altzone / 3600)
        self.scan_entry['start_time'] = utc_time.encode('utf-8')
        self.measurement = self.scan_entry.create_group('measurement')
        self.measurement.attrs['NX_class'] = 'NXcollection'
        instrument = self.measurement.create_group('instrument')
        instrument.attrs['NX_class'] = 'NXinstrument'
        positioners = instrument.create_group('positioners')
        positioners.attrs['NX_class'] = 'NXcollection'
        positioners_dial = instrument.create_group('positioners_dial')
        positioners_dial.attrs['NX_class'] = 'NXcollection'
        positioners_dict = \
            scan_recorder.scan_info.get('positioners', {})
        for pname, ppos in positioners_dict.iteritems():
            if isinstance(ppos, float):  
                positioners.create_dataset(pname, dtype='float64', data=ppos)
        positioners_dial_dict = \
            scan_recorder.scan_info.get('positioners_dial', {})
        for pname, ppos in positioners_dial_dict.iteritems():
            if isinstance(ppos, float):
                positioners_dial.create_dataset(pname, dtype='float64', data=ppos)

    def new_master(self, master, scan):
        return self.measurement.create_group(master.name.replace('/', '_') + '_master')

    def close(self):
        super(Writer, self).close()
        if self.file is not None:
            self.file.close()
            self.file = None
        self.scan_entry = None
        self.measurement = None

    def get_scan_entries(self):
        file_name = os.path.join(self.root_path, 'data.h5')
        try:
            with h5py.File(file_name, mode='r') as f:
                return f.keys()
        except IOError:         # file doesn't exist
            return []
