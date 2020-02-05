# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Templates of configuration files used to create new sessions.
"""

from jinja2 import Template


xxx_setup_py_template = Template(
    """
from bliss.setup_globals import *

load_script(\"{{ name }}.py\")

print(\"\")
print(\"Welcome to your new '{{ name }}' BLISS session !! \")
print(\"\")
print(\"You can now customize your '{{ name }}' session by changing files:\")
print(\"   * {{ dir }}/{{ name }}_setup.py \")
print(\"   * {{ dir }}/{{ name }}.yml \")
print(\"   * {{ dir }}/scripts/{{ name }}.py \")
print(\"\")
"""
)


xxx_py_template = Template(
    """
"""
)
