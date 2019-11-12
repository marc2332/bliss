from bliss.scanning.chain import AcquisitionSlave, ChainNode
from bliss.common.event import dispatcher

# === DEPRECATED
class CalcHook(object):
    def compute(self, sender, data_dict):
        raise NotImplementedError

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass


# === DEPRECATED
class CalcAcquisitionSlave(AcquisitionSlave):
    """
    Helper to do some extra Calculation on counters.
    i.e: compute encoder position to user position
    Args:
        src_acq_devices_list -- list or tuple of acq(device/master) you want to listen to.
        func -- the transformation function. This will have has input a  dictionary
        with the name of counter as the key and the value has the data of source data channel.
        This function should return a dictionary with the name of the destination channel as key,
        and the value as its data.
        Can also be an inherited class of **CalcHook**:
         - the transformation function is the **compute** method.
         - optionally you can redefine prepare,start,stop. 
    """

    def __init__(
        self,
        name,
        src_acq_devices_list,
        func,
        output_channels_list=None,
        ctrl_params=None,
    ):
        AcquisitionSlave.__init__(
            self,
            None,
            name=name,
            trigger_type=AcquisitionSlave.HARDWARE,
            ctrl_params=ctrl_params,
        )
        self._connected = False
        self.src_acq_devices_list = src_acq_devices_list
        if isinstance(func, CalcHook):
            self.cbk = func
        else:

            class CBK(CalcHook):
                def compute(self, sender, data_dict):
                    return func(sender, data_dict)

            self.cbk = CBK()
        if output_channels_list is not None:
            self.channels.extend(output_channels_list)

    def add_counter(self, counter):
        if counter in self._counters:
            return
        return self._do_add_counter(counter)

    def connect(self):
        if self._connected:
            return
        for acq_device in self.src_acq_devices_list:
            for channel in acq_device.channels:
                dispatcher.connect(self.new_data_received, "new_data", channel)
        self._connected = True

    def disconnect(self):
        if not self._connected:
            return
        for acq_device in self.src_acq_devices_list:
            for channel in acq_device.channels:
                dispatcher.disconnect(self.new_data_received, "new_data", channel)
        self._connected = False

    def prepare(self):
        self.cbk.prepare()
        self.connect()

    def new_data_received(self, event_dict=None, signal=None, sender=None):
        channel_data = event_dict.get("data")
        if channel_data is None:
            return
        channel = sender
        output_channels_data_dict = self.cbk.compute(
            sender, {channel.short_name: channel_data}
        )

        if output_channels_data_dict:
            for channel in self.channels:
                channel_data = output_channels_data_dict.get(channel.name)
                if channel_data is not None:
                    channel.emit(channel_data)

    def start(self):
        self.cbk.start()

    def stop(self):
        self.disconnect()
        self.cbk.stop()


class CalcCounterAcquisitionSlave(AcquisitionSlave):
    """
    Helper to do some extra Calculation on counters.
    i.e: compute encoder position to user position
    Args:
        controller -- CalcCounterController Object
        src_acq_devices_list -- list or tuple of acq(device/master) you want to listen to.
    """

    def __init__(self, controller, src_acq_devices_list, ctrl_params=None):

        # name = "AD_" + controller.name
        name = controller.name

        AcquisitionSlave.__init__(
            self,
            controller,
            name=name,
            trigger_type=AcquisitionSlave.HARDWARE,
            ctrl_params=ctrl_params,
        )
        self._connected = False

        self.src_acq_devices_list = src_acq_devices_list

        self.output_counters = {}

    def _do_add_counter(self, counter):
        super()._do_add_counter(counter)
        self.output_counters[counter.name] = counter

    def connect(self):
        if self._connected:
            return
        for acq_device in self.src_acq_devices_list:
            for channel in acq_device.channels:
                dispatcher.connect(self.new_data_received, "new_data", channel)
        self._connected = True

    def disconnect(self):
        if not self._connected:
            return
        for acq_device in self.src_acq_devices_list:
            for channel in acq_device.channels:
                dispatcher.disconnect(self.new_data_received, "new_data", channel)
        self._connected = False

    def prepare(self):
        self.device.prepare()
        self.connect()

    def new_data_received(self, event_dict=None, signal=None, sender=None):

        channel_data = event_dict.get("data")
        if channel_data is None:
            return
        channel = sender
        output_channels_data_dict = self.device.compute(
            sender, {channel.short_name: channel_data}
        )

        if output_channels_data_dict:
            for channel in self.channels:
                channel_data = output_channels_data_dict.get(
                    self.device.tags[channel.short_name]
                )
                if channel_data is not None:
                    channel.emit(channel_data)

    def start(self):
        self.device.start()

    def stop(self):
        self.disconnect()
        self.device.stop()


class CalcCounterChainNode(ChainNode):
    def get_acquisition_object(self, acq_params, ctrl_params=None):

        # Check if Acquisition Devices of dependant counters already exist
        acq_devices = []
        for node in self._calc_dep_nodes.values():
            acq_obj = node.acquisition_obj
            if acq_obj is None:
                raise ValueError(
                    f"cannot create CalcCounterAcquisitionSlave: acquisition object of {node}({node.controller}) is None!"
                )
            else:
                acq_devices.append(acq_obj)

        return CalcCounterAcquisitionSlave(
            self.controller, acq_devices, ctrl_params=ctrl_params
        )
