# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Package containing Flint, a GUI application based on Qt to mostly display
scan processing.

.. autosummary::
    :toctree:

    flint
    config
    flint_api
    flint_window
    model
        model.flint_model
        model.scan_model
        model.plot_model
        model.plot_item_model
    manager
        manager.manager
        manager.data_storage
        manager.scan_manager
        manager.workspace_manager
    helper
        helper.model_helper
        helper.plot_interaction
        helper.rpc_server
        helper.scan_info_helper
        helper.style_helper
    resources
    simulator
        simulator.acquisition
        simulator.simulator_widget
    utils
        utils.mathutils
        utils.qmodelutils
        utils.qsettingsutils
        utils.signalutils
        utils.stringutils
        utils.svgutils
    widgets
        widgets.scan_status
        widgets.curve_plot
        widgets.curve_plot_property
        widgets.image_plot
        widgets.image_plot_property
        widgets.scatter_plot
        widgets.scatter_plot_property
        widgets.mca_plot
        widgets.mca_plot_property
        widgets.about
        widgets.log_widget
"""
