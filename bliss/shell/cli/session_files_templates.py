# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016-2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Templates of configuration files used to create new sessions.
"""

from jinja2 import Template


xxx_setup_py_template = Template("""
from bliss import setup_globals

load_script(\"{{ name }}.py\")

print(\"\")
print(\"Welcome to your new '{{ name }}' BLISS session !! \")
print(\"\")
print(\"You can now customize your '{{ name }}' session by changing files:\")
print(\"   * {{ dir }}/{{ name }}_setup.py \")
print(\"   * {{ dir }}/{{ name }}.yml \")
print(\"   * {{ dir }}/scripts/{{ name }}.py \")
print(\"\")
""")


xxx_py_template = Template("""
from bliss.shell.cli import configure
from bliss.shell.cli.layout import AxisStatus, LabelWidget, DynamicWidget
from bliss.shell.cli.esrf import Attribute, FEStatus, IDStatus, BEAMLINE

import time

def what_time_is_it():
    return time.ctime()

@configure
def config(repl):
    repl.bliss_bar.items.append(LabelWidget(\"BL=ID245c\"))
    repl.bliss_bar.items.append(AxisStatus('simot1'))
    repl.bliss_bar.items.append(DynamicWidget(what_time_is_it))
""")
