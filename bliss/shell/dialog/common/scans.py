from bliss.shell.dialog.helpers import dialog
from bliss.shell.cli.user_dialog import (
    UserInput,
    UserCheckBox,
    Validator,
    UserChoice,
    UserIntInput,
)
from bliss.shell.cli.pt_widgets import BlissDialog
from bliss.shell.dialog.helpers import in_frange, list_axes
from bliss.common.scans import ascan
from bliss.common.measurementgroup import get_active


@dialog("ascan", "run")
def ascan_dialog(obj, *args, **kwargs):
    """"""
    dialogs = []
    # Motor Selection
    axes_dict = {ax.name: ax for ax in list_axes()}
    axes = [(name, name) for name in axes_dict.keys()]
    if not axes:
        raise RuntimeError("No Axis defined in current session")
    if get_active() is None or not len(get_active().enabled):
        raise RuntimeError(
            "Active Measurement group has to be defined"
            " with at least one active counter"
        )

    dialogs.append(UserChoice(label="Select Axis", values=list(axes)))

    choices = BlissDialog([dialogs], title="Absolute Scan", paddings=(0, 0)).show()
    if not choices:
        return
    motor_name = list(choices.values())[0]
    motor = axes_dict[motor_name]

    dialogs = []
    low, high = motor.limits
    v = Validator(in_frange, low, high)
    start_sel = UserInput(label=f"Motor start value {motor.limits}", validator=v)
    stop_sel = UserInput(label=f"Motor stop value {motor.limits}", validator=v)
    intervals_sel = UserIntInput(label="Number of intervals")
    v = Validator(in_frange, 0, float("inf"))
    count_time_sel = UserInput(label="Count time", validator=v)
    save_sel = UserCheckBox(label="Save", defval=True)
    run_sel = UserCheckBox(label="Run", defval=True)
    choices = BlissDialog(
        [
            [start_sel],
            [stop_sel],
            [intervals_sel],
            [count_time_sel],
            [save_sel],
            [run_sel],
        ],
        title="Absolute Scan",
        paddings=(0, 0),
    ).show()
    if not choices:
        return
    choices = iter(choices.values())
    start = float(next(choices))
    stop = float(next(choices))
    intervals = int(next(choices))
    count_time = float(next(choices))
    save = bool(next(choices))
    run = bool(next(choices))
    ascan(motor, start, stop, intervals, count_time, save=save, run=run)
