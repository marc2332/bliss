from distutils.core import setup, Extension
from distutils.unixccompiler import UnixCCompiler
import sipdistutils
import PyQt4.pyqtconfig as pyqtconfig
import numpy
import os

# Get the PyQt configuration information.
config = pyqtconfig.Configuration()
qt_sip_flags = config.pyqt_sip_flags

#Local include
include_dirs = [os.path.dirname(os.path.realpath(__file__))]
#Extra include for numpy
include_dirs += [numpy.get_include()]
#Extra include for pyqt
include_dirs += [config.qt_inc_dir]
include_dirs += [os.path.join(config.qt_inc_dir,x) for x in ['QtCore','QtGui']]

extra_compile_args = pyqtconfig._default_macros['CXXFLAGS'].split()
extra_compile_args += pyqtconfig._default_macros['CXXFLAGS_THREAD'].split()
extra_compile_args += pyqtconfig._default_macros['CXXFLAGS_WARN_ON'].split()

extra_link_args = pyqtconfig._default_macros['LFLAGS'].split()

library_dirs = pyqtconfig._default_macros['LIBDIR_QT'].split()
extra_libs = ['QtCore','QtGui']

class build_ext(sipdistutils.build_ext):

    def initialize_options (self):
        sipdistutils.build_ext.initialize_options(self)
        self.sip_opts = ' '.join(('-g','-e','-I', config.pyqt_sip_dir,qt_sip_flags))

    def build_extensions(self):
        if isinstance(self.compiler, UnixCCompiler):
            compiler_pars = self.compiler.compiler_so
            while '-Wstrict-prototypes' in compiler_pars:
                del compiler_pars[compiler_pars.index('-Wstrict-prototypes')]
        sipdistutils.build_ext.build_extensions(self)

setup(
  name = 'pixmaptools',
  version = '1.0',
  ext_modules=[
    Extension("pixmaptools",
              sources = ['pixmaptools_io.cpp','pixmaptools_lut.cpp',
                         'pixmaptools_stat.cpp','pixmaptools.sip'],
              include_dirs = include_dirs,
              extra_compile_args=extra_compile_args,
              extra_link_args = extra_link_args,
              library_dirs = library_dirs,
              libraries = extra_libs,
              language = 'c++',
          ),

    ],

    cmdclass = {'build_ext': build_ext},
)
