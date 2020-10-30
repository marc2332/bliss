"""Repository of controllers used by the test suite only.

Example of usage

- name: loginitcontroller1
  plugin: bliss
  package: tests.controllers
  class: LogInitController

"""

# Import all controller classes to be made available to the config

from .loginitcontroller import *
