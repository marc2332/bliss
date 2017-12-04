# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import inspect

from distutils.cmd import Command
from setuptools import setup, find_packages

try:
    from sphinx.setup_command import BuildDoc
except ImportError:
    BuildDoc = None


TESTING = any(x in sys.argv for x in ['test', 'pytest'])


def abspath(*path):
    """A method to determine absolute path for a given relative path to the
    directory where this setup.py script is located"""
    setup_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(setup_dir, *path)


def find_commands(module):
    """
    Finds instances of distutils.Command in a module.
    Returns an iterator
    """
    items = (getattr(module, item) for item in dir(module)
             if not item.startswith('_'))
    classes = (item for item in items if inspect.isclass(item))
    commands = (cls for cls in classes if issubclass(cls, Command))
    local_commands = (cmd for cmd in commands
                      if cmd.__module__.startswith('extensions.'))
    return dict(((cmd.cmd_name, cmd) for cmd in local_commands))


def find_extensions():
    """Find bliss extensions. Returns a list of distutils.Command"""
    top = abspath('extensions')
    # list with 'extension.sip', 'extension.cython', ...
    ext_type_names = ('extensions.' + name for name in os.listdir(top)
                      if not name.startswith('__') and \
                         os.path.isdir(os.path.join(top, name)))

    commands = {}
    for ext_type_name in ext_type_names:
        try:
            ext_type_module = __import__(ext_type_name, None, None,
                                         ext_type_name)
            for ext_name in ext_type_module.__all__:
                ext_name = ext_type_name + '.' + ext_name
                ext_module = __import__(ext_name, None, None, ext_name)
                commands.update(find_commands(ext_module))
        except Exception:
            continue

    return commands


def main():
    """run setup"""

    meta = {}
    execfile(abspath('bliss', 'release.py'), meta)

    packages = find_packages(where=abspath(), exclude=('extensions*',))

    cmd_class = find_extensions()
    if BuildDoc is not None:
        cmd_class['build_doc'] = BuildDoc

    setup(name=meta['name'],
          author=meta['author'],
          version=meta['version'],
          description=meta['description'],
          license=meta['license'],
          url=meta['url'],
          package_dir={"bliss": "bliss"},
          packages=packages,
          package_data={"bliss.config.redis": ["redis.conf"],
                        "bliss.config.plugins": ["*.html"],
                        "bliss.config.conductor.web": ["*.html",
                                                       "css/*.*",
                                                       "css/jstree/*.*",
                                                       "js/*.*",
                                                       "res/*.*"],
                        'bliss.shell.web': ['*.html', 'css/*.css', "js/*.js"]},
          cmdclass=cmd_class,
          scripts=["bin/beacon-server-list", 'bin/bliss_webserver',
                   'bin/sps_data_watch', 'bin/flint'],
          entry_points={
              'console_scripts': [
                  'bliss = bliss.shell.cli.main:main',
                  'bliss-emulator = bliss.controllers.emulator:main',
                  'beacon-server = bliss.config.conductor.server:main',
                  'bliss-ct2-server = bliss.controllers.ct2.server:main',
              ],
          },
          tests_require=['pytest-mock', 'pytest-coverage', 'h5py'],
          setup_requires=['pytest-runner'] if TESTING else [],
         )


if __name__ == "__main__":
    main()
