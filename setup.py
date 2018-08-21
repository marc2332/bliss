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

TESTING = any(x in sys.argv for x in ["test", "pytest"])


def abspath(*path):
    """A method to determine absolute path for a given relative path to the
    directory where this setup.py script is located"""
    setup_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(setup_dir, *path)


def find_commands(module):
    """
    Finds instances of distutils.Command in a module.
    Returns a dict<command name: command class>
    """
    items = (getattr(module, item) for item in dir(module) if not item.startswith("_"))
    classes = (item for item in items if inspect.isclass(item))
    commands = (cls for cls in classes if issubclass(cls, Command))
    local_commands = (
        cmd for cmd in commands if cmd.__module__.startswith("extensions.")
    )
    return dict(((cmd.cmd_name, cmd) for cmd in local_commands))


def find_extensions():
    """Find bliss extensions. Returns a list of distutils.Command"""
    top = abspath("extensions")
    commands = {}
    for name in os.listdir(top):
        if name.startswith("_"):
            continue
        full_name = os.path.join(top, name)
        if os.path.isdir(full_name):
            ext_type_name = "extensions." + name
            try:
                ext_type_module = __import__(ext_type_name, None, None, ext_type_name)
                for ext_name in ext_type_module.__all__:
                    ext_name = ext_type_name + "." + ext_name
                    ext_module = __import__(ext_name, None, None, ext_name)
                    commands.update(find_commands(ext_module))
            except Exception:
                continue
        else:
            # must be a python module
            name, ext = os.path.splitext(name)
            if ext != ".py":
                continue
            ext_name = "extensions." + name
            try:
                ext_module = __import__(ext_name, None, None, ext_name)
                commands.update(find_commands(ext_module))
            except Exception:
                continue
    return commands


def main():
    """run setup"""

    py_xy = sys.version_info[:2]
    py_xy_str = ".".join(map(str, py_xy))

    if py_xy < (2, 7) or py_xy >= (3, 0):
        print(
            "Incompatible python version ({0}). Needs python 2.x "
            "(where x > 6).".format(py_xy_str)
        )
        sys.exit(1)

    meta = {}
    execfile(abspath("bliss", "release.py"), meta)

    packages = find_packages(where=abspath(), exclude=("extensions*",))

    cmd_class = find_extensions()

    install_requires = [
        "redis  >= 2.8",
        "PyYaml",
        "netifaces < 0.10.5",
        "louie",
        "jinja2 >= 2.7",
        "flask",
        "treelib",
        "gipc",
        "jedi",
        "ptpython >= 0.39",
        "docopt",
        "bottle",
        "six >= 1.10",
        "tabulate",
        "pyserial == 2.7",
        "ruamel.yaml == 0.11.15",
        "zerorpc",
        "msgpack_numpy",
        "blessings",
        "h5py",
        "gevent >= 1.3.5",
        "pygments",
        "numpy >= 1.13",
        'enum34 ; python_version < "3.4"',
        "h5py",
        "mendeleev",
        "pint",
        'mock ; python_version < "3.3"',
        "futures",
        'silx >= 0.8 ; platform_machine == "x86_64"',
        "psutil",
        "subprocess32",
        "requests",
    ]

    tests_require = ["pytest", "pytest-mock", "pytest-cov", "scipy", "gipc"]

    setup_requires = [
        #        'setuptools >= 37',
    ]

    if TESTING:
        setup_requires += ["pytest-runner"]

    setup(
        name=meta["name"],
        author=meta["author"],
        version=meta["version"],
        description=meta["description"],
        license=meta["license"],
        url=meta["url"],
        package_dir={"bliss": "bliss"},
        packages=packages,
        package_data={
            "bliss.config.redis": ["redis.conf"],
            "bliss.config.plugins": ["*.html"],
            "bliss.config.conductor.web": [
                "*.html",
                "css/*.*",
                "css/jstree/*.*",
                "js/*.*",
                "res/*.*",
            ],
            "bliss.shell.web": ["*.html", "css/*.css", "js/*.js"],
        },
        cmdclass=cmd_class,
        scripts=["bin/beacon-server-list", "bin/bliss_webserver", "bin/sps_data_watch"],
        entry_points={
            "console_scripts": [
                "bliss = bliss.shell.cli.main:main",
                "bliss-emulator = bliss.controllers.emulator:main",
                "beacon-server = bliss.config.conductor.server:main",
                "bliss-ct2-server = bliss.controllers.ct2.server:main",
                "bliss-flex-server = bliss.controllers.correlator.flex.server:main",
                "flint = bliss.flint:main",
                "CT2 = bliss.tango.servers.ct2_ds:main",
                "Bliss = bliss.tango.servers.bliss_ds:main",
                "BlissAxisManager =  bliss.tango.servers.axis_ds:main",
                "BlissTempManager = bliss.tango.servers.temp_ds:main",
                "Musst = bliss.tango.servers.musst_ds:main",
                "Nanodac = bliss.tango.servers.nanodac_ds:main",
                "FuelCell = bliss.tango.servers.fuelcell_ds:main",
                "Gpib = bliss.tango.servers.gpib_ds:main",
                "Keithley428 = bliss.tango.servers.keithley428_ds:main",
                "Multiplexer = bliss.tango.servers.multiplexer_ds:main",
                "LinkamDsc = bliss.tango.servers.linkamdsc_ds:main",
                "NanoBpm = bliss.tango.servers.nanobpm_ds:main",
                "NanoBpmServo = bliss.tango.servers.nanobpm_servo_ds:main",
            ]
        },
        install_requires=install_requires,
        tests_require=tests_require,
        setup_requires=setup_requires,
    )


if __name__ == "__main__":
    main()
