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
)

from bliss.shell.cli.pt_widgets import display, BlissDialog


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


def lima_image_dialog(lima_controller):

    rot_dict = {"NONE": 0, "90": 1, "180": 2, "270": 3}

    dlg1 = UserCheckBox(
        label="Flip over X axis", defval=lima_controller._image_params.flip[0]
    )
    dlg2 = UserCheckBox(
        label="Flip over Y axis", defval=lima_controller._image_params.flip[1]
    )
    dlg3 = UserChoice(
        values=[("None", "0"), ("90", "90"), ("180", "180"), ("270", "270")],
        defval=rot_dict[lima_controller._image_params.rotation],
    )

    dlg_roi_x = UserIntInput(
        label="x:      ", defval=lima_controller._image_params._roi[0]
    )
    dlg_roi_y = UserIntInput(
        label="y:      ", defval=lima_controller._image_params._roi[1]
    )
    dlg_roi_width = UserIntInput(
        label="width:  ", defval=lima_controller._image_params._roi[2]
    )
    dlg_roi_height = UserIntInput(
        label="height: ", defval=lima_controller._image_params._roi[3]
    )

    ct1 = Container([dlg1, dlg2], title="Flipping:")
    ct2 = Container([dlg3], title="Rotation:")

    ct3 = Container([dlg_roi_x, dlg_roi_y, dlg_roi_width, dlg_roi_height], title="Roi:")

    ans = BlissDialog(
        [[ct1, ct2], [ct3]], title=f"{lima_controller.name}: Image options"
    ).show()

    if ans:
        lima_controller._image_params.flip = [ans[dlg1], ans[dlg2]]
        lima_controller._image_params.rotation = ans[dlg3]
        lima_controller._image_params._roi = [
            ans[dlg_roi_x],
            ans[dlg_roi_y],
            ans[dlg_roi_width],
            ans[dlg_roi_height],
        ]
