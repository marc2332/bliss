from bliss.shell.dialog.helpers import dialog
from bliss.shell.cli.user_dialog import UserCheckBox
from bliss.shell.cli.pt_widgets import BlissDialog


@dialog("MeasurementGroup", "selection")
def measurement_group_selection(obj, *args, **kwargs):
    dialogs = []
    counters_info = []
    for fullname in obj.available:
        if fullname in obj.enabled:
            counters_info.append((fullname, True))
        else:
            counters_info.append((fullname, False))

    for fullname, enabled in counters_info:
        dialogs.append([UserCheckBox(label=fullname, defval=enabled)])

    choices = BlissDialog(
        dialogs, title=f"MeasurementGroup {obj.name} Counter selection", paddings=(0, 0)
    ).show()
    if choices:
        values = list(zip(obj.available, choices.values()))
        for fullname, enabled in values:
            if enabled:
                obj.enable(fullname)
            else:
                obj.disable(fullname)
