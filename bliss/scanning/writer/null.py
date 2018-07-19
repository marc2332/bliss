from bliss.scanning.writer.file import FileWriter, \
    AcquisitionMasterEventReceiver, AcquisitionDeviceEventReceiver


def _on_event(obj, event_dict, signal, sender):
    return

class NullMasterEventReceiver(AcquisitionMasterEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionMasterEventReceiver.__init__(self, *args, **kwargs)

    def on_event(self, event_dict=None, signal=None, sender=None):
        return _on_event(self, event_dict, signal, sender)


class NullDeviceEventReceiver(AcquisitionDeviceEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionDeviceEventReceiver.__init__(self, *args, **kwargs)

    def on_event(self, event_dict=None, signal=None, sender=None):
        return _on_event(self, event_dict, signal, sender)


class Writer(FileWriter):
    def __init__(self, *args, **keys):
        FileWriter.__init__(self, '',
                            master_event_receiver=NullMasterEventReceiver,
                            device_event_receiver=NullDeviceEventReceiver,
                            **keys)

    def create_path(self, scan_recorder):
        return scan_recorder.path

    def new_file(self, scan_file_dir, scan_recorder):
        return

    def new_master(self, master, scan):
        return

    def close(self):
        return

    def get_scan_entries(self):
        return []
