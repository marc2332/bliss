from bliss import global_map
from bliss.shell.cli.pt_widgets import select_dialog


def in_frange(str_input, mini, maxi):
    val = float(str_input)

    if val < mini:
        raise ValueError("value %s < %s (mini)" % (val, mini))

    if val > maxi:
        raise ValueError("value %s > %s (maxi)" % (val, maxi))

    return val


def list_axes():
    for axis in global_map.instance_iter("axes"):
        yield axis


def find_dialog(obj):
    """Finds the proper `dialog` class connected to the given object
    """
    try:
        name = obj.__name__
        dialog_classes = dialog.DIALOGS[name]
    except (AttributeError, KeyError):
        try:
            name = obj.__class__.__name__
            dialog_classes = dialog.DIALOGS[name]
        except (AttributeError, KeyError):
            return

    def display_dialog(dialog_type, *args, **kwargs):
        if dialog_type in dialog_classes:
            return dialog_classes[dialog_type](obj, *args, **kwargs)
        elif not dialog_type:
            if len(dialog_classes) == 1:
                # only one dialog is available => no need to specify
                _, display_func = dict(dialog_classes).popitem()
                return display_func(obj, *args, **kwargs)
            elif len(dialog_classes) > 1:
                # there are multiple dialogs => show main dialog to select sub-dialog
                title = f"Dialog Selection for {obj.name}"
                submenu_class = select_dialog(dialog_classes, title=title)
                if submenu_class:
                    display_func = dialog_classes[submenu_class]
                    return display_func(obj, *args, **kwargs)
            else:
                raise ValueError(
                    "Available dialogs types are: " + ", ".join(dialog_classes)
                )
        else:
            raise ValueError(
                "Wrong dialog type, available types are: " + ", ".join(dialog_classes)
            )

    return display_dialog


class dialog:
    """
    Class decorator that registers a dialog for a BLISS function or class
    """

    DIALOGS = {}

    def __init__(self, object_class_name, dialog_type, overwrite=False):
        self._object_class_name = object_class_name
        self._dialog_type = dialog_type
        self._overwrite = overwrite

    def __call__(self, dialog_func):
        name = self._object_class_name
        # associate the class name to a dialog type + dialog display function
        if name not in dialog.DIALOGS:
            dialog.DIALOGS[name] = {}
        if not self._overwrite and self._dialog_type in dialog.DIALOGS[name]:
            raise RuntimeError(
                f"Trying to register twice a dialog for {name} of type {self._dialog_type}"
            )

        dialog.DIALOGS[name][self._dialog_type] = dialog_func

        return dialog_func
