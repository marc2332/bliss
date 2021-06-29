# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from importlib import import_module
from bliss.config.plugins.utils import find_top_class_and_node, find_class_and_node
from bliss.config.static import ConfigReference, ConfigNode, ConfigList
from bliss.common.utils import autocomplete_property


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


class ConfigItemContainer:

    """
        Base class designed to ease the management of sub-objects that declared under a top object configuration.

        Sub-objects are declared in the top object yml configuration under dedicated sub-sections.
        A sub-object is considered as a subitem if it has a name (key 'name' in a sub-section of the config).
        Usually subitems are counters and axes but could be anything else (known by the top object).

        # --- Plugin ---

        ConfigItemContainer objects are created from the yml config using the bliss plugin.
        Any subitem with a name can be imported in a Bliss session with config.get('name').
        The plugin ensures that the top object and its subitems are only created once.
        The ConfigItemContainer itself can have a name (optional) and can be imported in the session.

        The plugin resolves dependencies between the ConfigItemContainer and its subitems.
        It looks for the top 'class' key in the config to instantiate the ConfigItemContainer.
        While importing any subitem in the session, the ConfigItemContainer is instantiated first (if not alive already).

        The effective creation of the subitems is performed by the ConfigItemContainer itself and the plugin just ensures
        that the container is always created before subitems and only once.

        Example: config.get(top_name) or config.get(item_name) with config = bliss.config.static.get_config()

        # --- Items and sub-controllers ---

        An ConfigItemContainer can have sub-controllers. In that case there are two ways to create the sub-containers:
        
        - The most simple way to do this is to declare the sub-containers as an independant object with its own yml config
        and use a reference to this object into the top-object config.

        - If a sub-container has no reason to exist independently from the top-container, then the top-container
        will create and manage its sub-containers from the knowledge of the top-container config only. 
        In that case, some items declared in the top-container are, in fact, managed by one of the sub-containers. 
        In that case, the author of the top container class must overload the '_get_item_owner' method and specify 
        which is the sub-container that manages which items.
        Example: Consider a top container which manages a motors controller internally. The top container config 
        declares the axes subitems but those items are in fact managed by the motors controller.
        In that case, '_get_item_owner' should specify that the axes subitems are managed by 'self.motor_controller'
        instead of 'self'. The method receives the item name and the parent_key. So 'self.motor_controller' can be
        associated to all subitems under the 'axes' parent_key (instead of doing it for each subitem name).


        # --- From config dict ---

        A ConfigItemContainer can be instantiated directly (i.e. not via plugin) providing a config as a dictionary. 
        In that case, users must call the method 'self._initialize_config()' just after the controller instantiation
        to ensure that the controller is initialized in the same way as the plugin does.
        The config dictionary should be structured like a YML file (i.e: nested dict and list) and
        references replaced by their corresponding object instances.
        
        Example: bctrl = ConfigItemContainer( config_dict ) => bctrl._initialize_config()

        
        # --- yml config example ---

        - plugin: bliss               <== use the dedicated bliss plugin
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
        self.__initialization_done = False
        self._subitems_config = {}  # stores items info (cfg, pkey) (filled by self._prepare_subitems_configs)
        self._subitems = {}  # stores items instances   (filled by self.__build_subitem_from_config)

        # generate generic name for the container if not found in config
        self._name = config.get("name")
        if self._name is None:
            if isinstance(config, ConfigNode):
                self._name = f"{self.__class__.__name__}_{config.md5hash()}"
            else:
                self._name = f"{self.__class__.__name__}_{id(self)}"

        # config can be a ConfigNode or a dict
        self._config = config

    # ========== STANDARD METHODS ============================

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        return self._config

    # ========== INTERNAL METHODS (PRIVATE) ============================

    @property
    def _is_initialized(self):
        return self.__initialization_done

    def __build_subitem_from_config(self, name):
        """ 
            Standard method to create an item from its config.
            This method is called:
             - by the plugin, via config.get(item_name) => create_object_from_cache => name is exported in session
             - directly, via self._get_subitem(item_name) => name is NOT exported in session
        """

        # print(f"=== Build item {name} from {self.name}")

        if not self.__initialization_done:
            raise RuntimeError(
                f"Item container not initialized: {self}\nCall 'self._initialize_config()'"
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
            msg += f"Check that item config is supported by {self}"
            raise RuntimeError(msg)

        self._subitems[name] = item

    def __find_item_class(self, cfg, pkey):
        """
            Return a suitable class for an item. 

            It tries to find a class_name in the item's config or ask the container for a default.
            The class_name could be an absolute path, else the class is searched in the container 
            module first. If not found, ask the container the path of the module where the class should be found.
            
            args:
                - cfg: item config node
                - pkey: item parent key

        """

        class_name = cfg.get("class")
        if class_name is None:  # ask default class name to the container
            class_name = self._get_subitem_default_class_name(cfg, pkey)
            if class_name is None:
                msg = f"\nUnable to obtain default_class_name from {self.name} with:\n"
                msg += f"  parent_key: '{pkey}'\n"
                msg += f"  config: {cfg}\n"
                msg += f"Check item config is supported by {self}\n"
                raise RuntimeError(msg)

        if "." in class_name:  # from absolute path
            idx = class_name.rfind(".")
            module_name, cname = class_name[:idx], class_name[idx + 1 :]
            module = __import__(module_name, fromlist=[""])
            return getattr(module, cname)
        else:
            module = import_module(
                self.__module__
            )  # try at the container module level first
            if hasattr(module, class_name):
                return getattr(module, class_name)
            else:  # ask the container the module where the class should be found
                module_name = self._get_subitem_default_module(class_name, cfg, pkey)
                if module_name is None:
                    msg = f"\nUnable to obtain default_module from {self.name} with:\n"
                    msg += f"  class_name: {class_name}\n"
                    msg += f"  parent_key: '{pkey}'\n"
                    msg += f"  config: {cfg}\n"
                    msg += f"Check item config is supported by {self}\n"
                    raise RuntimeError(msg)
                module = import_module(module_name)
                if hasattr(module, class_name):
                    return getattr(module, class_name)
                else:
                    raise ModuleNotFoundError(
                        f"cannot find class {class_name} in {module}"
                    )

    def _get_item_owner(self, name, cfg, pkey):
        """ Return the container that owns the items declared in the config.
            By default, this container is the owner of all items.
            However if this container has sub-containers, use this method to specify
            the items owners.
        """

        # === Example with one sub-container (self.foo_container)  ===
        # === owning all items found under the 'foo' section of the config ===
        #
        # if pkey == 'foo':
        #     return self.foo_container
        # else:
        #     return self

        return self

    def _prepare_subitems_configs(self):
        """ Find all sub objects with a name in the container config (i.e. items).
            Store the items config info (cfg, pkey) in the container (including referenced items).
            Return the list of found items (excluding referenced items).
        """

        cacheditemnames2ctrl = {}
        sub_cfgs = find_sub_names_config(self._config)
        for level in sorted(sub_cfgs.keys()):
            if level != 0:  # ignore the container itself
                for cfg, pkey in sub_cfgs[level]:
                    if isinstance(cfg, ConfigNode):
                        name = cfg.raw_get("name")
                    else:
                        name = cfg.get("name")

                    if isinstance(name, str):
                        # only store in items_list the subitems with a name as a string
                        # because items_list is used by the plugin to cache subitem's container.
                        # (i.e exclude referenced names as they are not owned by this container)
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

    def _initialize_config(self):
        """ Standard method to fully initialize this container object.
            This method must be called if the container has been directly 
            instantiated with a config dictionary (i.e without going through the plugin and YML config). 
        """
        if not self.__initialization_done:
            if not self.__subitems_configs_ready:
                self._prepare_subitems_configs()

            self.__initialization_done = True
            try:
                self._load_config()
                self._init()
            except BaseException:
                self.__initialization_done = False
                raise

    # ========== ABSTRACT METHODS ====================

    def _get_subitem_default_class_name(self, cfg, parent_key):
        # Called when the class key cannot be found in the item_config.
        # Then a default class must be returned. The choice of the item_class is usually made from the parent_key value.
        # Elements of the item_config may also by used to make the choice of the item_class.

        """ 
            Return the appropriate default class name (as a string) for a given item.
            args: 
                - cfg: item config node
                - parent_key: the key under which item config was found
        """
        raise NotImplementedError

    def _get_subitem_default_module(self, class_name, cfg, parent_key):
        # Called when the given class_name (found in cfg) cannot be found at the container module level.
        # Then a default module path must be returned. The choice of the item module is usually made from the parent_key value.
        # Elements of the item_config may also by used to make the choice of the item module.

        """ 
            Return the path (str) of the default module where the given class_name should be found.
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
            Return the instance of a new item owned by this container.

            args:
                name: item name
                cfg : item config
                parent_key: the config key under which the item was found (ex: 'counters').
                item_class: a class to instantiate the item (None if item is a reference)
                item_obj: the item instance (None if item is NOT a reference)

            return: item instance
                
        """

        # === Example ===
        #
        # if item_obj is not None:
        #     return item_obj
        #
        # if pkey == 'foo':
        #     return item_class(name, cfg)
        # else:
        #     return item_class(cfg)

        raise NotImplementedError

    def _load_config(self):
        # Called by the plugin via self._initialize_config
        # Called after self._subitems_config has_been filled.

        """
            Read and apply the YML configuration of this container. 
        """
        raise NotImplementedError

    def _init(self):
        # Called by the plugin via self._initialize_config
        # Called just after self._load_config

        """
            Place holder for any action to perform after the configuration has been loaded.
        """
        pass


def create_objects_from_config_node(cfg_obj, cfg_node):

    """
        Create an object from the config with a given name (unique). 
        It ensures that a ConfigItemContainer and its sub-objects are only created once.
        
        This function resolves dependencies between a ConfigItemContainer and its sub-objects with a name (items).
        It looks for the 'class' key in 'cfg_node' (or at upper levels) to instantiate the ConfigItemContainer.
        All items configs found under a container are registered as cached items for a later instantiation (see 'create_object_from_cache').

        args:
            cfg_obj: a Config object (from config.static)
            cfg_node: a ConfigNode object (from config.static)

        yield: 
            tuple: (created_items, cached_items)
    """

    # search the 'class' key in cfg_node or at a upper node level
    # then return the class and the associated config node
    klass, ctrl_node = find_top_class_and_node(cfg_node)
    ctrl_name = ctrl_node.get("name")  # container could have a name in config
    item_name = cfg_node["name"]  # name of the item that should be created and returned

    if issubclass(klass, ConfigItemContainer):

        # always create the container first
        bctrl = klass(ctrl_node)
        # print(f"\n=== From config: {item_name} from {bctrl.name}")

        # prepare subitems configs and cache item's container.
        # the container decides which item should be cached and which container
        # is associated to the cached item (in case the cached item is owned by a sub-container of this container)
        cacheditemnames2ctrl = bctrl._prepare_subitems_configs()
        # print(f"\n=== Caching: {list(cacheditemnames2ctrl.keys())} from {bctrl.name}")

        # --- add the container to registered items (if it has a name)
        name2items = {}
        if ctrl_name:
            name2items[ctrl_name] = bctrl

        # update the config cache dict now to avoid cyclic instantiation with internal references
        # an internal reference occurs when a subitem config uses a reference to another subitem owned by the same container.
        yield name2items, cacheditemnames2ctrl

        # load config and initialize
        try:
            bctrl._initialize_config()
        except BaseException:
            # remove cached obj if container initialization fails (to avoid items with different instances of the same container)
            for iname in cacheditemnames2ctrl.keys():
                cfg_obj._name2cache.pop(iname, None)
            raise

        # --- don't forget to instantiate the object for which this function has been called (if not a container)
        if item_name != ctrl_name:
            obj = cfg_obj.get(item_name)
            yield {item_name: obj}

        # --- Now any new object_name going through 'config.get( obj_name )' should call 'create_object_from_cache' only.
        # --- 'create_objects_from_config_node' should never be called again for any object related to the container instantiated here (see config.get code)

    elif (
        item_name != ctrl_name
    ):  # prevent instantiation of an item comming from a top object that is not a ConfigItemContainer
        raise TypeError(
            f"Object with subitems in config must be a ConfigItemContainer object"
        )

    # elif cfg_node.plugin == "bliss":  # act as the older Bliss plugin

    #     klass, node = find_class_and_node(cfg_node)

    #     if node.get("name") != item_name:
    #         cfg_node = ConfigNode.indexed_nodes[item_name]
    #     else:
    #         cfg_node = node

    #     o = klass(item_name, cfg_node.clone())

    #     for key, value in cfg_node.items():
    #         if isinstance(cfg_node.raw_get(key), ConfigReference):
    #             if hasattr(o, key):
    #                 continue
    #             else:
    #                 setattr(o, key, value)

    #     yield {item_name: o}
    #     return

    # else:
    #     bctrl = klass(ctrl_node)
    #     yield {ctrl_name: bctrl}
    #     return

    else:
        bctrl = klass(ctrl_node)
        # print(f"\n=== From config: {item_name} from {bctrl.name}")
        if (
            item_name == ctrl_name
        ):  # allow instantiation of top object which is not a ConfigItemContainer
            yield {ctrl_name: bctrl}
            return
        else:  # prevent instantiation of an item comming from a top object that is not a ConfigItemContainer
            raise TypeError(
                "Object with subitems in config must be a ConfigItemContainer object"
            )


def create_object_from_cache(config, name, bctrl):
    # print(f"\n=== From cache: {name} from {bctrl.name}")

    try:
        return bctrl._get_subitem(name)
    except BaseException:
        # put back item in cached items if instantiation has failed
        config._name2cache[name] = bctrl
        raise
