# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss shell utilities"""


def bind_key(repl, action, *keys, **kwargs):
    """
    Bind key(s) to a specific action

    *action* can be:

    - *callable*: it is ran in the terminal directly without showing which
      callable was executed
    - *string*: in this case the code is pasted into the CLI and then
      executed if the resulting line has no syntax error

    Example binding `wa()` to F2 key::
        
        from prompt_toolkit.keys import Keys
        from bliss.common.standard import wa
        from bliss.shell import repl_config, bind_key
        
        @repl_config
        def configure(repl):
            bind_key(repl, wa, Keys.F2)

    Args:
        repl: prompt-toolkit REPL
        action: if a callable is given, key press will trigger
                function call without arguments. if a string is
                given it will be feed into the console and executed.
        keys: key(s) to bind
        kwargs: any argument (ex: filter, eager) supported by 
                prompt-toolkit repl.add_key_binding()
    """

    @repl.add_key_binding(*keys, **kwargs)
    def _(event):
        if callable(action):
            event.cli.run_in_terminal(action)
        else:
            buff = event.cli.current_buffer
            buff.insert_text(action)
            if buff.accept_action.is_returnable:
                buff.accept_action.validate_and_handle(event.cli, buff)
