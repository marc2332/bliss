# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import functools

from gevent import lock

from bliss.config.conductor.client import Lock
from bliss.config.channels import Cache


class Switch(object):
    """
    Generic interface for switch object.
    """

    def lazy_init(func):
        @functools.wraps(func)
        def func_wrapper(self, *args, **kwargs):
            self.init()
            with Lock(self):
                return func(self, *args, **kwargs)

        return func_wrapper

    def __init__(self, name, config):
        self.__name = name
        self.__config = config
        self.__initialized_hw = Cache(self, "initialized", default_value=False)
        self.__state = Cache(self, "state")
        self._init_flag = False
        self.__lock = lock.Semaphore()

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    def init(self):
        """
        initialize the switch object
        """
        if not self._init_flag:
            self._init_flag = True
            try:
                self._init()
                with Lock(self):
                    with self.__lock:
                        if not self.__initialized_hw.value:
                            self._initialize_hardware()
                            self.__initialized_hw.value = True
            except:
                self._init_flag = False
                raise

    def _init(self):
        """
        This method should contains all software initialization
        """
        pass

    def _initialize_hardware(self):
        """
        This method should contains all commands needed to
        initialize the hardware.
        It will be called only once (by the first client).
        """
        pass

    @lazy_init
    def set(self, state):
        state_upper = state.upper()
        if self.__state.value != state_upper:
            try:
                self._set(state_upper)
            except:
                self.__state.value = None
                raise
            else:
                self.__state.value = state_upper

    def _set(self, state):
        raise NotImplementedError

    @lazy_init
    def get(self):
        state = self._get().upper()
        self.__state.value = state
        return state

    def _get(self):
        raise NotImplementedError

    @lazy_init
    def states_list(self):
        return [x.upper() for x in self._states_list()]

    def _states_list(self):
        raise NotImplementedError
