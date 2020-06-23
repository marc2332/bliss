from bliss.shell.cli.user_dialog import UserChoice, UserMsg
from bliss.shell.dialog.helpers import dialog
from bliss.common.utils import flatten
from bliss.shell.cli.pt_widgets import BlissDialog


@dialog("WhiteBeamAttenuatorMockup", "selection")
@dialog("WhiteBeamAttenuator", "selection")
def wba_menu(obj, *args, **kwargs):
    """Whitebeam attenuator dialog for foil selection"""
    dialogs = []
    exclude_first_result = False
    attenuators = [att["attenuator"] for att in obj.attenuators]  # objects
    attenuator_names = [att.name for att in attenuators]  # names
    for i, attenuator in enumerate(attenuators):
        positions_list = attenuator.positions_list
        indexes = {pos["label"]: i for i, pos in enumerate(positions_list)}
        values = [(pos["label"], pos["description"]) for pos in positions_list]
        axis = positions_list[0]["target"][0]["axis"]
        defval_label = attenuator.position  # actual position in string form
        try:
            defval = indexes[defval_label]  # numeric index of position
        except KeyError:
            defval = 0
            dialogs.append([UserMsg(label="WARNING! Attenuator position is UNKNOWN")])
            exclude_first_result = True

        dialogs.append(
            [
                UserChoice(
                    label=f"Attenuator motor {axis.name}", values=values, defval=defval
                )
            ]
        )
    choices = BlissDialog(
        dialogs, title="Attenuator foil selection", paddings=(3, 0)
    ).show()
    if choices:
        values = list(choices.values())
        if exclude_first_result:
            values = values[1:]
        values = flatten(list(zip(attenuator_names, values)))
        obj.move(flatten(values))
    return obj
