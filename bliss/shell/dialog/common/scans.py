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
from bliss.common.scans import anscan, dnscan, amesh, dmesh
from bliss.common.measurementgroup import get_active
from bliss.common.utils import flatten


@dialog("ascan", "run")
def ascan_dialog(obj, *args, **kwargs):
    return perform_anscan(1)


@dialog("a2scan", "run")
def a2scan_dialog(obj, *args, **kwargs):
    return perform_anscan(2)


@dialog("a3scan", "run")
def a3scan_dialog(obj, *args, **kwargs):
    return perform_anscan(3)


@dialog("a4scan", "run")
def a4scan_dialog(obj, *args, **kwargs):
    return perform_anscan(4)


@dialog("a5scan", "run")
def a5scan_dialog(obj, *args, **kwargs):
    return perform_anscan(5)


@dialog("dscan", "run")
def dscan_dialog(obj, *args, **kwargs):
    return perform_dnscan(1)


@dialog("d2scan", "run")
def d2scan_dialog(obj, *args, **kwargs):
    return perform_dnscan(2)


@dialog("d3scan", "run")
def d3scan_dialog(obj, *args, **kwargs):
    return perform_dnscan(3)


@dialog("d4scan", "run")
def d4scan_dialog(obj, *args, **kwargs):
    return perform_dnscan(4)


@dialog("d5scan", "run")
def d5scan_dialog(obj, *args, **kwargs):
    return perform_dnscan(5)


@dialog("amesh", "run")
def amesh_dialog(obj, *args, **kwargs):
    axes_dict = {ax.name: ax for ax in list_axes()}
    motors = motors_w_intervals_dialog(axes_dict, 2)
    options = options_mesh_dialog()
    if motors and options:
        count_time, backnforth, save, sleep_time, run = options
        return amesh(
            *flatten(motors),
            count_time,
            backnforth=backnforth,
            save=save,
            sleep_time=sleep_time,
            run=run,
        )


@dialog("dmesh", "run")
def dmesh_dialog(obj, *args, **kwargs):
    axes_dict = {ax.name: ax for ax in list_axes()}
    motors = motors_w_intervals_dialog(axes_dict, 2)
    options = options_mesh_dialog()
    if motors and options:
        count_time, backnforth, save, sleep_time, run = options
        return dmesh(
            *flatten(motors),
            count_time,
            backnforth=backnforth,
            save=save,
            sleep_time=sleep_time,
            run=run,
        )


def perform_anscan(n):
    axes_dict = {ax.name: ax for ax in list_axes()}
    motors = motors_dialog(axes_dict, n)
    options = options_scan_dialog()
    if motors and options:
        count_time, intervals, save, sleep_time, run = options
        return anscan(
            motors, intervals, count_time, save=save, sleep_time=sleep_time, run=run
        )


def perform_dnscan(n):
    axes_dict = {ax.name: ax for ax in list_axes()}
    motors = motors_dialog(axes_dict, n)
    options = options_scan_dialog()
    if motors and options:
        count_time, intervals, save, sleep_time, run = options
        return dnscan(
            motors, intervals, count_time, save=save, sleep_time=sleep_time, run=run
        )


def motors_dialog(axes_dict, n_axis):
    """Motor selection"""
    results = []

    axes = [(name, name) for name in axes_dict.keys()]
    if not axes:
        raise RuntimeError("No Axis defined in current session")
    if get_active() is None or not len(get_active().enabled):
        raise RuntimeError(
            "Active Measurement group has to be defined"
            " with at least one active counter"
        )

    for _ in range(n_axis):
        dialogs = []
        dialogs.append(UserChoice(label="Select Axis", values=list(axes)))
        choices = BlissDialog([dialogs], title="Axis selection", paddings=(0, 0)).show()
        if not choices:
            return
        motor_name = list(choices.values())[0]
        motor = axes_dict[motor_name]

        dialogs = []
        low, high = motor.limits
        v = Validator(in_frange, low, high)
        start_sel = UserInput(label=f"Motor start value {motor.limits}", validator=v)
        stop_sel = UserInput(label=f"Motor stop value {motor.limits}", validator=v)
        choices = BlissDialog(
            [[start_sel], [stop_sel]],
            title=f"Start and stop for motor {motor_name}",
            paddings=(0, 0),
        ).show()
        if not choices:
            return
        choices = iter(choices.values())
        start = float(next(choices))
        stop = float(next(choices))
        results.append((motor, start, stop))
        axes.remove((motor_name, motor_name))  # remove motor to not be selected again
    return results


def motors_w_intervals_dialog(axes_dict, n_axis):
    """Motor selection"""
    results = []

    axes = [(name, name) for name in axes_dict.keys()]
    if not axes:
        raise RuntimeError("No Axis defined in current session")
    if get_active() is None or not len(get_active().enabled):
        raise RuntimeError(
            "Active Measurement group has to be defined"
            " with at least one active counter"
        )

    for _ in range(n_axis):
        dialogs = []
        dialogs.append(UserChoice(label="Select Axis", values=list(axes)))
        choices = BlissDialog([dialogs], title="Axis selection", paddings=(0, 0)).show()
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
        choices = BlissDialog(
            [[start_sel], [stop_sel], [intervals_sel]],
            title=f"Start and stop for motor {motor_name}",
            paddings=(0, 0),
        ).show()
        if not choices:
            return
        choices = iter(choices.values())
        start = float(next(choices))
        stop = float(next(choices))
        intervals = int(next(choices))
        results.append((motor, start, stop, intervals))
        axes.remove((motor_name, motor_name))  # remove motor to not be selected again
    return results


def options_scan_dialog():
    v = Validator(in_frange, 0, float("inf"))
    count_time_sel = UserInput(label="Count time", validator=v)
    intervals_sel = UserIntInput(label="Number of intervals")
    save_sel = UserCheckBox(label="Save", defval=True)
    sleep_time = UserInput(label="Sleep time", validator=v, defval=0)
    run_sel = UserCheckBox(label="Run", defval=True)
    choices = BlissDialog(
        [[count_time_sel], [intervals_sel], [save_sel], [sleep_time], [run_sel]],
        title="Scan options selection",
        paddings=(0, 0),
    ).show()
    if not choices:
        return
    choices = iter(choices.values())
    count_time = float(next(choices))
    intervals = int(next(choices))
    save = bool(next(choices))
    sleep_time = float(next(choices))
    run = bool(next(choices))
    return count_time, intervals, save, sleep_time, run


def options_mesh_dialog():
    v = Validator(in_frange, 0, float("inf"))
    count_time_sel = UserInput(label="Count time", validator=v)
    backnforth = UserCheckBox(label="Back and forth", defval=False)
    save_sel = UserCheckBox(label="Save", defval=True)
    sleep_time = UserInput(label="Sleep time", validator=v, defval=0)
    run_sel = UserCheckBox(label="Run", defval=True)
    choices = BlissDialog(
        [[count_time_sel], [backnforth], [save_sel], [sleep_time], [run_sel]],
        title="Mesh options selection",
        paddings=(0, 0),
    ).show()
    if not choices:
        return
    choices = iter(choices.values())
    count_time = float(next(choices))
    backnforth = bool(next(choices))
    save = bool(next(choices))
    sleep_time = float(next(choices))
    run = bool(next(choices))
    return count_time, backnforth, save, sleep_time, run
