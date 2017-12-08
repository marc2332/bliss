import os
import errno
import h5py
from bliss.scanning.chain import AcquisitionDevice, AcquisitionMaster


class FileOrganizer(object):
    def __init__(self, root_path,
                 windows_path_mapping=None,
                 detector_temporay_path=None, **keys):
        """ A default way to organize file structure

        windows_path_mapping -- transform unix path to windows
        i.e: {'/data/visitor/':'Y:/'}
        detector_temporay_path -- temporary path for a detector
        i.e: {detector: {'/data/visitor':'/tmp/data/visitor'}}
        """
        self._root_path = root_path
        self._windows_path_mapping = windows_path_mapping or dict()
        self._detector_temporay_path = detector_temporay_path or dict()


class Hdf5Organizer(FileOrganizer):
    def __init__(self, root_path, **keys):
        FileOrganizer.__init__(self, root_path, **keys)
        self.file = None

    def _acq_device_event(self, event_dict=None, signal=None, sender=None):
        print 'received', signal, 'from', sender, ":", event_dict

    def prepare(self, scan_recorder, scan_info, devices_tree):
        path_suffix = scan_recorder.node.db_name().replace(':', os.path.sep)
        full_path = os.path.join(self._root_path, path_suffix)
        try:
            os.makedirs(full_path)
        except OSError as exc:  # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise

        self.file = h5py.File(os.path.join(full_path, 'data.h5'))
        scan_entry = h5py.Group(self.file, scan_recorder.name, create=True)
        scan_entry.attrs['NX_class'] = 'NXentry'

        measurement = h5py.Group(scan_entry, 'measurement', create=True)

        master_id = 0
        for dev, node in scan_recorder.nodes.iteritems():
            if isinstance(dev, AcquisitionMaster):
                master_entry = h5py.Group(
                    measurement, 'master%d' % master_id, create=True)
                master_id += 1
                for slave in dev.slaves:
                    if isinstance(slave, AcquisitionDevice):
                        for signal in ('start', 'end', 'new_ref', 'new_data'):
                            dispatcher.connect(
                                self._acq_device_event, signal, dev)
