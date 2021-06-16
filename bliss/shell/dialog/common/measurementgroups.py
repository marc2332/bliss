from bliss.shell.dialog.helpers import dialog
from bliss.shell.cli.user_dialog import UserCheckBoxList
from bliss.shell.cli.pt_widgets import BlissDialog


@dialog("MeasurementGroup", "selection")
def measurement_group_selection(obj, *args, **kwargs):

    values = []
    selection = []
    for fullname in obj.available:
        label = fullname
        values.append((fullname, label))
        if fullname in obj.enabled:
            selection.append(fullname)

    widget = UserCheckBoxList(label="Counters", values=values, defval=selection)
    result = BlissDialog(
        [[widget]],
        title=f"MeasurementGroup {obj.name} Counter selection",
        paddings=(0, 0),
    ).show()

    if result:
        selection = set(result[widget])
        for fullname, label in values:
            enabled = fullname in selection
            if enabled:
                obj.enable(fullname)
            else:
                obj.disable(fullname)
