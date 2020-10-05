# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.shell.cli.user_dialog import (
    UserIntInput,
    UserFileInput,
    UserCheckBox,
    UserChoice,
    Container,
    UserMsg,
    Validator,
    UserInput,
)

from bliss.shell.cli.pt_widgets import BlissDialog
from bliss.shell.dialog.helpers import dialog


@dialog("Lima", "saving")
def lima_saving_parameters_dialog(lima_controller):

    modes = [
        (value, key)
        for key, value in lima_controller.saving.SavingMode.__members__.items()
    ]

    formats = [(key, key) for key in lima_controller.saving.available_saving_formats]

    dlg1 = UserChoice(
        label="Saving mode:", values=modes, defval=int(lima_controller.saving.mode)
    )
    dlg2 = UserChoice(
        label="Saving format",
        values=formats,
        defval=lima_controller.saving.available_saving_formats.index(
            lima_controller.saving.file_format
        ),
    )

    dlg3 = UserIntInput(
        label="Number of frames per file", defval=lima_controller.saving.frames_per_file
    )
    dlg4 = UserIntInput(
        label="Maximum file size in MB",
        defval=lima_controller.saving.max_file_size_in_MB,
    )

    dlg5 = UserMsg(label="")
    dlg6 = UserMsg(label="For SPECIFY_MAX_FILE_SIZE mode: ")
    dlg7 = UserMsg(label="For ONE_FILE_PER_N_FRAMES mode: ")

    ct1 = Container([dlg2], title="File format:")
    ct2 = Container([dlg1, dlg5, dlg7, dlg3, dlg5, dlg6, dlg4], title="Saving mode:")

    ans = BlissDialog(
        [[ct1, ct2]], title=f"{lima_controller.name}: Saving options"
    ).show()

    if ans:
        lima_controller.saving.mode = ans[dlg1]
        lima_controller.saving.file_format = ans[dlg2]
        lima_controller.saving.frames_per_file = ans[dlg3]
        lima_controller.saving.max_file_size_in_MB = ans[dlg4]


@dialog("Lima", "processing")
def lima_processing_dialog(lima_controller):

    dlg1 = UserCheckBox(label="Enable mask", defval=lima_controller.processing.use_mask)

    dlg2 = UserFileInput(label="Path", defval=lima_controller.processing.mask)

    dlg3 = UserCheckBox(
        label="Enable flatfield", defval=lima_controller.processing.use_flatfield
    )

    dlg4 = UserFileInput(label="Path", defval=lima_controller.processing.flatfield)

    dlg5 = UserChoice(
        label="Enable / disable:",
        values=list(lima_controller.processing.BG_SUB_MODES.items()),
        defval=list(lima_controller.processing.BG_SUB_MODES).index(
            lima_controller.processing.use_background_substraction
        ),
    )
    dlg6 = UserFileInput(label="Path", defval=lima_controller.processing.background)

    ct1 = Container([dlg1, dlg2], title="Mask:")
    ct2 = Container([dlg3, dlg4], title="Flatfield:")
    ct3 = Container([dlg5, dlg6], title="Background substraction:")

    ans = BlissDialog(
        [[ct1], [ct2], [ct3]], title=f"{lima_controller.name}: Processing options"
    ).show()

    if ans:
        lima_controller.processing.use_mask = ans[dlg1]
        lima_controller.processing.mask = ans[dlg2]
        lima_controller.processing.use_flatfield = ans[dlg3]
        lima_controller.processing.flatfield = ans[dlg4]
        lima_controller.processing.use_background_substraction = ans[dlg5]
        lima_controller.processing.background = ans[dlg6]


def validate_binning(str_input):
    binning = int(str_input)
    if binning < 1:
        raise ValueError("Binning value must be >= 1")

    return binning


def validate_roi(str_input, mini, maxi):
    roi_coord = int(str_input)

    if roi_coord < mini:
        raise ValueError(f"ROI coordinate must be >= {mini}")

    if roi_coord > maxi:
        raise ValueError(f"ROI coordinate must be <= {maxi}")

    return roi_coord


