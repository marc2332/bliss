"""Helper for tests"""


class ScanInfoFactory:
    def __init__(self):
        self.__scan_info = {
            "acquisition_chain": {},
            "devices": {},
            "channels": {},
            "positioners": {},
        }

    def __setitem__(self, key, value):
        self.__scan_info[key] = value

    def add_device(
        self,
        root_id: str,
        device_id: str,
        meta: dict = {},
        triggered_by: str = None,
        type: str = None,
    ):
        default_root = {"devices": []}
        acq_root = self.__scan_info["acquisition_chain"].setdefault(
            root_id, default_root
        )
        acq_root["devices"].append(device_id)
        default_device = {"channels": []}
        device_desc = self.__scan_info["devices"].setdefault(device_id, default_device)
        device_desc.update(meta)
        if type is not None:
            device_desc["type"] = type
        if triggered_by is not None:
            triggering_dev = self.__scan_info["devices"][triggered_by]
            triggered_devs = triggering_dev.setdefault("triggered_devices", [])
            triggered_devs.append(device_id)

    def add_lima_device(
        self,
        root_id: str,
        device_id: str,
        image: bool = False,
        rois: dict = None,
        triggered_by: str = None,
    ):
        self.add_device(
            root_id=root_id, device_id=device_id, triggered_by=triggered_by, type="lima"
        )
        if image:
            self.add_channel(device_id + ":image", device_id=device_id, dim=2)
        if rois is not None:
            self.add_device(
                root_id=root_id,
                device_id=device_id + ":roi_counters",
                triggered_by=device_id,
                meta=rois,
            )

    def add_channel(
        self,
        channel_id: str,
        device_id: str = None,
        meta: dict = {},
        dim: int = None,
        unit: str = None,
    ):
        if device_id is None:
            device_id = channel_id.rsplit(":", 1)[0]
        device_desc = self.__scan_info["devices"][device_id]
        device_desc["channels"].append(channel_id)
        channel_desc = self.__scan_info["channels"].setdefault(channel_id, {})
        channel_desc.update(meta)
        if dim is not None:
            channel_desc["dim"] = dim
        if unit is not None:
            channel_desc["unit"] = unit

    def scan_info(self):
        scan_info = self.__scan_info
        self.__scan_info = None
        return scan_info
