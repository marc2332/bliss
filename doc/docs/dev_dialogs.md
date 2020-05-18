# Integrating Dialogs in Bliss

To know more about dialogs API, see: [Dialogs](shell_dialogs.md) 

To know more about the `menu` command, see: [Show](shell_std_func.md#dialogs)

The following document will define the recomended way to integrate dialogs inside Bliss.

## User Interface to dialogs

The users will access dialogs using the `menu` function available in the Bliss shell
exported from `bliss.shell.standard`.


## Programmer interface to dialogs

This paragraph is about how to add your own dialogs to bliss or beamline repository
interacting with the `menu()` function.

What you have to do is simply define your function that takes as first argument
the object instance itself (on which you will operate) and decorate it with
`@dialog("MyClassName", "dialog_type")`.

This will register the dialog as available for this specific object or class of objects.

If you try to register the same Class twice you wil get an exception, but you
can force this with `@dialog("MyClassName", "dialog_type", overwrite=True)`.
This is to avoid unexpected behavior when you register twice the same name.

Full Example:

```python
from bliss.shell.dialog.helpers import dialog
from bliss.shell.cli.user_dialog import UserCheckBox
from bliss.shell.cli.pt_widgets import BlissDialog
from bliss.common.utils import grouped_with_tail


@dialog("Transfocator", "selection")
def transfocator_menu(obj, *args, **kwargs):
    """Transfocator Pinhole/Lens selection"""
    dialogs = []
    positions_list = obj.status_dict()
    for label, position in positions_list.items():
        type_ = "Pinhole" if label.startswith("P") else "Lens"
        num = label[1:]
        dialogs.append(UserCheckBox(label=f"{type_} n.{num}", defval=position))

    layout = []

    for gr in grouped_with_tail(dialogs, 6):
        layout.append(gr)

    choices = BlissDialog(
        layout,
        title="Transfocator selection (checked is IN, unchecked is OUT)",
        paddings=(3, 0),
    ).show()
    if choices:
        for n, position in enumerate(choices.values()):
            obj[n] = position
    return obj
```

- `@dialog("Transfocator", "selection")`: import this decorator from `bliss.shell.dialog.helpers`
  and decorate your function with the Class Name and dialog type.

- `obj`: this is the first argument received from `menu`.

- `*args, **kwargs`: further args received from `menu(obj, dialog_type, *args, **kwargs)`

- `return obj`: is not compulsory to return something. In some case is good to return obj because many bliss objects has implemented the `__info__` method that will display a status on Bliss shell. In some other cases could be too verbose or simply not necessary.
The idea is to return something that will display the result of your dialog operation. If you want to return and print something on the shell is recomended to simply use `ShellStr` from `bliss.common.utils`.

Plenty of examples can be found inside the `bliss/shell/dialogs` folder.

!!! Note
    Be aware that the dialog code should be imported to work.

    For the bliss package this is normally done inside `bliss/shell/dialog/__init__.py`.
