# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import typing
from bliss.common import deprecation
from bliss import current_session
from bliss.config.settings import ParametersWardrobe
from bliss.config.conductor.client import get_caching_redis_proxy


class ScanDisplay(ParametersWardrobe):
    SLOTS = []

    def __init__(self, session_name=None):
        """
        This class represents the display parameters for scans for a session.
        """
        if session_name is None:
            session_name = current_session.name

        super().__init__(
            "%s:scan_display_params" % session_name,
            default_values={
                "auto": False,
                "motor_position": True,
                "_extra_args": [],
                "_scan_metadata": {},
                "displayed_channels": [],
                "scan_display_filter_enabled": True,
            },
            property_attributes=("session", "extra_args", "flint_output_enabled"),
            not_removable=(
                "auto",
                "motor_position",
                "displayed_channels",
                "_scan_metadata",
                "scan_display_filter_enabled",
            ),
            connection=get_caching_redis_proxy(),
        )

        self.add("_session_name", session_name)

        # Compatibility with deprecated property
        # his could be removed for BLISS 1.6
        stored = self.to_dict()
        if "enable_scan_display_filter" in stored:
            try:
                value = stored["enable_scan_display_filter"]
                self.remove(".enable_scan_display_filter")
            except NameError:
                self.scan_display_filter_enabled = value

    def __dir__(self):
        keys = super().__dir__()
        return keys

    def __repr__(self):
        return super().__repr__()

    def clone(self):
        new_scan_display = self.__class__(session_name=self._session_name)
        for s in self.SLOTS:
            setattr(new_scan_display, s, getattr(self, s))
        return new_scan_display

    @property
    def session(self):
        """ This give the name of the current session or default if no current session is defined """
        return self._session_name

    @property
    def extra_args(self):
        """Returns the list of extra arguments which will be provided to flint
        at it's next creation"""
        return self._extra_args

    @extra_args.setter
    def extra_args(self, extra_args):
        """Set the list of extra arguments to provide to flint at it's
        creation"""
        # FIXME: It could warn to restart flint in case it is already loaded
        if not isinstance(extra_args, (list, tuple)):
            raise TypeError(
                "SCAN_DISPLAY.extra_args expects a list or a tuple of strings"
            )

        # Do not load it while it is not needed
        from argparse import ArgumentParser
        from bliss.flint import config

        # Parse and check flint command line arguments
        parser = ArgumentParser(prog="Flint")
        config.configure_parser_arguments(parser)
        try:
            parser.parse_args(extra_args)
        except SystemExit:
            # Avoid to exit while parsing the arguments
            pass

        self._extra_args = list(extra_args)

    @property
    def enable_scan_display_filter(self):
        """Compatibility with deprecated code"""
        deprecation.deprecated_warning(
            "Property",
            "enable_scan_display_filter",
            replacement="scan_display_filter_enabled",
            since_version="1.5",
            skip_backtrace_count=1,
        )
        return self.scan_display_filter_enabled

    @enable_scan_display_filter.setter
    def enable_scan_display_filter(self, enabled):
        """Compatibility with deprecated code"""
        enabled = bool(enabled)
        deprecation.deprecated_warning(
            "Property",
            "enable_scan_display_filter",
            replacement="scan_display_filter_enabled",
            since_version="1.5",
            skip_backtrace_count=1,
        )
        self.scan_display_filter_enabled = enabled

    @property
    def flint_output_enabled(self):
        """
        Returns true if the output (strout/stderr) is displayed using the
        logging system.

        This is an helper to display the `disabled` state of the logger
        `flint.output`.
        """
        from bliss.common import plot

        logger = plot.FLINT_OUTPUT_LOGGER
        return not logger.disabled

    @flint_output_enabled.setter
    def flint_output_enabled(self, enabled):
        """
        Enable or disable the display of flint output ((strout/stderr) )
        using the logging system.

        This is an helper to set the `disabled` state of the logger
        `flint.output`.
        """
        from bliss.common import plot

        enabled = bool(enabled)
        logger = plot.FLINT_OUTPUT_LOGGER
        logger.disabled = not enabled

    @property
    def next_scan_displayed_channels(self) -> typing.Optional[typing.List[str]]:
        """Returns a list of forced channels to display with the next scan.

        If None, nothing was requested.
        """
        return self._scan_metadata.get("displayed_channels", None)

    @next_scan_displayed_channels.setter
    def next_scan_displayed_channels(self, values: typing.Optional[typing.List[str]]):
        """Specify a list of specific channels to display with the next scan.
        """
        meta = self._scan_metadata
        if meta is None:
            meta = {}
        else:
            meta = meta.copy()
        if values is None:
            if "displayed_channels" in meta:
                del meta["displayed_channels"]
        else:
            meta["displayed_channels"] = values
        self._scan_metadata = meta

    def _pop_next_scan_displayed_channels(self) -> typing.Optional[typing.List[str]]:
        """Return the specific channels to display with the next scan, and
        discard it.
        """
        meta = self._scan_metadata.copy()
        result = meta.pop("displayed_channels", None)
        self._scan_metadata = meta
        return result
