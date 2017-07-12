# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import argparse

from setuptools import setup

from distutils.command.build import build
from distutils.command.install import install
from distutils.unixccompiler import UnixCCompiler

from sphinx.setup_command import BuildDoc

try:
    import sipdistutils
    from extensions import sip as sip_modules
except ImportError:
    sipdistutils = None

TESTING = any(x in sys.argv for x in ['test', 'pytest'])


def abspath(*path):
    """A method to determine absolute path for a given relative path to the
    directory where this setup.py script is located"""
    setup_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(setup_dir, *path)


def get_packages_path():
    packages_path = ['bliss']
    for sub_package in os.listdir('bliss'):
        if os.path.isdir(os.path.join('bliss', sub_package)):
            full_package_path = os.path.join('bliss', sub_package)
            packages_path.extend(
                dirnames
                for dirnames, _, filenames in os.walk(full_package_path)
                if '__init__.py' in filenames)

    return [dirname.replace(os.path.sep, '.') for dirname in packages_path]


def get_release():
    with open(abspath('bliss', '__init__.py')) as f:
        raw = '\n'.join(line for line in f if line.startswith('__'))
    dct = {}
    exec(raw, dct)
    return dct


def get_options():
    user_options = []
    if sipdistutils is not None:
        for module_name in sip_modules.__all__:
            try:
                m = __import__('extensions.sip.%s' % (module_name),
                               None, None, 'extensions.sip.%s' % (module_name))
            except ImportError:
                print("Warning optional sip module %s can't be compile, "
                      "dependency not satisfied." % module_name)
                continue
            else:
                try:
                    func = getattr(m, 'get_options')
                except AttributeError:
                    continue
                else:
                    user_options.extend(func())
    return user_options


def get_sip_extension(extra_option):
    sip_extension_modules = []
    if sipdistutils is not None:
        for module_name in sip_modules.__all__:
            try:
                m = __import__('extensions.sip.%s' % (module_name),
                               None, None, 'extensions.sip.%s' % (module_name))
            except ImportError:
                continue
            else:
                try:
                    func = getattr(m, 'get_sip_extension')
                except AttributeError:
                    continue
                else:
                    sip_extension_modules.extend(func(extra_option))
    return sip_extension_modules


extra_option = {}


def _initialize_options(self):
    from distutils.fancy_getopt import longopt_xlate
    for option, _, _ in get_options():
        option = option.translate(longopt_xlate)
        if option[-1] == "=":
            option = option[:-1]
        self.__dict__[option] = None
        extra_option[option] = None


def _finalize_options(self):
    for key in extra_option:
        extra_option[key] = self.__dict__[key]


class BlissBuild(build):
    user_options = build.user_options + get_options()
    boolean_options = build.boolean_options + \
        [x[0] for x in get_options() if x[0][:-1] != '=']

    def __init__(self, *args, **keys):
        build.__init__(self, *args, **keys)
        self._args = {}

    def initialize_options(self):
        build.initialize_options(self)
        _initialize_options(self)

    def finalize_options(self):
        build.finalize_options(self)
        _finalize_options(self)


class BlissInstall(install):
    user_options = install.user_options + get_options()
    boolean_options = install.boolean_options + \
        [x[0] for x in get_options() if x[0][:-1] != '=']

    def __init__(self, *args, **keys):
        install.__init__(self, *args, **keys)
        self._args = {}

    def initialize_options(self):
        install.initialize_options(self)
        _initialize_options(self)

    def finalize_options(self):
        install.finalize_options(self)
        _finalize_options(self)


release = get_release()
cmdclass = {'build': BlissBuild,
            'install': BlissInstall,
            'build_doc': BuildDoc, }

setup(name="bliss",
      version=release['__version__'],
      description=release['__description__'],
      author=release['__author__'],
      package_dir={"bliss": "bliss"},
      packages=get_packages_path(),
      package_data={"bliss.config.redis": ["redis.conf"],
                    "bliss.config.plugins": ["*.html"],
                    "bliss.config.conductor.web": ["*.html",
                                                   "css/*.*",
                                                   "css/jstree/*.*",
                                                   "js/*.*",
                                                   "res/*.*"],
                    'bliss.shell.web': ['*.html', 'css/*.css', "js/*.js"]},
      scripts=["bin/beacon-server-list", "bin/bliss", 'bin/bliss_webserver',
               'bin/sps_data_watch', 'bin/flint'],
      entry_points={
          'console_scripts':
              ['bliss-emulator=bliss.controllers.emulator:main',
               'beacon-server=bliss.config.conductor.server:main']},
      cmdclass=cmdclass,

      tests_require=['pytest-mock', 'pytest-coverage', 'h5py'],
      setup_requires=['pytest-runner'] if TESTING else [],
      )

# remove user option from command argument
final_argv = []
long_options = set((x[0] for x in get_options()))
short_option = set((x[1] for x in get_options() if x[1] is not None))
for arg in sys.argv:
    pos = arg.find('=')
    opt = arg[:pos + 1] if pos > -1 else arg
    # long options
    if opt.startswith('--'):
        if opt[2:] in long_options:
            continue
    elif opt.startswith('-'):
        if opt[1:] in short_option:
            continue

    final_argv.append(arg)

sys.argv = final_argv
# Sip extension modules
all_sip_extension_modules = get_sip_extension(extra_option)

if all_sip_extension_modules:
    # merge module by sip_flags
    modules_by_sipflags = {}
    for extentions, sip_flags in all_sip_extension_modules:
        m_list = modules_by_sipflags.get(sip_flags, [])
        if isinstance(extentions, list):
            m_list.extend(extentions)
        else:
            m_list.append(extentions)
        modules_by_sipflags[sip_flags] = m_list

    for sip_flags, modules in modules_by_sipflags.iteritems():
        class build_ext(sipdistutils.build_ext):

            def initialize_options(self):
                sipdistutils.build_ext.initialize_options(self)
                self.sip_opts = ' '.join(('-g', '-e', sip_flags))

            def build_extensions(self):
                if isinstance(self.compiler, UnixCCompiler):
                    compiler_pars = self.compiler.compiler_so
                    while '-Wstrict-prototypes' in compiler_pars:
                        del compiler_pars[compiler_pars.index(
                            '-Wstrict-prototypes')]
                sipdistutils.build_ext.build_extensions(self)

        setup(
            name='bliss.siptools',
            version='1.0',
            ext_modules=modules,

            cmdclass={'build_ext': build_ext},
        )
