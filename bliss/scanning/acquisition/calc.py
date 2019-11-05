from bliss.scanning.chain import AcquisitionSlave, ChainNode
from bliss.common.event import dispatcher


class CalcHook(object):
    def compute(self, sender, data_dict):
        raise NotImplementedError

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass


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


class CalcCounterChainNode(ChainNode):
    def get_acquisition_object(self, acq_params, ctrl_params=None):

        # --- Warn user if an unexpected is found in acq_params
        expected_keys = ["output_channels_list"]
        for key in acq_params.keys():
            if key not in expected_keys:
                print(
                    f"=== Warning: unexpected key '{key}' found in acquisition parameters for CalcAcquisitionSlave({self.controller}) ==="
                )

        output_channels_list = acq_params.get("output_channels_list")

        name = self.controller.calc_counter.name
        func = self.controller.calc_counter.calc_func

        acq_devices = []
        for node in self._calc_dep_nodes.values():
            acq_obj = node.acquisition_obj
            if acq_obj is None:
                raise ValueError(
                    f"cannot create CalcAcquisitionSlave: acquisition object of {node}({node.controller}) is None!"
                )
            else:
                acq_devices.append(acq_obj)

        return CalcAcquisitionSlave(
            name, acq_devices, func, output_channels_list, ctrl_params=ctrl_params
        )
