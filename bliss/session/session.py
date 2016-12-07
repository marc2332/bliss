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
from bliss.config.conductor.client import get_config_file,get_python_modules

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
      self._base_path = os.path.dirname(config_tree.filename)
      self._setup_file_path = config_tree.get('setup-file')
      self._synoptic_file = config_tree.get('svg-file')
      self._config_objects_names = config_tree.get("config-objects")

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

   def setup(self,env_dict = None,verbose = False):
      if self._setup_file_path is not None:
         if self._setup_file_path.startswith('.'): # relative from current node
            filename = os.path.basename(self._setup_file_path)
            fullpath = os.path.join(self._base_path,filename)
         else:
            fullpath = setup_file_path

         try:
            setup_python = get_config_file(fullpath)
         except RuntimeError:
            raise ValueError("Session: setup-file %s can't be found" % fullpath)
         else:
            module_path = os.path.join(self._base_path,'scripts')
            
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

            self._load_config(env_dict, config_objects, verbose)
            
            env_dict['load_script'] = functools.partial(self._load_script, env_dict)

            if module_path not in _importer_path:
               sys.meta_path.append(_StringImporter(module_path,self.name))
               _importer_path.add(module_path)

            try:
               exec(setup_python,env_dict)
            finally:
               for obj_name, obj in env_dict.iteritems():
                  setattr(setup_globals, obj_name, obj) 
            if verbose:
               print "Done."
            return True
      raise RuntimeError("No setup file.")

   @staticmethod
   def _load_config(env_dict, names_list=None, verbose=True):
      try:
         cfg = static.get_config()
      except:
         sys.excepthook(*sys.exc_info())
         return        

      if names_list is None:
         names_list = cfg.names_list
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

