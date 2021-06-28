# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.protocols import CounterContainer
from bliss.common.utils import autocomplete_property
from bliss.config.plugins.bliss_controller import ConfigItemContainer


class BlissController(CounterContainer, ConfigItemContainer):
    """
        BlissController base class is made for the implementation of all Bliss controllers.
        It is designed to ease the management of sub-objects that depend on a shared controller (see ConfigItemContainer).

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
        In that case, users must call the method 'self._initialize_config()' just after the controller instantiation
        to ensure that the controller is initialized in the same way as the plugin does.
        The config dictionary should be structured like a YML file (i.e: nested dict and list) and
        references replaced by their corresponding object instances.
        
        Example: bctrl = BlissController( config_dict ) => bctrl._initialize_config()

        
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

    # ========== STANDARD PROPERTIES ============================

    @autocomplete_property
    def hardware(self):
        if self._hw_controller is None:
            self._hw_controller = self._create_hardware()
        return self._hw_controller

    # ========== ABSTRACT METHODS ====================

    def _create_hardware(self):
        """ return the low level hardware controller interface """
        raise NotImplementedError

    @autocomplete_property
    def counters(self):
        raise NotImplementedError

    @autocomplete_property
    def axes(self):
        raise NotImplementedError
