# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
from types import ModuleType
import functools

from bliss import setup_globals
from bliss.config import static
from bliss.config.conductor.client import get_config_file,get_python_modules,get_file

DEFAULT_SESSION = None

def get_default():
   return DEFAULT_SESSION

_importer_path = set()

class _StringImporter(object):
   BASE_MODULE_NAME_SPACE='bliss.setup'
   SUB_NAME_SPACE='scripts'

   def __init__(self, path,session_name):
      self._modules = dict()
      global_module_name_space = '%s.%s' % (self.BASE_MODULE_NAME_SPACE,
                                            self.SUB_NAME_SPACE)
      session_module_name_space = '%s.%s' % (self.BASE_MODULE_NAME_SPACE,
                                             session_name)
      for module_name,file_path in get_python_modules(path):
         for mod_namespace in (global_module_name_space,session_module_name_space):
            self._modules['%s.%s' % (mod_namespace,module_name)] = file_path
      if self._modules:
         self._modules[self.BASE_MODULE_NAME_SPACE] = None
         self._modules['%s.%s' % (self.BASE_MODULE_NAME_SPACE,self.SUB_NAME_SPACE)] = None
         self._modules['%s.%s' % (self.BASE_MODULE_NAME_SPACE,session_name)] = None

   def find_module(self, fullname, path):
      if fullname in self._modules:
         return self
      return None

   def load_module(self, fullname):
      if not fullname in self._modules.keys():
         raise ImportError(fullname)

      file_name = self._modules.get(fullname)
      if file_name:
         data_file = get_config_file(file_name)
      else:
         file_name = '%s (__init__ memory)' % fullname
         data_file = ''         # empty __init__.py

      new_module = sys.modules.get(fullname,
                                   ModuleType(fullname))
      new_module.__loader__ = self
      module_filename = 'beacon://%s' % file_name
      new_module.__file__ = module_filename
      if file_name.find('__init__') > -1:
         new_module.__path__ = []
         new_module.__package__ = fullname
      else:
         new_module.__package__ = fullname.rpartition('.')[0]
      sys.modules.setdefault(fullname,new_module)
      c_code = compile(data_file,module_filename,'exec')
      exec(c_code,new_module.__dict__)
      return new_module
  
class Session(object):
   def __init__(self,name,config_tree):
      self.__name = name
      self._config_tree = config_tree
      self._synoptic_file = config_tree.get('svg-file')
      self._config_objects_names = config_tree.get("config-objects")
      self._exclude_objects_names = config_tree.get("exclude-objects")

      global DEFAULT_SESSION
      if(DEFAULT_SESSION is None or 
         config_tree.get('default',False)):
         DEFAULT_SESSION = self

   @property
   def name(self):
      return self.__name

   @property
   def object_names(self):
      return self._config_objects_names

   def setup(self,
             env_dict = None,verbose = False):
      try:
         with get_file(self._config_tree,'setup-file') as setup_file:
            base_path = os.path.dirname(self._config_tree.filename)
            module_path = os.path.join(base_path,'scripts')
            
            if env_dict is None:
               # does Python run in interactive mode?
               import __main__ as main
               if not hasattr(main, '__file__'):
                  # interactive interpreter 
                  env_dict = main.__dict__
               else:
                  env_dict = globals()

            if isinstance(self._config_objects_names,(str,unicode)):
               config_objects = self._config_objects_names.split()
            else:
               config_objects = self._config_objects_names

            if isinstance(self._exclude_objects_names,(str,unicode)):
               exclude_objects = self._exclude_objects_names.split()
            else:
               exclude_objects = self._exclude_objects_names or []

            exclude_objects.append(self.name)

            self._load_config(env_dict, config_objects, exclude_objects, verbose)
            
            env_dict['load_script'] = functools.partial(self._load_script, env_dict)

            if module_path not in _importer_path:
               sys.meta_path.append(_StringImporter(module_path,self.name))
               _importer_path.add(module_path)

            from bliss.scanning.scan import ScanSaving
            env_dict['SCAN_SAVING'] = ScanSaving()
            from bliss.session.measurementgroup import ACTIVE_MG
            env_dict['ACTIVE_MG'] = ACTIVE_MG

            for obj_name, obj in env_dict.iteritems():
                setattr(setup_globals, obj_name, obj)

            fullpath = self._config_tree.get('setup-file')
            if fullpath is None:
                raise RuntimeError("No setup file.")
            code = compile(setup_file.read(), fullpath, 'exec')
            exec(code, env_dict)
            
            for obj_name, obj in env_dict.iteritems():
                setattr(setup_globals, obj_name, obj)

            return True
      except IOError:
         raise ValueError("Session: setup-file %s can't be found" % 
                          self._config_tree.get('setup-file'))

   @staticmethod
   def _load_config(env_dict, names_list=None, exclude_list=None, verbose=True):
      try:
         cfg = static.get_config()
      except:
         sys.excepthook(*sys.exc_info())
         return        

      if names_list is None:
         names_list = cfg.names_list
         if exclude_list:
            for name in exclude_list:
               try:
                  names_list.remove(name)
               except (ValueError, AttributeError):
                  pass

      for item_name in names_list:
         if hasattr(setup_globals, item_name):
            env_dict[item_name] = getattr(setup_globals, item_name)
            continue

         if verbose:
            print "Initializing '%s`" % item_name
         try:
            o = cfg.get(item_name)
         except:
            sys.excepthook(*sys.exc_info())
         else:
            env_dict[item_name] = o
            setattr(setup_globals, item_name, o)
            del o

   @staticmethod
   def _load_script(env_dict, script_module_name) :
      module_name = '%s.%s.%s' % (_StringImporter.BASE_MODULE_NAME_SPACE,
                                  _StringImporter.SUB_NAME_SPACE,
                                  script_module_name)
  
      if module_name in sys.modules:
         reload_module = True
      else:
         reload_module = False
      try:
         script_module = __import__(module_name, env_dict, {}, ['*'])
      except Exception:
         sys.excepthook(*sys.exc_info())
      else:
         if reload_module:
            reload(script_module)
         for k, v in script_module.__dict__.iteritems():
            if k.startswith('_'): continue
            env_dict[k] = v

