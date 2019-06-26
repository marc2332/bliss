# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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

build_flint = sys.platform not in ["win32", "cygwin"]

try:
    from Cython.Build import cythonize
except ImportError:
    cython = False
    cythonize = lambda ext: [ext]
else:
    cython = True

if build_flint:
    # need qt headers and lib
    if conda_base is not None:
        qt_include_dirs = [os.path.join(conda_base, "include", "qt")]
        qt_library_dirs = [os.path.join(conda_base, "lib")]
    else:
        qt_include_dirs = []
        qt_library_dirs = []

    if cython:
        sources = [
            "extensions/cython/flint/qwindowsystem.pyx",
            "extensions/cython/flint/q_window_system.cpp",
        ]
    else:
        sources = [
            "extensions/cython/flint/qwindowsystem.cpp",
            "extensions/cython/flint/q_window_system.cpp",
        ]

    flint_extension = Extension(
        "bliss.flint.qwindowsystem",
        include_dirs=qt_include_dirs,
        library_dirs=qt_library_dirs,
        extra_compile_args=["-std=c++11"],
        libraries=["Qt5Gui"],
        language="c++",
        sources=sources,
    )

    extensions.extend(cythonize(flint_extension))


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
    copyright = "2015-2019 Beamline Control Unit, ESRF"
    description = "BeamLine Instrumentation Support Software"
    url = "bliss.gitlab-pages.esrf.fr/bliss"

    src = f"""\
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
        "louie",
        "netifaces",
        "jinja2 >= 2.7",
        "flask",
        "treelib",
        "jedi",
        "ptpython >= 2.0",
        "prompt_toolkit >= 2.0",
        "docopt",
        "tabulate",
        "pyserial > 2",
        "pyyaml >= 5.1",
        "msgpack >= 0.6.1",
        "msgpack_numpy >= 0.4.4.2",
        "blessings",
        "h5py",
        "gevent >= 1.4",
        "pygments",
        "numpy >= 1.13",
        "mendeleev",
        "pint",
        'silx == 0.10.1; platform_machine == "x86_64"',
        "psutil",
        "requests",
        "cffi",
        "pygraphviz >= 1.5",
        "networkx",
    ]

    tests_require = ["pytest >= 4.1.1", "pytest-cov >= 2.6.1", "scipy"]

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
            "bliss.config": ["tmux.conf"],
        },
        ext_modules=extensions,
        scripts=["bin/beacon-server-list", "bin/sps_data_watch"],
        entry_points={
            "console_scripts": [
                "bliss = bliss.shell.cli.main:main",
                "bliss-emulator = bliss.controllers.emulator:main",
                "beacon-server = bliss.config.conductor.server:main",
                "bliss-ct2-server = bliss.controllers.ct2.server:main",
                "bliss-flex-server = bliss.controllers.correlator.flex.server:main",
                "bliss-handel-server = bliss.controllers.mca.handel.server:main",
                "bliss-speedgoat-server = bliss.controllers.speedgoat.server:main",
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
