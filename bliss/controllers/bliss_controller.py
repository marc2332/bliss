# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from importlib import import_module
from bliss.common.protocols import CounterContainer
from bliss.common.utils import autocomplete_property
from bliss.config.static import ConfigReference, ConfigNode, ConfigList


def find_sub_names_config(config, selection=None, level=0, parent_key=None):
    """ Recursively search in a config the sub-sections where the key 'name' is found. 

        Returns a dict of tuples (sub_config, parent_key) indexed by level (0 is the top level).
            - sub_config: the sub-config containing the 'name' key
            - parent_key: key under which the sub_config was found (None for level 0)

        args:
            config: the config that should be explored
            selection: a list containing the info of the subnames already found (for recursion)
            level: an integer describing at which level the subname was found (level=0 is the top/upper level) (for recursion)
            parent_key: key under which the sub_config was found (None for level 0) (for recursion)
    """

    assert isinstance(config, (ConfigNode, dict))

    if selection is None:
        selection = {}

    if selection.get(level) is None:
        selection[level] = []

    if isinstance(config, ConfigNode):
        name = config.raw_get("name")
    else:
        name = config.get("name")

    if name is not None:
        selection[level].append((config, parent_key))

    if isinstance(config, ConfigNode):
        cfg_items = (
            config.raw_items()
        )  # !!! raw_items to avoid cyclic import while resloving reference !!!
    else:
        cfg_items = config.items()

    for k, v in cfg_items:
        if isinstance(v, (ConfigNode, dict)):
            find_sub_names_config(v, selection, level + 1, k)

        elif isinstance(v, (ConfigList, list)):
            for i in v:
                if isinstance(i, (ConfigNode, dict)):
                    find_sub_names_config(i, selection, level + 1, k)

    return selection


def from_config_dict(ctrl_class, cfg_dict):
    """ Helper to instanciate a BlissController object from a configuration dictionary """
    if BlissController not in ctrl_class.mro():
        raise TypeError(f"{ctrl_class} is not a BlissController class")
    bctrl = ctrl_class(cfg_dict)
    bctrl._controller_init()
    return bctrl


