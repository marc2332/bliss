# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.shell.cli.user_dialog import (
    UserMsg,
    UserInput,
    UserIntInput,
    UserFloatInput,
    UserFileInput,
    UserChoice,
    UserCheckBox,
    Container,
    check,
    BlissWizard,
)
from bliss.shell.cli.pt_widgets import BlissDialog


def multi_dialog(title="Bliss dialog"):

    from bliss import global_map

    motor_names = list(global_map.get_axes_names_iter())
    motor_obj = list(global_map.get_axes_iter())

    ch_values = list(zip(motor_obj, motor_names))

    dlg = BlissDialog(
        [
            [
                UserMsg(
                    label="I am a long message", text_align="CENTER", text_expand=True
                )
            ],
            [
                Container(
                    [
                        UserIntInput(label=None, name="myint", defval=100),
                        UserFloatInput(label="", name="myfloat"),
                        UserInput(
                            name="myinput",
                            label="frange_1.1.3",
                            validator=check["frange"],
                            defval=6,
                        ),
                        UserInput(
                            label="word_1.1.4",
                            defval="The observable univers has at least one hundred billion galaxies",
                        ),
                    ],
                    title="Group 1",
                    border=1,
                    padding=1,
                    splitting="h",
                )
            ],
            [UserInput(label="motor_2.1", completer=motor_names)],
            [UserFileInput(label="path_3.1", defval="")],
            [
                Container(
                    [UserChoice(values=ch_values, defval=0, label="Select a motor")],
                    title="Motors",
                    border=1,
                ),
                Container(
                    [
                        UserCheckBox(label="BELGIAN BEER"),
                        UserCheckBox(label="red wine"),
                        UserCheckBox(label="rhum"),
                        UserCheckBox(label="chartreuse"),
                    ],
                    title="Drinks",
                    border=1,
                ),
            ],
        ],
        title=title,
        paddings=(1, 1),
        show_help=True,
        disable_tmux_mouse=True,
    )
    return dlg.show()


def wizard(title="wizard"):
    from bliss.common.utils import get_axes_names_iter, get_axes_iter

    motor_names = list(get_axes_names_iter())
    motor_obj = list(get_axes_iter())

    ch_values = list(zip(motor_obj, motor_names))

    dlg1 = BlissDialog(
        [
            [
                Container(
                    [
                        UserIntInput(label="int_1"),
                        UserFloatInput(label="float_1.1.2"),
                        UserInput(
                            label="frange_1.1.3", validator=check["frange"], defval=6
                        ),
                        UserInput(label="word_1.1.4"),
                    ],
                    title="Group 1",
                    border=1,
                    padding=1,
                    splitting="h",
                )
            ],
            [UserInput(label="motor_2.1", completer=motor_names)],
            [UserFileInput(label="path_3.1", defval="")],
            [
                Container(
                    [UserChoice(values=ch_values, defval=0, label="Select a motor")],
                    title="Motors",
                    border=1,
                ),
                Container(
                    [
                        UserCheckBox(label="BELGIAN BEER"),
                        UserCheckBox(label="red wine"),
                        UserCheckBox(label="rhum"),
                        UserCheckBox(label="chartreuse"),
                    ],
                    title="Drinks",
                    border=1,
                ),
            ],
        ],
        title=title,
        paddings=(1, 1),
    )

    dlg2 = BlissDialog(
        [
            [
                Container(
                    [
                        UserIntInput(label="int_1"),
                        UserFloatInput(label="float_1.1.2"),
                        UserInput(
                            label="frange_1.1.3", validator=check["frange"], defval=6
                        ),
                        UserInput(label="word_1.1.4"),
                    ],
                    title="Group 1",
                    border=1,
                    padding=1,
                    splitting="h",
                )
            ],
            [UserInput(label="motor_2.1", completer=motor_names)],
            [UserFileInput(label="path_3.1", defval="")],
            [
                Container(
                    [UserChoice(values=ch_values, defval=0, label="Select a motor")],
                    title="Motors",
                    border=1,
                )
            ],
        ],
        title=title,
        paddings=(1, 1),
    )

    return BlissWizard([dlg1, dlg2]).show()


def dlg_from_wardrobe(ward_robe):
    dico = ward_robe.to_dict()

    str_fields = []
    bool_option = []
    other = []
    for key, value in dico.items():

        if isinstance(value, str):
            str_fields.append(UserInput(label=key, defval=value))
        elif isinstance(value, bool):
            bool_option.append(UserCheckBox(label=key))
        else:
            other.append(UserInput(label=key, defval=value))

    user_dlgs = [
        [Container(str_fields, title="set options", border=1)],
        [Container(bool_option, title="enable options", border=1)],
    ]

    return BlissDialog(user_dlgs, title="WardRobe", paddings=(1, 1)).show()
