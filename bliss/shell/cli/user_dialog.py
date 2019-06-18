#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

""" Module providing dialogs to interact with the user """

# try:
from bliss.shell.cli.pt_widgets import BlissDialog

# except:
#    try:
#        from bliss.shell.cli.qt_widgets import BlissDialog
#    except:
#        raise ImportError

# =========================================================================================


class _UserDlg:
    def __init__(
        self,
        wtype=None,
        label="",
        values=None,
        defval=None,
        validator=None,
        completer=None,
        text_align=None,
        text_expand=True,
    ):
        self.wtype = wtype
        self.label = label
        self.values = values
        self.defval = defval
        self.validator = validator
        self.completer = completer
        self.text_align = text_align  # "CENTER" "LEFT" "JUSTIFY" "RIGHT"
        self.text_expand = text_expand


class UserYesNo(_UserDlg):
    """ A simple question, expecting YES or NO as an answer """

    def __init__(self, label="Do you want to continue?", defval=False):
        super().__init__(wtype="yesno", label=label, defval=defval)


class UserMsg(_UserDlg):
    """ A simple message (=label) to be displayed """

    def __init__(self, label="This is a message!", text_align=None, text_expand=True):
        super().__init__(
            wtype="msg", label=label, text_align=text_align, text_expand=text_expand
        )


class UserInput(_UserDlg):
    """ Ask the user to enter/type a value (string, integer, float, ...) """

    def __init__(
        self,
        label="",
        defval="",
        validator=None,
        completer=None,
        text_align=None,
        text_expand=False,
    ):
        super().__init__(
            wtype="input",
            label=label,
            defval=defval,
            validator=validator,
            completer=completer,
            text_align=text_align,
            text_expand=text_expand,
        )


class UserIntInput(_UserDlg):
    """ Ask the user to enter/type an integer value """

    def __init__(self, label="", defval=0, text_align=None, text_expand=False):
        super().__init__(
            wtype="input",
            label=label,
            defval=defval,
            validator=check["int"],
            text_align=text_align,
            text_expand=text_expand,
        )


class UserFloatInput(_UserDlg):
    """ Ask the user to enter/type a float value """

    def __init__(self, label="", defval=0.0, text_align=None, text_expand=False):
        super().__init__(
            wtype="input",
            label=label,
            defval=defval,
            validator=check["float"],
            text_align=text_align,
            text_expand=text_expand,
        )


class UserFileInput(_UserDlg):
    """ Ask the user to enter/type a value (string, integer, float, ...) """

    def __init__(
        self,
        label="",
        defval="",
        validator=None,
        completer=None,
        text_align=None,
        text_expand=False,
    ):
        super().__init__(
            wtype="file_input",
            label=label,
            defval=defval,
            validator=validator,
            completer=completer,
            text_align=text_align,
            text_expand=text_expand,
        )


class UserChoice(_UserDlg):
    """ Ask the user to select one value among values (radio list).
        label : a label on top of the radio list (optional). 
        values: list of (value,label) tuples. ex: values = [(1,"choice1"), (2,"choice2"), (3,"choice3")]
        defval : the index of the value selected as default.  
    """

    def __init__(
        self, label=None, values=[], defval=0, text_align=None, text_expand=True
    ):
        super().__init__(
            wtype="choice",
            label=label,
            values=values,
            defval=defval,
            text_align=text_align,
            text_expand=text_expand,
        )


class UserCheckBox(_UserDlg):
    """ Ask the user to enable or disable an option.
        defval : the default values for the option (True=checked, False=unchecked).  
    """

    def __init__(self, label="", defval=False):
        super().__init__(wtype="checkbox", label=label, defval=defval)


class Container:
    def __init__(self, user_dlg_list, title=None, border=0, padding=0, splitting="h"):
        self.wtype = "container"
        self.dlgs = user_dlg_list
        self.title = title
        self.border = border
        self.padding = padding
        self.splitting = splitting


class Validator:
    def __init__(self, func, *args):
        self.func = func
        self.args = args

    def check(self, str_input):
        if self.args is not None:
            return self.func(str_input, *self.args)
        else:
            return self.func(str_input)


def is_int(str_input):
    return int(str_input)


def is_float(str_input):
    return float(str_input)


def in_frange(str_input, mini, maxi):
    val = float(str_input)

    if val < mini:
        raise ValueError("value %s < %s (mini)" % (val, mini))

    if val > maxi:
        raise ValueError("value %s > %s (maxi)" % (val, maxi))

    return val


check = {
    "int": Validator(is_int),
    "float": Validator(is_float),
    "frange": Validator(in_frange, 5, 10),
}


class BlissWizard:
    def __init__(self, bliss_dlgs):
        self.dlgs = bliss_dlgs

    def show(self):
        allres = []

        for dlg in self.dlgs:
            ans = dlg.show()
            if ans is False:
                return False
            else:
                allres.append(ans)

        return allres
