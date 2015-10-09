import os, errno
import h5py
from louie import dispatcher
from bliss.common.continuous_scan import AcquisitionDevice, AcquisitionMaster

class FileWriter(object):
    def __init__(self,root_path,
                 windows_path_mapping=None,
                 detector_temporay_path=None,**keys):
        """ A default way to organize file structure

        windows_path_mapping -- transform unix path to windows
        i.e: {'/data/visitor/':'Y:/'}
        detector_temporay_path -- temporary path for a detector
        i.e: {detector: {'/data/visitor':'/tmp/data/visitor'}}
        """
        self._root_path = root_path
        self._windows_path_mapping = windows_path_mapping or dict()
        self._detector_temporay_path = detector_temporay_path or dict()

class MasterEventReceiver(object):
    def __init__(self, master, slave, parent_group):
        self._master = master
        self._slave = slave
        self._parent = parent_group
        for signal in ('start', 'end', 'new_data'):
            dispatcher.connect(self, signal, slave)
                

    def __call__(self, event_dict=None, signal=None, sender=None):
        if signal == 'start':
            device = sender
            shape = self._master.shape
            maxshape = [None] + list(shape)[1:]
            dtype = device.dtype
            self.dataset = self._parent.create_dataset(device.name,
                                                       shape=shape,
                                                       dtype=dtype,
                                                       compression='gzip',
                                                       maxshape=maxshape)
        elif signal == 'new_data':
            pass


class EventReceiver(object):
    def __init__(self,device,parent_group):
        self._device = device
        self._parent = parent_group
        self.dataset = dict()
        
        for signal in ('start', 'end', 'new_data'):
            dispatcher.connect(self, signal, device)

    def __call__(self, event_dict=None, signal=None, sender=None):
        device = sender
                
        if signal == 'start':
            for channel in device.channels:
                maxshape = [None] + list(channel.shape)
                npoints = device.npoints
                shape = [npoints] + list(channel.shape)
                self.dataset[channel.name] = self._parent.create_dataset(device.name+':'+channel.name,
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
                    # this is to make hf5py happy
                    data.shape = (-1,1)
                print data, len(data)
                dataset[last_point_index:last_point_index + data.shape[0]] = data
                dataset.last_point_index += data.shape[0]


class Writer(FileWriter):
    def __init__(self,root_path,**keys):
        FileWriter.__init__(self,root_path,**keys)
        self.file = None
        self._event_receivers = list()

    def prepare(self,scan_recorder,scan_info,devices_tree):
        self._event_receivers = list()

        path_suffix = scan_recorder.node.db_name().replace(':',os.path.sep)
        full_path = os.path.join(self._root_path,path_suffix)
        try:
            os.makedirs(full_path)
        except OSError as exc: # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else: raise

        self.file = h5py.File(os.path.join(full_path,'data.h5'))
        scan_entry = self.file.create_group(scan_recorder.name)
        scan_entry.attrs['NX_class'] = 'NXentry'

        measurement = scan_entry.create_group('measurement')

        master_id = 0
        for dev, node in scan_recorder.nodes.iteritems():
            if isinstance(dev, AcquisitionMaster):
                master_entry = measurement.create_group('master%d' % master_id)
                master_id += 1
                for slave in dev.slaves:
                    if isinstance(slave,AcquisitionDevice):
                        if slave.type == 'lima':
                            dev.saving_format = 'EDF'
                            dev.saving_mode = 'AUTO_FRAME'
                            dev.saving_frame_per_file = 1
                            camera_name = dev.camera_type
                            scan_name = scan_recorder.node.name()
                            dev.saving_directory=os.path.join(full_path,'%s_%s' % (scan_name,camera_type))
                            dev.saving_prefix='contscan_'
                            dev.saving_suffix='.edf'
                            pass # link
                        else:
                            self._event_receivers.append(EventReceiver(slave, master_entry))
                    elif isinstance(slave,AcquisitionMaster):
                        self._event_receivers.append(MasterEventReceiver(dev, slave, master_entry))
                self._event_receivers.append(EventReceiver(dev, master_entry))
                
