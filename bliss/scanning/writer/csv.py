from __future__ import absolute_import
from bliss.common import event
from ..chain import AcquisitionDevice, AcquisitionMaster
from .file import FileWriter, \
    AcquisitionMasterEventReceiver, AcquisitionDeviceEventReceiver
import numpy
import csv
import os

class CsvMasterEventReceiver(AcquisitionMasterEventReceiver):
    def __init__(self, *args, **kwargs):
        AcquisitionMasterEventReceiver.__init__(self, *args, **kwargs)
    
    def on_event(self, event_dict=None, signal=None, sender=None):
        device = sender
        if signal == 'start':
            pass


class CsvDeviceEventReceiver(AcquisitionDeviceEventReceiver):
    def __init__(self,  *args, **kwargs):
        AcquisitionDeviceEventReceiver.__init__(self, *args, **kwargs)

    def on_event(self, event_dict=None, signal=None, sender=None):
        device = sender
        if signal == 'start':
            self.parent.add_channels(device.channels)
        elif signal == "new_data":
            self.parent.handle_data(event_dict["channel_data"])


class CsvMasterFile(object):
    def __init__(self, full_path):
        self.csvfile = file(full_path, "w")
        self.csvwriter = csv.writer(self.csvfile, delimiter=' ', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        self.channel_names = list()
        self.channel_data = dict()
        self.write_header = True

    def add_channels(self, channels):
        self.channel_names.extend([c.name for c in channels if c.shape == (1,)])
            
    def handle_data(self, channel_data):
        for channel_name, data in channel_data.iteritems():
            if channel_name not in self.channel_names:
                continue
            prev_data = self.channel_data.get(channel_name)
            if prev_data is None:
                self.channel_data[channel_name] = data
            else:
                self.channel_data[channel_name] = numpy.append(prev_data, data)

        if len(self.channel_data) < len(self.channel_names):
            return

        nlines = min([self.channel_data[name].size for name in self.channel_names])

        if nlines:
            if self.write_header:
                self.write_header = False
                self.csvwriter.writerow(self.channel_names)
            rows = numpy.zeros((nlines, len(self.channel_names)), dtype = numpy.double)
            print 'channel names=',self.channel_names
            for i, channel_name in enumerate(self.channel_names):
                print channel_name
                data = self.channel_data[channel_name]
                rows[:,i] = data[:nlines]
                next_data = data[nlines:]
                if next_data:
                    self.channel_data[channel_name] = next_data
                else:
                    del self.channel_data[channel_name]
            self.csvwriter.writerows(rows)

            
class Writer(FileWriter):
    def __init__(self, root_path, **keys):
        FileWriter.__init__(self, root_path, 
                            master_event_receiver=CsvMasterEventReceiver,
                            device_event_receiver=CsvDeviceEventReceiver,
                            **keys)
 
    def new_master(self, master, scan_file_dir):
        return CsvMasterFile(os.path.join(scan_file_dir, master.name+"_master.csv"))

        
        
        
        
