from bliss.common.utils import grouped_with_tail
from bliss.shell.dialog.helpers import dialog
from bliss.shell.cli.user_dialog import UserInput, UserCheckBox, Container, Validator
from bliss.shell.cli.pt_widgets import BlissDialog
from bliss.controllers.wago.helpers import int_to_register_type
from bliss.shell.dialog.helpers import in_frange


def get_fs_limits(reading_type: str):
    try:
        fs_low, fs_high = map(int, reading_type[2:].split("-"))
    except ValueError:
        fs_low = 0
        fs_high = int(reading_type[2:])
    return fs_low, fs_high


@dialog("WagoMockup", "set")
@dialog("Wago", "set")
def wago_menu(obj):
    """Wago dialog for setting analog and digital output"""
    keys = list(obj.modules_config.logical_keys.keys())

    reference = []  # store name, channels for later manipulation
    dialogs = []

    for name in keys:
        group = []
        for ch in obj.modules_config.read_table[name].keys():
            # getting only digitan and analog outputs
            # ty = obj.modules_config.read_table[k][ch]["module_reference"]

            key = obj.controller.devname2key(name)
            _, int_reg_type, _, _, _ = obj.controller.devlog2hard((key, ch))

            if int_to_register_type(int_reg_type) not in ("IB", "IW", "OB", "OW"):
                raise TypeError
            if int_to_register_type(int_reg_type) in ("IB", "IW"):
                # if is an input skip
                continue
            info = obj.modules_config.read_table[name][ch]["info"]
            # getting actual value
            val = obj.get(name, cached=True)
            try:
                # if logical_device has multiple channels extract it
                val = val[ch]
            except Exception:
                pass
            if info.reading_type == "digital":
                group.append(UserCheckBox(label=f"channel {ch}", defval=val))
            elif info.reading_type.startswith("fs"):
                # getting high and low limits for the value
                low, high = get_fs_limits(info.reading_type)

                v = Validator(in_frange, low, high)

                group.append(
                    UserInput(
                        label=f"channel {ch} ({low}-{high})",
                        defval=f"{val: .5}",
                        validator=v,
                    )
                )

            reference.append((key, ch, val))

        if len(group):
            dialogs.append(Container(group, title=f"{name}", splitting="h"))

    layout = []
    for gr in grouped_with_tail(dialogs, 4):
        layout.append(gr)
    choices = BlissDialog(layout, title="Wago values set", paddings=(0, 0)).show()
    if choices:
        values = zip(reference, choices.values())
        for ((key, ch, old_val), new_val) in values:
            new_val = float(new_val)
            if new_val != old_val:
                obj.controller.devwritephys([key, ch, new_val])
