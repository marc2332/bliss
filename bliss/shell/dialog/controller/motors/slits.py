from bliss.shell.dialog.helpers import dialog, in_frange
from bliss.shell.cli.user_dialog import UserInput, Validator
from bliss.shell.cli.pt_widgets import BlissDialog
from bliss.shell.standard import ShellStr


@dialog("Slits", "set")
def slits_menu(obj):
    """Slits dialog"""
    virtual_motors = {mot.name: (mot, mot.config) for mot in obj.pseudos}
    real_motors = {mot.name: (mot, mot.config) for mot in obj.reals}
    if len(virtual_motors) != 4 or len(real_motors) != 4:
        raise RuntimeError("Slits configuration problem")

    dialogs = []

    for name, (mot, info) in virtual_motors.items():
        low, high = mot.limits
        v = Validator(in_frange, low, high)
        dialogs.append(
            [
                UserInput(
                    label=f"Slit motor '{name}' tag '{info.get('tags')}' ({low},{high})",
                    defval=mot.position,
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
