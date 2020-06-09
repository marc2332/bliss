# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import inspect
import subprocess

from setuptools.extension import Extension
from setuptools import setup, find_packages

TESTING = any(x in sys.argv for x in ["test", "pytest"])

conda_base = os.environ.get("CONDA_PREFIX")
extensions = []
sip_extensions = []

build_flint = False  # sys.platform not in ["win32", "cygwin"]

if build_flint:
    poll = Extension(
        "bliss.common.poll_patch",
        sources=["extensions/c/poll/poll.c"],
        extra_compile_args=["-pthread"],
        libraries=["dl"],
    )
    extensions.append(poll)
    poll_patch = Extension(
        "bliss.flint.patches.poll_patch",
        sources=[
            "extensions/cython/flint/poll_patch.pyx",
            "extensions/cython/flint/poll_patch_init.c",
        ],
    )
    extensions.append(poll_patch)


def abspath(*path):
    """A method to determine absolute path for a given relative path to the
    directory where this setup.py script is located"""
    setup_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(setup_dir, *path)


def generate_release_file():
    dirname = os.path.dirname(__file__)
    try:
        process = subprocess.run(
            ["git", "describe", "--tags", "--always"], capture_output=True, cwd=dirname
        )
        if process.returncode:
            raise Exception("Not a git repository")
    except:
        version = "master"
    else:
        version = process.stdout.strip().decode()
    name = "bliss"
    author = "BCU (ESRF)"
    author_email = ""
    license = "LGPLv3"
    copyright = "2015-2020 Beamline Control Unit, ESRF"
    description = "BeamLine Instrumentation Support Software"
    url = "bliss.gitlab-pages.esrf.fr/bliss"

    src = f"""\
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# Single source of truth for the version number and the like

import os
import subprocess

dirname = os.path.dirname(__file__)

name = "{name}"
author = "{author}"
author_email = "{author_email}"
license = "{license}"
copyright = "{copyright}"
description = "{description}"
url = "{url}"
try:
    process = subprocess.run(
        ["git", "describe", "--tags", "--always"], capture_output=True, cwd=dirname
    )
    if process.returncode:
        raise Exception("Not a git repository")
except:
    short_version = version = "{version}"
else:
    short_version = version = process.stdout.strip().decode()

version_info = [x.split("-")[0] for x in version.split(".")]
"""
    with open(os.path.join(dirname, "bliss", "release.py"), "w") as f:
        f.write(src)
    return locals()


console_script_entry_points = [
    "bliss = bliss.shell.cli.main:main",
    "bliss-emulator = bliss.controllers.emulator:main",
    "beacon-server = bliss.config.conductor.server:main",
    "bliss-ct2-server = bliss.controllers.ct2.server:main",
    "bliss-flex-server = bliss.controllers.correlator.flex.server:main",
    "bliss-handel-server = bliss.controllers.mca.handel.server:main",
    "bliss-speedgoat-server = bliss.controllers.speedgoat.server:main",
    "flint = bliss.flint.flint:main",
    "CT2 = bliss.tango.servers.ct2_ds:main",
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
    "Wago = bliss.tango.servers.wago_ds:main",
    "NexusWriterService = nexus_writer_service.nexus_writer_service:main",
    "NexusSessionWriter = nexus_writer_service.subscribers.session_writer:main",
    "RegisterNexusWriter = nexus_writer_service.nexus_register_writer:main",
]

if sys.platform not in ["win32", "cygwin"]:
    console_script_entry_points.append("Bliss = bliss.tango.servers.bliss_ds:main")
else:
    # rename bliss device server on windows because commands are not case sensitive
    console_script_entry_points.append(
        "BlissServer = bliss.tango.servers.bliss_ds:main"
    )


def main():
    """run setup"""

    py = sys.version_info
    py_str = ".".join(map(str, py))

    if py < (3,):
        print(("Incompatible python version ({0}). Needs python 3.x ".format(py_str)))
        sys.exit(1)

    meta = generate_release_file()

    packages = find_packages(where=abspath(), exclude=("extensions*",))

    install_requires = [
        "redis >= 3",
        "hiredis",
        "louie >= 2",
        "netifaces",
        "jinja2 >= 2.7",
        "flask",
        "treelib",
        "jedi >= 0.16",
        "ptpython >= 2.0",
        "prompt_toolkit >= 2.0",
        "docopt",
        "tabulate",
        "pyserial > 2",
        "ruamel.yaml",
        "msgpack >= 0.6.1",
        "msgpack_numpy >= 0.4.4.2",
        'blessings; platform_machine == "x86_64"',
        "h5py",
        "gevent >= 1.4",
        "pygments",
        "numpy >= 1.13",
        "mendeleev",
        "pint",
        'silx >= 0.13.0b1; platform_machine == "x86_64"',
        "psutil",
        "requests",
        "cffi",
        'pygraphviz >= 1.5; platform_machine == "x86_64"',
        "networkx",
        "tblib",
        "sortedcontainers",
    ]

    tests_require = ["pytest >= 4.1.1", "pytest-cov >= 2.6.1", "scipy"]

    setup_requires = ["cython"]

    if TESTING:
        setup_requires += ["pytest-runner"]

    package_data = {
        "bliss.config.redis": ["redis.conf"],
        "bliss.config.plugins": ["*.html"],
        "bliss.config.conductor.web.configuration": [
            "*.html",
            "css/*.*",
            "js/*.*",
            "res/*.*",
        ],
        "bliss.config.conductor.web.homepage": [
            "*.html",
            "css/*.*",
            "js/*.*",
            "img/*.*",
        ],
        "bliss.shell.web": ["*.html", "css/*.css", "js/*.js"],
        "bliss.config": ["tmux.conf"],
        "bliss.flint.resources": [
            "logo/*.png",
            "logo/*.svg",
            "icons/*.png",
            "icons/*.svg",
            "icons/*.mng",
            "icons/*.gif",
            "icons/*/*.png",
            "gui/*.ui",
        ],
    }

    setup(
        name=meta["name"],
        author=meta["author"],
        version=meta["version"],
        description=meta["description"],
        license=meta["license"],
        url=meta["url"],
        package_dir={"bliss": "bliss", "nexus_writer_service": "nexus_writer_service"},
        packages=packages,
        package_data=package_data,
        ext_modules=extensions,
        scripts=[
            "bin/beacon-server-list",
            "bin/SlitsSimulationLimaCCDs",
            "bin/TomoSimulationLimaCCDs",
        ],
        entry_points={"console_scripts": console_script_entry_points},
        install_requires=install_requires,
        tests_require=tests_require,
        setup_requires=setup_requires,
    )


if __name__ == "__main__":
    main()