class BlissController(CounterContainer):
    """
        BlissController base class is made for the implementation of all Bliss controllers.
        It is designed to ease the management of sub-objects that depend on a shared controller.

        Sub-objects are declared in the yml configuration of the controller under dedicated sub-sections.
        A sub-object is considered as a subitem if it has a name (key 'name' in a sub-section of the config).
        Usually subitems are counters and axes but could be anything else (known by the controller).

        The BlissController has properties @counters and @axes to retrieve subitems that can be identified
        as counters or axes.

        
        # --- Plugin ---

        BlissController objects are created from the yml config using the bliss_controller plugin.
        Any subitem with a name can be imported in a Bliss session with config.get('name').
        The plugin ensures that the controller and subitems are only created once.
        The bliss controller itself can have a name (optional) and can be imported in the session.

        The plugin resolves dependencies between the BlissController and its subitems.
        It looks for the top 'class' key in the config to instantiate the BlissController.
        While importing any subitem in the session, the bliss controller is instantiated first (if not alive already).

        The effective creation of the subitems is performed by the BlissController itself and the plugin just ensures
        that the controller is always created before subitems and only once.

        Example: config.get(bctrl_name) or config.get(item_name) with config = bliss.config.static.get_config()

        # --- Items and sub-controllers ---

        A controller (top) can have sub-controllers. In that case there are two ways to create the sub_controllers:
        
        - The most simple way to do this is to declare the sub-controller as an independant object with its own yml config
        and use a reference to this object into the top-controller config.

        - If a sub-controller has no reason to exist independently from the top-controller, then the top-controller
        will create and manage its sub-controllers from the knowledge of the top-controller config only. 
        In that case, some items declared in the top-controller are, in fact, managed by one of the sub-controllers. 
        In that case, the author of the top controller class must overload the '_get_item_owner' method and specify 
        which is the sub-controller that manages which items.
        Example: Consider a top controller which manages a motors controller internally. The top controller config 
        declares the axes subitems but those items are in fact managed by the motors controller.
        In that case, '_get_item_owner' should specify that the axes subitems are managed by 'self.motor_controller'
        instead of 'self'. The method receives the item name and the parent_key. So 'self.motor_controller' can be
        associated to all subitems under the 'axes' parent_key (instead of doing it for each subitem name).


        # --- From config dict ---

        A BlissController can be instantiated directly (i.e. not via plugin) providing a config as a dictionary. 
        In that case, users must call the method 'self._controller_init()' just after the controller instantiation
        to ensure that the controller is initialized in the same way as the plugin does.
        The config dictionary should be structured like a YML file (i.e: nested dict and list) and
        references replaced by their corresponding object instances.
        
        Example: bctrl = BlissController( config_dict ) => bctrl._controller_init()

        
        # --- yml config example ---

        - plugin: bliss_controller    <== use the dedicated bliss controller plugin
          module: custom_module       <== module of the custom bliss controller
          class: BCMockup             <== class of the custom bliss controller
          name: bcmock                <== name of the custom bliss controller  (optional)

          com:                        <== communication config for associated hardware (optional)
            tcp:
            url: bcmock

          custom_param_1: value       <== a parameter for the custom bliss controller creation (optional)
          custom_param_2: $ref1       <== a referenced object for the controller (optional/authorized)

          sub-section-1:              <== a sub-section where subitems can be declared (optional) (ex: 'counters')
            - name: sub_item_1        <== name of the subitem (and its config)
              tag : item_tag_1        <== a tag for this item (known and interpreted by the custom bliss controller) (optional)
              sub_param_1: value      <== a custom parameter for the item creation (optional)
              device: $ref2           <== an external reference for this subitem (optional/authorized)

          sub-section-2:              <== another sub-section where subitems can be declared (optional) (ex: 'axes')
            - name: sub_item_2        <== name of the subitem (and its config)
              tag : item_tag_2        <== a tag for this item (known and interpreted by the custom bliss controller) (optional)
              input: $sub_item_1      <== an internal reference to another subitem owned by the same controller (optional/authorized)

              sub-section-2-1:        <== nested sub-sections are possible (optional)
                - name: sub_item_21
                  tag : item_tag_21

          sub-section-3 :             <== a third sub-section
            - name: $ref3             <== a subitem as an external reference is possible (optional/authorized)
              something: value
    """

    def __init__(self, config):
        self.__subitems_configs_ready = False
        self.__ctrl_is_initialized = False
        self._subitems_config = {}  # stores items info (cfg, pkey) (filled by self._prepare_subitems_configs)
        self._subitems = {}  # stores items instances   (filled by self.__build_subitem_from_config)
        self._hw_controller = (
            None
        )  # acces the low level hardware controller interface (if any)

        # generate generic name if no controller name found in config
        self._name = config.get("name")
        if self._name is None:
            if isinstance(config, ConfigNode):
                self._name = f"{self.__class__.__name__}_{config.md5hash()}"
            else:
                self._name = f"{self.__class__.__name__}_{id(self)}"

        # config can be a ConfigNode or a dict
        self._config = config

    # ========== STANDARD METHODS ============================

    @autocomplete_property
    def hardware(self):
        if self._hw_controller is None:
            self._hw_controller = self._create_hardware()
        return self._hw_controller

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        return self._config

    # ========== INTERNAL METHODS (PRIVATE) ============================

    @property
    def _is_initialized(self):
        return self.__ctrl_is_initialized

    def __build_subitem_from_config(self, name):
        """ 
            Standard method to create an item from its config.
            This method is called by either:
             - the plugin, via a config.get(item_name) => create_object_from_cache => name is exported in session
             - the controller, via self._get_subitem(item_name) => name is NOT exported in session
        """

        # print(f"=== Build item {name} from {self.name}")

        if not self.__ctrl_is_initialized:
            raise RuntimeError(
                f"Controller not initialized: {self}\nCall 'ctrl._controller_init()'"
            )

        if name not in self._subitems_config:
            raise ValueError(f"Cannot find item with name: {name}")

        cfg, pkey = self._subitems_config[name]
        cfg_name = cfg.get("name")

        if isinstance(cfg_name, str):
            item_class = self.__find_item_class(cfg, pkey)
            item_obj = None
        else:  # its a referenced object (cfg_name contains the object instance)
            item_class = None
            item_obj = cfg_name
            cfg_name = item_obj.name

        item = self._create_subitem_from_config(
            cfg_name, cfg, pkey, item_class, item_obj
        )
        if item is None:
            msg = f"\nUnable to obtain item {cfg_name} from {self.name} with:\n"
            msg += f"  class: {item_class}\n"
            msg += f"  parent_key: '{pkey}'\n"
            msg += f"  config: {cfg}\n"
            msg += "Check item config is supported by this controller"
            raise RuntimeError(msg)

        self._subitems[name] = item

    def __find_item_class(self, cfg, pkey):
        """
            Return a suitable class for an item of a bliss controller. 

            It tries to find a class_name in the item's config or ask the controller for a default.
            The class_name could be an absolute path, else the class is searched in the controller 
            module first. If not found, ask the controller the path of the module where the class should be found.
            
            args:
                - cfg: item config node
                - pkey: item parent key

        """

        class_name = cfg.get("class")
        if class_name is None:  # ask default class name to the controller
            class_name = self._get_subitem_default_class_name(cfg, pkey)
            if class_name is None:
                msg = f"\nUnable to obtain default_class_name from {self.name} with:\n"
                msg += f"  parent_key: '{pkey}'\n"
                msg += f"  config: {cfg}\n"
                msg += "Check item config is supported by this controller\n"
                raise RuntimeError(msg)

        if "." in class_name:  # from absolute path
            idx = class_name.rfind(".")
            module_name, cname = class_name[:idx], class_name[idx + 1 :]
            module = __import__(module_name, fromlist=[""])
            return getattr(module, cname)
        else:
            module = import_module(
                self.__module__
            )  # try at the controller module level first
            if hasattr(module, class_name):
                return getattr(module, class_name)
            else:  # ask the controller the module where the class should be found
                module_name = self._get_subitem_default_module(class_name, cfg, pkey)
                if module_name is None:
                    msg = f"\nUnable to obtain default_module from {self.name} with:\n"
                    msg += f"  class_name: {class_name}\n"
                    msg += f"  parent_key: '{pkey}'\n"
                    msg += f"  config: {cfg}\n"
                    msg += "Check item config is supported by this controller\n"
                    raise RuntimeError(msg)
                module = import_module(module_name)
                if hasattr(module, class_name):
                    return getattr(module, class_name)
                else:
                    raise ModuleNotFoundError(
                        f"cannot find class {class_name} in {module}"
                    )

    def _get_item_owner(self, name, cfg, pkey):
        """ Return the controller that owns the items declared in the config.
            By default, this controller is the owner of all config items.
            However if this controller has sub-controllers that are the real owners 
            of some items, this method should use to specify which sub-controller is
            the owner of which item (identified with name and pkey). 
        """
        return self

    def _prepare_subitems_configs(self):
        """ Find all sub objects with a name in the controller config.
            Store the items config info (cfg, pkey) in the controller (including referenced items).
            Return the list of found items (excluding referenced items).
        """

        cacheditemnames2ctrl = {}
        sub_cfgs = find_sub_names_config(self._config)
        for level in sorted(sub_cfgs.keys()):
            if level != 0:  # ignore the controller itself
                for cfg, pkey in sub_cfgs[level]:
                    if isinstance(cfg, ConfigNode):
                        name = cfg.raw_get("name")
                    else:
                        name = cfg.get("name")

                    if isinstance(name, str):
                        # only store in items_list the subitems with a name as a string
                        # because items_list is used by the plugin to cache subitem's controller.
                        # (i.e exclude referenced names as they are not owned by this controller)
                        cacheditemnames2ctrl[name] = self._get_item_owner(
                            name, cfg, pkey
                        )
                    elif isinstance(name, ConfigReference):
                        name = name.object_name
                    else:
                        name = name.name

                    self._subitems_config[name] = (cfg, pkey)

        self.__subitems_configs_ready = True
        return cacheditemnames2ctrl

    def _get_subitem(self, name):
        """ return an item (create it if not alive) """
        if name not in self._subitems:
            self.__build_subitem_from_config(name)
        return self._subitems[name]

    def _controller_init(self):
        """ Initialize a controller the same way as the plugin does.
            This method must be called if the controller has been directly 
            instantiated with a config dictionary (i.e without going through the plugin and YML config). 
        """
        if not self.__ctrl_is_initialized:
            if not self.__subitems_configs_ready:
                self._prepare_subitems_configs()

            self.__ctrl_is_initialized = True
            try:
                self._load_config()
                self._init()
            except BaseException:
                self.__ctrl_is_initialized = False
                raise

    # ========== ABSTRACT METHODS ====================

    def _create_hardware(self):
        """ return the low level hardware controller interface """
        raise NotImplementedError

    def _get_default_chain_counter_controller(self):
        """ return the counter controller that shoud be used with the DefaultAcquisitionChain (i.e for standard step by step scans) """
        raise NotImplementedError

    def _get_subitem_default_class_name(self, cfg, parent_key):
        # Called when the class key cannot be found in the item_config.
        # Then a default class must be returned. The choice of the item_class is usually made from the parent_key value.
        # Elements of the item_config may also by used to make the choice of the item_class.

        """ 
            Return the appropriate default class for a given item.
            args: 
                - cfg: item config node
                - parent_key: the key under which item config was found
        """
        raise NotImplementedError

    def _get_subitem_default_module(self, class_name, cfg, parent_key):
        # Called when the given class_name (found in cfg) cannot be found at the controller module level.
        # Then a default module path must be returned. The choice of the item module is usually made from the parent_key value.
        # Elements of the item_config may also by used to make the choice of the item module.

        """ 
            Return the appropriate default class for a given item.
            args: 
                - class_name: item class name
                - cfg: item config node
                - parent_key: the key under which item config was found
        """

        raise NotImplementedError

    def _create_subitem_from_config(
        self, name, cfg, parent_key, item_class, item_obj=None
    ):
        # Called when a new subitem is created (i.e accessed for the first time via self._get_subitem)
        """ 
            Return the instance of a new item owned by this controller.

            args:
                name: item name
                cfg : item config
                parent_key: the config key under which the item was found (ex: 'counters').
                item_class: a class to instantiate the item (None if item is a reference)
                item_obj: the item instance (None if item is NOT a reference)

            return: item instance
                
        """

        # === Example ===
        # return item_class(cfg)

        raise NotImplementedError

    def _load_config(self):
        # Called by bliss_controller plugin (after self._subitems_config has_been filled).

        """
            Read and apply the YML configuration of the controller. 
        """
        raise NotImplementedError

    def _init(self):
        # Called by bliss_controller plugin (just after self._load_config)

        """
            Place holder for any action to perform after the configuration has been loaded.
        """
        pass

    @autocomplete_property
    def counters(self):
        raise NotImplementedError

    @autocomplete_property
    def axes(self):
        raise NotImplementedError
