
# Terminal issues

BLISS uses *ptpython* to run sessions in a terminal.

## Terminal scrolling

Symptom: Can not scroll up in the BLISS session terminal

Issue: Trying to scroll up on some terminal is immediately canceled by
a return to the the last line.

* Fix for xfce4-terminal:

        Fix: Edit-> Preferences -> General: Untick `Scroll on output`
	         Click on `Close` and "Voila !"


## Terminal color scheme

BLISS terminal color scheme can be changed by adding :

    repl.use_code_colorscheme('pastie')
to the config file (`sessions/scripts/<session>.py`) of the session.

example :

    from bliss.shell.cli import configure
    
    @configure
    def config(repl):
        repl.bliss_bar.items.append(LabelWidget("BL=ID42c"))

        # Color scheme change.
        repl.use_code_colorscheme('pastie')
