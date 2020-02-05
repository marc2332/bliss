# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os

from sipdistutils import build_ext
from distutils.core import Extension

import numpy

try:
    import PyQt4.pyqtconfig as pyqtconfig_qt4
except ImportError:
    pyqtconfig_qt4 = None

try:
    import pyqtconfig
except ImportError:
    pyqtconfig = None

try:
    import sipconfig

    # get sip version
    str_version = sipconfig.version_to_string(sipconfig.Configuration().sip_version)
    versions = [int(x) for x in str_version.split(".")]
    major, minor = versions[0], versions[1]
except ImportError:
    sipconfig = None

base_path = os.path.join("bliss", "data", "routines", "pixmaptools")


class _BaseBuild(build_ext):

    user_options = []

    def initialize_options(self):
        build_ext.initialize_options(self)
        self.extension, sip_opts = self.initialize_sip_extension()
        self.sip_opts = " ".join(("-g", "-e", sip_opts))

    def finalize_options(self):
        build_ext.finalize_options(self)
        self.extensions = [self.extension]

    def build_extensions(self):
        compiler_pars = self.compiler.compiler_so
        while "-Wstrict-prototypes" in compiler_pars:
            del compiler_pars[compiler_pars.index("-Wstrict-prototypes")]
        build_ext.build_extensions(self)


class BuildPixmaptoolsQt3(_BaseBuild):

    cmd_name = "build_pixmaptools_qt3"
    description = "Build pixmaptools extension for Qt3"

    def initialize_sip_extension(self):
        if pyqtconfig is None:
            raise RuntimeError(
                "PyQt3 dev is not installed. Can't build " "pixmaptools extension"
            )
        # Get the PyQt configuration information.
        config = pyqtconfig.Configuration()
        qt_sip_flags = config.pyqt_qt_sip_flags

        # Local include
        include_dirs = [os.path.dirname(os.path.realpath(__file__))]
        # Extra include for numpy
        include_dirs += [numpy.get_include()]
        # Extra include for pyqt
        include_dirs += [config.qt_inc_dir]
        include_dirs.append(os.path.join(base_path, "qt3"))

        extra_compile_args = pyqtconfig._default_macros["CXXFLAGS"].split()
        extra_compile_args += pyqtconfig._default_macros["CXXFLAGS_THREAD"].split()
        extra_compile_args += pyqtconfig._default_macros["CXXFLAGS_WARN_ON"].split()

        extra_link_args = pyqtconfig._default_macros["LFLAGS"].split()

        library_dirs = pyqtconfig._default_macros["LIBDIR_QT"].split()
        extra_libs = ["qt-mt"]
        sources = ["pixmaptools_io.cpp", "pixmaptools_lut.cpp", "pixmaptools_stat.cpp"]
        if major == 4 and minor < 12:
            sources.append("pixmaptools_qt3_before_4_12.sip")
        else:
            sources.append("pixmaptools_qt3.sip")

        ext = Extension(
            "bliss.data.routines.pixmaptools.qt3",
            sources=[os.path.join(base_path, "qt3", x) for x in sources],
            include_dirs=include_dirs,
            extra_compile_args=extra_compile_args,
            extra_link_args=extra_link_args,
            library_dirs=library_dirs,
            libraries=extra_libs,
            language="c++",
        )
        sip_flags = " ".join(("-I", config.pyqt_sip_dir, qt_sip_flags))
        return ext, sip_flags


class BuildPixmaptoolsQt4(_BaseBuild):

    cmd_name = "build_pixmaptools_qt4"
    description = "Build pixmaptools extension for Qt4"

    def initialize_sip_extension(self):
        if pyqtconfig_qt4 is None:
            raise RuntimeError(
                "PyQt4 dev is not installed. Can't build " "pixmaptools extension"
            )
        # Get the PyQt configuration information.
        config = pyqtconfig_qt4.Configuration()
        qt_sip_flags = config.pyqt_sip_flags

        # Local include
        include_dirs = [os.path.dirname(os.path.realpath(__file__))]
        # Extra include for numpy
        include_dirs += [numpy.get_include()]
        # Extra include for pyqt
        include_dirs += [config.qt_inc_dir]
        include_dirs += [
            os.path.join(config.qt_inc_dir, x) for x in ["QtCore", "QtGui"]
        ]
        include_dirs.append(base_path)

        extra_compile_args = pyqtconfig_qt4._default_macros["CXXFLAGS"].split()
        extra_compile_args += pyqtconfig_qt4._default_macros["CXXFLAGS_THREAD"].split()
        extra_compile_args += pyqtconfig_qt4._default_macros["CXXFLAGS_WARN_ON"].split()

        extra_link_args = pyqtconfig_qt4._default_macros["LFLAGS"].split()

        library_dirs = pyqtconfig_qt4._default_macros["LIBDIR_QT"].split()
        extra_libs = ["QtCore", "QtGui"]
        sources = ["pixmaptools_io.cpp", "pixmaptools_lut.cpp", "pixmaptools_stat.cpp"]
        if major == 4 and minor < 12:
            sources.append("pixmaptools_before_4_12.sip")
        else:
            sources.append("pixmaptools.sip")
        ext = Extension(
            "bliss.data.routines.pixmaptools.qt4",
            sources=[os.path.join(base_path, x) for x in sources],
            include_dirs=include_dirs,
            extra_compile_args=extra_compile_args,
            extra_link_args=extra_link_args,
            library_dirs=library_dirs,
            libraries=extra_libs,
            language="c++",
        )

        sip_flags = " ".join(("-I", config.pyqt_sip_dir, qt_sip_flags))
        return ext, sip_flags
