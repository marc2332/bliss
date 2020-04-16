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


def validate_binning(dlg_input):
    binning = int(dlg_input)
    if binning < 1:
        raise ValueError("Binng factor must be > 1!")

    return binning


def validate_roi(str_input, max_value):
    roi_coord = int(str_input)

    if roi_coord < 0:
        raise ValueError("ROI coordinates must be >= 0")

    if roi_coord > max_value:
        raise ValueError("ROI coordinate exceeds image size!")


def lima_image_dialog(lima_controller):

    rot_dict = {"NONE": 0, "90": 1, "180": 2, "270": 3}

    dlg_flip_x = UserCheckBox(
        label="Flip over X axis", defval=lima_controller._image_params.flip[0]
    )
    dlg_flip_y = UserCheckBox(
        label="Flip over Y axis", defval=lima_controller._image_params.flip[1]
    )

    dlg_bin_x = UserInput(
        label="Binning X axis",
        defval=lima_controller._image_params.binning[0],
        validator=Validator(validate_binning),
    )
    dlg_bin_y = UserInput(
        label="Binning Y axis",
        defval=lima_controller._image_params.binning[1],
        validator=Validator(validate_binning),
    )

    dlg_rot = UserChoice(
        values=[("0", "None"), ("90", "90"), ("180", "180"), ("270", "270")],
        defval=rot_dict[lima_controller._image_params.rotation],
    )

    ct1 = Container([dlg_flip_x, dlg_flip_y], title="Flipping:")
    ct2 = Container([dlg_rot], title="Rotation:")
    ct3 = Container([dlg_bin_x, dlg_bin_y], title="Binning:")

    # ROI handling
    max_width, max_height = lima_controller._image_params._max_dim_lima_ref

    if (
        lima_controller._image_params.roi.width == 0
        and lima_controller._image_params.roi.height == 0
    ) or (
        lima_controller._image_params.roi.width == max_width
        and lima_controller._image_params.roi.height == max_height
    ):
        no_roi = True
        dlg_roi = UserChoice(
            values=[
                ("none", "No ROI"),
                ("center", "Add centered ROI"),
                ("free", "Add free ROI"),
            ],
            defval=0,
        )
        ct4 = Container([dlg_roi], title="Roi:")
    else:
        no_roi = False
        dlg_last_roi = UserMsg(
            label=f"Actual ROI: {lima_controller._image_params.roi} (eventual changes above not yet considered!)"
        )
        dlg_roi = UserChoice(
            values=[
                ("none", "Remove ROI"),
                ("keep", "Keep current ROI"),
                ("center", "Modify centered ROI"),
                ("free", "Modify free ROI"),
            ],
            defval=0,
        )
        ct4 = Container([dlg_last_roi, dlg_roi], title="Roi:")

    ans = BlissDialog(
        [[ct1, ct2], [ct3], [ct4]], title=f"{lima_controller.name}: Image options"
    ).show()

    if ans:
        lima_controller._image_params.flip = [ans[dlg_flip_x], ans[dlg_flip_y]]

        new_binning = [int(ans[dlg_bin_x]), int(ans[dlg_bin_y])]

        lima_controller._image_params.binning = [
            int(ans[dlg_bin_x]),
            int(ans[dlg_bin_y]),
        ]
        lima_controller._image_params.rotation = int(ans[dlg_rot])

        # treat ROI request
        if ans[dlg_roi] == "none":
            lima_controller._image_params._roi = [0, 0, max_width, max_width]
        elif ans[dlg_roi] == "keep":
            pass
        else:
            if ans[dlg_roi] == "center":
                centered_roi(lima_controller)
            else:
                width = max_width
                height = max_width
                dlg_msg = UserMsg(label=f"Image size ({width}x{height})")
                cur_roi = lima_controller.image.roi.to_array()
                dlg_roi_x = UserInput(
                    label="Start X position",
                    defval=cur_roi[0],
                    validator=Validator(validate_roi, width),
                )
                dlg_roi_y = UserInput(
                    label="Start Y position",
                    defval=cur_roi[1],
                    validator=Validator(validate_roi, height),
                )
                dlg_roi_width = UserInput(
                    label="Width           ",
                    defval=cur_roi[2],
                    validator=Validator(validate_roi, width),
                )
                dlg_roi_height = UserInput(
                    label="Height          ",
                    defval=cur_roi[3],
                    validator=Validator(validate_roi, height),
                )

                ct = Container(
                    [dlg_msg, dlg_roi_x, dlg_roi_y, dlg_roi_width, dlg_roi_height],
                    title="Free ROI",
                )
                ans = BlissDialog(
                    [[ct]], title=f"{lima_controller.name}: Image options"
                ).show()

                if ans != False:
                    lima_controller._image_params._roi = [
                        int(ans[dlg_roi_x]),
                        int(ans[dlg_roi_y]),
                        int(ans[dlg_roi_width]),
                        int(ans[dlg_roi_height]),
                    ]


