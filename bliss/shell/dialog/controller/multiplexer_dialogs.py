
from bliss.shell.cli.user_dialog import UserChoice
from bliss.shell.cli.pt_widgets import BlissDialog


def multiplexer_dialog(mux_controller):
    status = mux_controller.getGlobalStat()
    values = mux_controller.getAllPossibleValues()

    lenmax = max(map(len, status.keys()))
    lenmax = max(25, lenmax)

    choices = list()
    for name in status.keys():
        label = "{0} {1}".format(name, "-" * (lenmax - len(name)))
        defval = values[name].index(status[name])
        vals = [(key, key) for key in values[name]]
        choices.append(UserChoice(name=name, label=label, values=vals, defval=defval))

    dialogs = list()
    if len(choices) > 5:
        for x in range(0, len(choices), 2):
            if x + 1 < len(choices):
                dialogs.append([choices[x], choices[x + 1]])
            else:
                dialogs.append([choices[x]])
    else:
        dialogs = [[choice] for choice in choices]

    ans = BlissDialog(dialogs, title=f"Multiplexer [{mux_controller.name}]").show()
    changes = dict()
    for key, val in ans.items():
        if val != status[key]:
            print(f"Switching {key} to {val}")
            mux_controller.switch(key, val)
