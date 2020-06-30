# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
from bliss.config import streaming_events

__all__ = ["LimaImageChannelDataEvent"]


class LimaImageChannelDataEvent(streaming_events.StreamEvent):
    TYPE = b"LIMACHANNELDATA"
    REF_KEY = b"__REFSTATUS__"

    def init(self, ref_status):
        """
        :param dict description:
        """
        defaults = {
            "server_url": "",
            "lima_acq_nb": -1,
            "buffer_max_number": -1,
            "last_image_acquired": -1,
            "last_image_ready": -1,
            "last_counter_ready": -1,
            "last_image_saved": -1,
        }
        if ref_status:
            missing = set(defaults.keys()) - set(ref_status.keys())
            for k in missing:
                ref_status[k] = defaults[k]
        else:
            ref_status.update(defaults)
        self.ref_status = ref_status

    def _encode(self):
        raw = super()._encode()
        raw[self.REF_KEY] = self.generic_encode(self.ref_status)
        return raw

    def _decode(self, raw):
        super()._decode(raw)
        self.ref_status = self.generic_decode(raw[self.REF_KEY])

    @property
    def last_index(self):
        # We can choose from:
        #   last_image_acquired
        #   last_image_ready (default for `LimaDataView.last_index`)
        #   last_counter_ready
        #   last_image_saved
        return self.ref_status["last_image_ready"]

    def get_data(self, from_index, ref_data):
        """
        :param int from_index:
        :param HashObjSetting ref_data:
        :returns list(tuple):
        """
        data = list()
        to_index = self.last_index
        if to_index >= from_index:
            # These images are not necessarily saved already
            image_nbs = list(range(from_index, to_index + 1))
            try:
                data = self.image_filenames(ref_data, image_nbs)
            except RuntimeError:
                # Images are not saved
                data = list()
        return data

    @staticmethod
    def image_filenames(ref_data, image_nbs, last_image_saved=None):
        """
        :param HashObjSetting ref_data:
        :param sequence image_nbs:
        :param int last_image_saved:
        :returns list(tuple): file name, path-in-file, image index, file format
                            File format is not file extension (HDF5, HDF5BS, EDFLZ4, ...)
        :raises RuntimeError: when an image is not saved already
        """
        saving_mode = ref_data.get("saving_mode", "MANUAL")
        if saving_mode == "MANUAL":  # files are not saved
            raise RuntimeError("Images were not saved")

        overwrite_policy = ref_data.get("saving_overwrite", "ABORT").lower()
        if overwrite_policy == "multiset":
            nb_image_per_file = ref_data["acq_nb_frames"]
        else:
            nb_image_per_file = ref_data.get("saving_frame_per_file", 1)

        first_file_number = ref_data.get("saving_next_number", 0)
        path_format = os.path.join(
            ref_data["saving_directory"],
            "%s%s%s"
            % (
                ref_data["saving_prefix"],
                ref_data.get("saving_index_format", "%04d"),
                ref_data["saving_suffix"],
            ),
        )
        returned_params = list()
        file_format = ref_data["saving_format"]
        if last_image_saved is None:
            last_image_saved = max(image_nbs)
        for image_nb in image_nbs:
            if image_nb > last_image_saved:
                raise RuntimeError("Image %d was not saved" % image_nb)

            image_index_in_file = image_nb % nb_image_per_file
            file_nb = first_file_number + image_nb // nb_image_per_file
            file_path = path_format % file_nb
            if file_format.lower().startswith("hdf5"):
                if ref_data.get("lima_version", "<1.9.1") == "<1.9.1":
                    # 'old' lima
                    path_in_file = (
                        "/entry_0000/instrument/"
                        + ref_data["user_detector_name"]
                        + "/data/array"
                    )
                else:
                    # 'new' lima
                    path_in_file = (
                        f"/entry_0000/{ref_data['user_instrument_name']}"
                        + f"/{ref_data['user_detector_name']}/data"
                    )
                returned_params.append(
                    (file_path, path_in_file, image_index_in_file, file_format)
                )
            else:
                returned_params.append(
                    (file_path, "", image_index_in_file, file_format)
                )
        return returned_params
