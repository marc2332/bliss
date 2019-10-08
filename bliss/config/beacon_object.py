# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import yaml
from functools import wraps
from bliss.config.settings import HashObjSetting, pipeline
from bliss.config.channels import Cache, EventChannel
from bliss.common import event
from bliss.common.utils import Null, autocomplete_property
from bliss.config.conductor.client import remote_open


def _find_dict(name, d):
    if d.get("name") == name:
        return d
    for key, value in d.items():
        if isinstance(value, dict):
            sub_dict = _find_dict(name, value)
        elif isinstance(value, list):
            sub_dict = _find_list(name, value)
        else:
            continue

        if sub_dict is not None:
            return sub_dict


def _find_list(name, l):
    for value in l:
        if isinstance(value, dict):
            sub_dict = _find_dict(name, value)
        elif isinstance(value, list):
            sub_dict = _find_list(name, value)
        else:
            continue
        if sub_dict is not None:
            return sub_dict


class BeaconObject:
    class _config_getter(property):
        pass

    class _property(property):
        def __init__(
            self,
            fget=None,
            fset=None,
            fdel=None,
            doc=None,
            must_be_in_config=False,
            only_in_config=False,
            default=Null,
            priority=0,
        ):
            try:
                fget.__redefined__
            except AttributeError:
                if only_in_config:

                    def get(self):
                        self._initialize_with_setting()
                        return fget(self)

                else:

                    def get(self):
                        self._initialize_with_setting()
                        object_name = self.config["name"]
                        if self._disabled_settings.get(fget.__name__):
                            return fget(self)

                        value = self._settings.get(fget.__name__)
                        return value if value is not None else fget(self)

                get.__redefined__ = True
                get.__default__ = default
                get.__must_be_in_config__ = must_be_in_config or only_in_config
                get.__only_in_config__ = only_in_config
                get.__priority__ = priority
            else:
                must_be_in_config = fget.__must_be_in_config__
                only_in_config = fget.__only_in_config__
                default = fget.__default__
                priority = fget.__priority__
                get = fget

            if fset is not None:
                if only_in_config:

                    def set(self, value):
                        if not self._in_initialize_with_setting:
                            raise RuntimeError(
                                f"parameter {fset.__name__} is read only."
                            )
                        rvalue = fset(self, value)
                        set_value = rvalue if rvalue is not None else value
                        self._event_channel.post(fset.__name__)

                else:
                    fence = {"in_set": False}

                    def set(self, value):
                        if fence.get("in_set"):
                            return
                        try:
                            fence["in_set"] = True
                            rvalue = fset(self, value)
                            set_value = rvalue if rvalue is not None else value
                            self._settings[fset.__name__] = set_value
                            self._event_channel.post(fset.__name__)
                            self._initialize_with_setting()
                        finally:
                            fence["in_set"] = False

            else:
                set = None
            super().__init__(get, set, fdel, doc)
            self.default = default
            self.must_be_in_config = must_be_in_config
            self.only_in_config = only_in_config
            self.priority = priority

    def __init__(self, config, share_hardware=True):
        """
        config -- a configuration node
        share_hardware -- mean that several instances of bliss share the same hardware
        and need to initialize it with the configuration if no other peer has done it.
        if share_hardware is False initialization of parameters will be done ones per peer.
        """
        self._config = config
        try:
            name = config["name"]
        except KeyError:
            # try to use name property instead
            try:
                name = self.name
            except AttributeError:
                raise RuntimeError("config object must have a name.")
        else:
            if not hasattr(self, "name"):
                self.name = name

        if share_hardware:
            self.__initialized = Cache(self, "initialized", default_value=False)
        else:

            class Local:
                def __init__(self):
                    self.__value = False

                @property
                def value(self):
                    return self.__value

                @value.setter
                def value(self, value):
                    self.__value = value

            self.__initialized = Local()
        self._in_initialize_with_setting = False
        self._event_channel = EventChannel(f"__EVENT__:{self.name}")
        self._event_channel.register_callback(self.__event_handler)

    @autocomplete_property
    def config(self):
        return self._config

    @autocomplete_property
    def settings(self):
        self._initialize_with_setting()
        return self._settings

    def __update_settings(self):
        config = self.config
        settings_property = self.__settings_properties()
        default_values = {
            name: prop.default
            for name, prop in settings_property.items()
            if prop.default != Null
        }
        must_be_in_config = set(
            [name for name, prop in settings_property.items() if prop.must_be_in_config]
        )
        must_be_in_config.update(self.__config_getter().keys())

        if not must_be_in_config <= config.keys():
            missing_keys = must_be_in_config - config.keys()
            raise RuntimeError(
                f"For device {self.name} configuration must contains {missing_keys}."
            )
        config_values = {
            name: config.get(name)
            for name in settings_property.keys()
            if config.get(name, Null) != Null
        }
        default_values.update(config_values)
        self._settings = HashObjSetting(
            f"{self.name}:settings", default_values=default_values
        )
        self._disabled_settings = HashObjSetting(f"{self.name}:disabled_settings")

    def apply_config(self, reload=False):
        name = self.config["name"]
        if reload:
            with remote_open(self.config.filename) as f:
                d = yaml.safe_load(f.read())
            if isinstance(d, dict):
                d = _find_dict(name, d)
            elif isinstance(d, list):
                d = _find_list(name, d)
            else:
                d = None

            if d is None:
                raise RuntimeError(
                    f"Can't find config node named:{name} "
                    f"in file:{self.config.filename}"
                )
            self.config.update(d)
        try:
            self._settings.remove(*self.__settings_properties().keys())
        except AttributeError:  # apply config before init
            pass
        self.__initialized.value = False
        self._initialize_with_setting()

    def disable_setting(self, name):
        """
        If a setting is disable, hardware if always read
        and it's not set at init
        """
        self._disabled_settings[name] = True

    def enable_setting(self, name):
        with pipeline(self._settings, self._disabled_settings):
            del self._disabled_settings[name]
            del self._settings[name]

    def initialize(self):
        """
        Do the initialization of the object.

        For now it is just calling _initialize_with_setting
        """
        self._initialize_with_setting()

    def _initialize_with_setting(self):
        if self._in_initialize_with_setting:
            return
        try:
            self._in_initialize_with_setting = True
            if not self.__initialized.value:
                self.__update_settings()
                values = self._settings.get_all()
                error_messages = []
                for name, prop in self.__settings_properties().items():
                    if prop.fset is None:
                        error_messages.append(
                            f"object {self.name} doesn't have property setter for {name}"
                        )
                        continue
                    if self._disabled_settings.get(name):
                        continue
                    val = values.get(name, Null)
                    if val != Null:
                        try:
                            setattr(self, name, val)
                        except AttributeError:
                            raise AttributeError(
                                f"can't set attribute {name} for device {self.name}"
                            )
                    else:  # initialize setting
                        self._settings[name] = getattr(self, name)
                        self._event_channel.post(name)

                if error_messages:
                    raise NotImplementedError("\n".join(error_messages))
                self.__initialized.value = True
        finally:
            self._in_initialize_with_setting = False

    @property
    def _is_initialized(self):
        return self.__initialized.value

    def __filter_attribute(self, filter):
        # Follow the order of declaration in the class
        # Don't use dir() which alphabetize
        prop_dict = dict()
        for klass in reversed(self.__class__.mro()):
            for name, prop in klass.__dict__.items():
                if isinstance(prop, filter):
                    prop_dict[name] = prop
                else:
                    prop_dict.pop(name, None)
        return prop_dict

    def __settings_properties(self):
        setting_properties = self.__filter_attribute(BeaconObject._property)
        return {
            key: value
            for key, value in sorted(
                setting_properties.items(), key=lambda x: x[1].priority
            )
        }

    def __config_getter(self):
        return self.__filter_attribute(BeaconObject._config_getter)

    def __event_handler(self, events):
        events = [ev for ev in set(events) if event.get_receivers(self, ev)]
        if not events:
            return  # noting to do

        settings_values = self.settings.get_all()
        for ev in events:
            value = settings_values.get(ev)
            try:
                event.send(self, ev, value)
            except Exception:
                sys.excepthook(*sys.exc_info())

    @staticmethod
    def property(
        fget=None,
        fset=None,
        fdel=None,
        doc=None,
        must_be_in_config=False,
        only_in_config=False,
        default=Null,
        priority=0,
    ):
        if fget is None:

            def f(fget):
                return BeaconObject._property(
                    fget,
                    must_be_in_config=must_be_in_config,
                    only_in_config=only_in_config,
                    default=default,
                    priority=priority,
                )

            return f
        return BeaconObject._property(
            fget, fset, fdel, doc, must_be_in_config, only_in_config, default, priority
        )

    @staticmethod
    def config_getter(parameter_name):
        def get(self):
            return self.config[parameter_name]

        property = BeaconObject._config_getter(get)
        property.parameter_name = parameter_name
        return property

    @staticmethod
    def property_setting(name, default=None):
        def get(self):
            return self.settings.get(name, default)

        def set(self, value):
            self.settings[name] = value

        return BeaconObject._property(get, set)

    @staticmethod
    def lazy_init(func):
        @wraps(func)
        def f(self, *args, **kwargs):
            self._initialize_with_setting()
            return func(self, *args, **kwargs)

        return f
