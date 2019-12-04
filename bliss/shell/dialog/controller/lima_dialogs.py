#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.shell.cli.user_dialog import (
    UserIntInput,
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

    rot_dict = {"NONE": 0, "90": 1, "180": 2, "270": 3}

    dlg1 = UserCheckBox(
        label="Flip over X axis", defval=lima_controller.processing.flip[0]
    )
    dlg2 = UserCheckBox(
        label="Flip over Y axis", defval=lima_controller.processing.flip[1]
    )
    dlg3 = UserChoice(
        values=[("None", "0"), ("90", "90"), ("180", "180"), ("270", "270")],
        defval=rot_dict[lima_controller.processing.rotation],
    )

    ct1 = Container([dlg1, dlg2], title="Flipping:")
    ct2 = Container([dlg3], title="Rotation:")

    ans = BlissDialog(
        [[ct1, ct2]], title=f"{lima_controller.name}: Processing options"
    ).show()

    if ans:
        lima_controller.processing.flip = [ans[dlg1], ans[dlg2]]
        lima_controller.processing.rotation = ans[dlg3]