@dialog("Lima", "image")
def lima_image_dialog(lima_controller):

    img = lima_controller.image
    max_width, max_height = img.fullsize

    curr_params = {
        "bin_x": img.binning[0],
        "bin_y": img.binning[1],
        "flip_x": img.flip[0],
        "flip_y": img.flip[1],
        "rotation": img.rotation,
        "roi_x": img.roi[0],
        "roi_y": img.roi[1],
        "roi_w": img.roi[2],
        "roi_h": img.roi[3],
    }

    # --- binning
    dlg_bin_x = UserInput(
        label="X axis:",
        defval=curr_params["bin_x"],
        validator=Validator(validate_binning),
    )
    dlg_bin_y = UserInput(
        label="Y axis:",
        defval=curr_params["bin_y"],
        validator=Validator(validate_binning),
    )

    # --- flip
    dlg_flip_x = UserCheckBox(label="Left-Right", defval=curr_params["flip_x"])
    dlg_flip_y = UserCheckBox(label="Up-Down   ", defval=curr_params["flip_y"])

    # --- rotation
    idx = {0: 0, 90: 1, 180: 2, 270: 3}
    dlg_rot = UserChoice(
        values=[(0, "0"), (90, "90"), (180, "180"), (270, "270")],
        defval=idx[curr_params["rotation"]],
    )

    # --- roi (subarea)

    dlg_roi_mode = UserChoice(
        values=[
            (0, "Left/Top + Width/Height"),
            (1, "Left/Top + Right/Bottom"),
            (2, "Centered (i.e. Width/Height only)"),
            (3, "Reset to full frame"),
        ],
        defval=0,
    )

    dlg_roi_x = UserInput(
        label="Left         :",
        defval=curr_params["roi_x"],
        validator=Validator(validate_roi, 0, max_width - 1),
    )
    dlg_roi_y = UserInput(
        label="Top          :",
        defval=curr_params["roi_y"],
        validator=Validator(validate_roi, 0, max_height - 1),
    )

    dlg_roi_w = UserInput(
        label="Width/Right  :",
        defval=curr_params["roi_w"],
        validator=Validator(validate_roi, 1, max_width),
    )
    dlg_roi_h = UserInput(
        label="Height/Bottom:",
        defval=curr_params["roi_h"],
        validator=Validator(validate_roi, 1, max_height),
    )

    ct1 = Container([dlg_bin_x, dlg_bin_y, UserMsg(), UserMsg()], title="Binning:")
    ct2 = Container([dlg_flip_x, dlg_flip_y, UserMsg(), UserMsg()], title="Flipping:")
    ct3 = Container([dlg_rot], title="Rotation:")
    ct4 = Container([dlg_roi_mode, UserMsg()], title="Roi definition mode:")
    ct5 = Container(
        [dlg_roi_x, dlg_roi_y, dlg_roi_w, dlg_roi_h], title="Roi coordinates:"
    )

    ans = BlissDialog(
        [[ct1, ct2, ct3], [ct4, ct5]], title=f"{lima_controller.name}: Image options"
    ).show()

    if ans:

        # ---Apply transformation first
        img.binning = ans[dlg_bin_x], ans[dlg_bin_y]

        img.flip = ans[dlg_flip_x], ans[dlg_flip_y]

        img.rotation = ans[dlg_rot]

        # ---Then apply the new roi
        roi_def_mode = ans[dlg_roi_mode]
        new_roi = [
            int(ans[dlg_roi_x]),
            int(ans[dlg_roi_y]),
            int(ans[dlg_roi_w]),
            int(ans[dlg_roi_h]),
        ]

        # roi mode: Left/Top + Width/Height
        if roi_def_mode == 0:
            pass
        # roi mode: Left/Top + Right/Bottom
        elif roi_def_mode == 1:

            x1, y1, x2, y2 = new_roi
            x = min(x1, x2)
            y = min(y1, y2)
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            new_roi = x, y, w, h

        # roi mode: Centered
        elif roi_def_mode == 2:

            x, y, w, h = new_roi
            w0, h0 = img.fullsize
            x = (w0 - w) / 2
            y = (h0 - h) / 2
            new_roi = x, y, w, h

        # roi mode: Reset to FullFrame
        elif roi_def_mode == 3:
            w0, h0 = img.fullsize
            new_roi = 0, 0, w0, h0

        # Apply the new_roi
        if new_roi != img.roi:
            img.roi = new_roi
