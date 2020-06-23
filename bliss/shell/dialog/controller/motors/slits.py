from bliss.shell.dialog.helpers import dialog, in_frange
from bliss.shell.cli.user_dialog import UserInput, Validator
from bliss.shell.cli.pt_widgets import BlissDialog
from bliss.shell.standard import ShellStr


@dialog("Slits", "set")
def slits_menu(obj):
    """Primary Slits dialog"""
    conf = obj.config.config_dict

    virtual_motors = {
        ax["name"]: {"tags": ax["tags"]}
        for ax in conf["axes"]
        if not ax["name"].startswith("$")
    }
    real_motors = {
        ax["name"][1:]: {"tags": ax["tags"]}
        for ax in conf["axes"]
        if ax["name"].startswith("$")
    }

    # virtual_motors will be like:
    # {"s1vg":{"tags":"vgap","obj":<bliss.common.axis.Axis object at ...>}}
    for name, dict_ in virtual_motors.items():
        dict_["obj"] = obj.axes[name]

    if len(virtual_motors) != 4 or len(real_motors) != 4:
        raise RuntimeError("Slits configuration problem")

    # sync real motors
    for name in real_motors.keys():
        obj.axes[name].sync_hard()

    dialogs = []

    for name, info in virtual_motors.items():
        assert name == info["obj"].name
        low, high = info["obj"].limits
        v = Validator(in_frange, low, high)
        dialogs.append(
            [
                UserInput(
                    label=f"Slit motor '{name}' tag '{info['tags']}' ({low},{high})",
                    defval=info["obj"].position,
                    validator=v,
                )
            ]
        )

    choices = BlissDialog(dialogs, title="Slits set", paddings=(3, 3)).show()

    if choices:
        out = "Done setting slits positions:"
        target_positions = zip(
            virtual_motors.keys(), (float(v) for v in choices.values())
        )

        for name, choice in target_positions:
            out += f"\n{name} to {choice}"
            obj.axes[name].move(choice)
        return ShellStr(out)