def centered_roi(lima_controller):
    width, height = lima_controller._image_params._max_dim_lima_ref

    dlg_msg_width = UserMsg(label=f"Full image width is {width}")
    dlg_roi_width = UserInput(
        label="ROI width?",
        defval=lima_controller._image_params.roi.width,
        validator=Validator(validate_roi, width),
    )

    dlg_msg_height = UserMsg(label=f"Full image height is {height}")
    dlg_roi_height = UserInput(
        label="ROI height?",
        defval=lima_controller._image_params.roi.height,
        validator=Validator(validate_roi, height),
    )

    ct = Container(
        [dlg_msg_width, dlg_roi_width, dlg_msg_height, dlg_roi_height],
        title="Centered ROI",
    )

    dlg_expert_mode = UserCheckBox(label="Advanced settings", defval=False)

    ans = BlissDialog(
        [[ct], [dlg_expert_mode]], title=f"{lima_controller.name}: Image options"
    ).show()

    if ans != False:
        if ans[dlg_expert_mode]:
            dlg_msg_width = UserMsg(label=f"Full image width is {width}")
            dlg_roi_startX = UserInput(
                label="X width starting point?",
                defval=lima_controller._image_params.roi.p0[0],
                validator=Validator(validate_roi, width),
            )
            dlg_roi_endX = UserInput(
                label="X width ending point?",
                defval=lima_controller._image_params.roi.p1[0],
                validator=Validator(validate_roi, width),
            )

            dlg_msg_height = UserMsg(label=f"Full image height is {height}")
            dlg_roi_startY = UserInput(
                label="Y height starting point?",
                defval=lima_controller._image_params.roi.p0[1],
                validator=Validator(validate_roi, height),
            )
            dlg_roi_endY = UserInput(
                label="Y height ending point?",
                defval=lima_controller._image_params.roi.p1[1],
                validator=Validator(validate_roi, height),
            )

            ct = Container(
                [
                    dlg_msg_width,
                    dlg_roi_startX,
                    dlg_roi_endX,
                    dlg_msg_height,
                    dlg_roi_startY,
                    dlg_roi_endY,
                ],
                title="Centered ROI",
            )
            ans_exp = BlissDialog(
                [[ct]], title=f"{lima_controller.name}: Image options"
            ).show()

            if ans_exp != False:
                new_width = int(ans_exp[dlg_roi_endX]) - int(ans_exp[dlg_roi_startX])
                new_height = int(ans_exp[dlg_roi_endY]) - int(ans_exp[dlg_roi_startY])
                lima_controller._image_params._roi = [
                    int(ans_exp[dlg_roi_startX]),
                    int(ans_exp[dlg_roi_startY]),
                    new_width,
                    new_height,
                ]

        else:
            roi_start_x = int(width / 2 - int(ans[dlg_roi_width]) / 2)

            roi_start_y = int(height / 2 - int(ans[dlg_roi_height]) / 2)

            lima_controller._image_params._roi = [
                roi_start_x,
                roi_start_y,
                int(ans[dlg_roi_width]),
                int(ans[dlg_roi_height]),
            ]
