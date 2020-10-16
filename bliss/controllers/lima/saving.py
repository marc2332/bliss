# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.beacon_object import BeaconObject
import textwrap
import enum


class LimaSavingParameters(BeaconObject):
    _suffix_conversion_dict = {
        "EDFGZ": ".edf.gz",
        "EDFLZ4": ".edf.lz4",
        "HDF5": ".h5",
        "HDF5GZ": ".h5",
        "HDF5BS": ".h5",
        "CBFMHEADER": ".cbf",
    }

    class SavingMode(enum.IntEnum):
        ONE_FILE_PER_FRAME = 0
        ONE_FILE_PER_SCAN = 1
        ONE_FILE_PER_N_FRAMES = 2
        SPECIFY_MAX_FILE_SIZE = 3

    def __init__(self, config, proxy, name):
        self._proxy = proxy
        super().__init__(config, name=name, share_hardware=False, path=["saving"])

    mode = BeaconObject.property_setting(
        "mode", default=SavingMode.ONE_FILE_PER_N_FRAMES
    )

    @mode.setter  ## TODO: write some doc about return of setter
    def mode(self, mode):
        if type(mode) is self.SavingMode:
            return mode
        elif mode in self.SavingMode.__members__.keys():
            return self.SavingMode[mode]
        elif self.SavingMode.__members__.values():
            return self.SavingMode(mode)
        else:
            raise RuntimeError("trying to set unkown saving mode")

    @property
    def available_saving_modes(self):
        return list(self.SavingMode.__members__.keys())

    @property
    def available_saving_formats(self):
        return self._proxy.getAttrStringValueList("saving_format")

    _frames_per_file_doc = """used in ONE_FILE_PER_N_FRAMES mode"""
    frames_per_file = BeaconObject.property_setting(
        "frames_per_file", default=100, doc=_frames_per_file_doc
    )

    _max_file_size_in_MB_doc = """used in N_MB_PER_FILE mode"""
    max_file_size_in_MB = BeaconObject.property_setting(
        "max_file_size_in_MB", default=500, doc=_max_file_size_in_MB_doc
    )

    _max_writing_tasks = BeaconObject.property_setting("_max_writing_tasks", default=1)

    @_max_writing_tasks.setter
    def _max_writing_tasks(self, value):
        assert isinstance(value, int)
        assert value > 0
        return value

    _managed_mode = BeaconObject.property_setting("_managed_mode", default="SOFTWARE")

    @_managed_mode.setter
    def _managed_mode(self, value):
        assert isinstance(value, str)
        value = value.upper()
        assert value in ["SOFTWARE", "HARDWARE"]
        return value

    file_format = BeaconObject.property_setting("file_format", default="HDF5")

    @file_format.setter
    def file_format(self, fileformat):
        avail_ff = self.available_saving_formats
        if fileformat in avail_ff:
            return fileformat
        else:
            raise RuntimeError(
                f"trying to set unkown saving format ({fileformat})."
                f"available formats are: {avail_ff}"
            )

    def _calc_max_frames_per_file(self):
        (sign, depth, width, height) = self._proxy.image_sizes
        return int(
            round(self.max_file_size_in_MB / (depth * width * height / 1024 ** 2))
        )

    def to_dict(self):
        """
        if saving_frame_per_file = -1 it has to be recalculated in the acq 
        dev and to be replaced by npoints of scan
        """

        if self.mode == self.SavingMode.ONE_FILE_PER_N_FRAMES:
            frames = self.frames_per_file
        elif self.mode == self.SavingMode.ONE_FILE_PER_SCAN:
            frames = -1
        elif self.mode == self.SavingMode.SPECIFY_MAX_FILE_SIZE:
            frames = self._calc_max_frames_per_file()
        else:
            frames = 1

        # force saving_max_writing_task in case any HDF based file format is used
        # this logic could go into lima at some point.
        if "HDF" in self.settings["file_format"]:
            max_tasks = 1
        else:
            max_tasks = self.settings["_max_writing_tasks"]

        return {
            "saving_format": self.settings["file_format"],
            "saving_frame_per_file": frames,
            "saving_suffix": self.suffix_dict[self.settings["file_format"]],
            "saving_max_writing_task": max_tasks,
            "saving_managed_mode": self._managed_mode,
        }

    @property
    def suffix_dict(self):
        _suffix_dict = {k: "." + k.lower() for k in self.available_saving_formats}
        _suffix_dict.update(self._suffix_conversion_dict)
        return _suffix_dict

    def __info__(self):
        tmp = self.to_dict()
        mode_prefix = """\
             - """

        av_modes = f"\n{mode_prefix}".join(self.available_saving_modes)
        return textwrap.dedent(
            f"""\
                Saving
            --------------
            File Format:   {self.file_format}
             └->  Suffix:  {tmp['saving_suffix']}
            Current Mode:  {self.mode.name}
            Available Modes:
{mode_prefix}{av_modes}

            for ONE_FILE_PER_N_FRAMES mode
            ------------------------------
            frames_per_file: {self.frames_per_file}

            for SPECIFY_MAX_FILE_SIZE mode
            ------------------------------
            max file size (MB):  {self.max_file_size_in_MB}
             └-> frames per file: {self._calc_max_frames_per_file()}

            Expert Settings
            ---------------
            config max_writing_tasks:  {self._max_writing_tasks}
            current max_writing_tasks: {tmp['saving_max_writing_task']}
            lima managed_mode:         {self._managed_mode}
            """
        )
