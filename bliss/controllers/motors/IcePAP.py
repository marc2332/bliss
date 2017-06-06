# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import os
import string
#TODO: MG18Nov14: needed by change in limit_search, to be removed
import time

"""
Bliss generic library
"""
from bliss.controllers.motor import Controller; from bliss.common import log
from bliss.common.utils import object_method
from bliss.common.axis import AxisState

"""
Extra modules
"""
from bliss.comm import libicepap

"""
Global resources
"""
_ICEPAP_TAB = "IcePAP: "


class IcePAP(Controller):

    """Implement IcePAP stepper motor controller access"""
    default_group    = None
    default_groupenc = None

    def __init__(self, name, config, axes, encoders):
        """Contructor"""
        Controller.__init__(self, name, config, axes, encoders)

        self.libdevice = None

    def initialize(self):
        """Controller initialization"""
        self.log_info("initialize() called")

        # Get controller config from bliss config
        # Mandatory parameters (port number is not needed)
        self.host = self.config.get("host")

        # Optional parameters
        try:
            self.libdebug = int(self.config.get("libdebug"))
        except:
            self.libdebug = 1

        # Create an IcePAP lib object to access the MASTER
        self.libdevice = libicepap.System(
            self.host,
            "verb=%d" %
            self.libdebug)

        # Create an IcePAP lib object as default group
        if IcePAP.default_group is None:
            IcePAP.default_group = libicepap.Group("default")
        self.libgroup = IcePAP.default_group

        # Create an IcePAP lib object as default group for encoders
        if IcePAP.default_groupenc is None:
            IcePAP.default_groupenc = libicepap.Group("default_enc")
        self.libgroupenc = IcePAP.default_groupenc

        # Create custom EMotion states to map IcePAP status bits
        self.icestate = AxisState()
        self.icestate.create_state("POWEROFF", "motor power is off")
        for code in libicepap.STATUS_DISCODE_STR:
            self.icestate.create_state(
                libicepap.STATUS_DISCODE_STR[code],
                libicepap.STATUS_DISCODE_DSC[code])
        for code in libicepap.STATUS_MODCODE_STR:
            self.icestate.create_state(
                libicepap.STATUS_MODCODE_STR[code],
                libicepap.STATUS_MODCODE_DSC[code])
        for code in libicepap.STATUS_STOPCODE_STR:
            self.icestate.create_state(
                libicepap.STATUS_STOPCODE_STR[code],
                libicepap.STATUS_STOPCODE_DSC[code])

    def finalize(self):
        """Controller no more needed"""
        self.log_info("finalize() called")

        # Remove any group in the IcePAP lib
        try:
            self.libgroup.delete()
            self.libgroupenc.delete()
        except:
            pass

        # Close IcePAP lib socket/threads
        if self.libdevice is not None:
            self.libdevice.close()
        

    def initialize_axis(self, axis):
        """Axis initialization"""
        self.log_info("initialize_axis() called for axis %r" % axis.name)

        # Get axis config from bliss config
        # address form is XY : X=rack {0..?} Y=driver {1..8}
        axis.address = axis.config.get("address", int)

        # Create an IcePAP lib axis object
        device = self.libdevice
        address = axis.address
        name = axis.name
        axis.libaxis = libicepap.Axis(device, address, name)

        # Add the axis to the default IcePAP lib group
        self.libgroup.add_axis(axis.libaxis)

    def initialize_hardware_axis(self,axis):
        # Initialiaze hardware
        # if set_power fails, display exception but let axis
        # be created properly
        try:
            self.libgroup.set_power(libicepap.ON, axis.libaxis)
        except:
            sys.excepthook(*sys.exc_info())


    def set_on(self, axis):
        """Switch power on"""
        self.libgroup.set_power(libicepap.ON, axis.libaxis)

    def set_off(self, axis):
        """Switch power off"""
        self.libgroup.set_power(libicepap.OFF, axis.libaxis)

    def read_position(self, axis):
        """Returns axis position in motor units"""
        self.log_info("read_position() called for axis %r" % axis.name)
        return self.libgroup.pos(axis.libaxis)


    def set_position(self, axis, new_pos):
        """Set axis position to a new value given in motor units"""
        l = libicepap.PosList()
        l[axis.libaxis] = new_pos
        self.libgroup.pos(l)
        return self.read_position(axis)


    def read_velocity(self, axis):
        """Returns axis current velocity in user units/sec"""
        #TODO: wouldn't be better in steps/s ?
        velocity = self.libgroup.velocity(axis.libaxis)
        self.log_info("read_velocity() returns %fstps/sec for axis %r" %
                      (velocity, axis.name))
        return velocity


    def set_velocity(self, axis, new_velocity):
        """Set axis velocity given in units/sec"""
        self.log_info("set_velocity(%fstps/sec) called for axis %r" %
                      (new_velocity, axis.name))

        l = libicepap.VelList()
        l[axis.libaxis] = new_velocity
        self.libgroup.velocity(l)

        # Always return the current velocity
        return self.read_velocity(axis)


    def read_acceleration(self, axis):
        """Returns axis current acceleration in steps/sec2"""
        acctime  = self.libgroup.acctime(axis.libaxis)
        velocity = self.read_velocity(axis)
        return velocity/acctime

    def set_acceleration(self, axis, new_acc):
        """Set axis acceleration given in steps/sec2"""
        self.log_info("set_acceleration(%fstps/sec2) called for axis %r" %
            (new_acc, axis.name))
        velocity     = self.read_velocity(axis)
        new_acctime  = velocity/new_acc

        self.log_info("set_acctime(%fsec) called for axis %r" %
                      (new_acctime, axis.name))
        l = libicepap.AcctimeList()
        l[axis.libaxis] = new_acctime
        self.libgroup.acctime(l)

        # Always return the current acceleration
        return self.read_acceleration(axis)

    def state(self, axis):
        """Returns the current axis state"""
        self.log_info("state() called for axis %r" % axis.name)

        # The axis can only be accessed through a group in IcePAP lib
        # Use the default group
        status = self.libgroup.status(axis.libaxis)

        # Convert status from icepaplib to bliss format.
        icestate = self.icestate.new()

        # first all concurrent states
        if(libicepap.status_lowlim(status)):
            icestate.set("LIMNEG")

        if(libicepap.status_highlim(status)):
            icestate.set("LIMPOS")

        if(libicepap.status_home(status)):
            icestate.set("HOME")

        modcod, modstr, moddsc = libicepap.status_get_mode(status)
        if modcod != None:
            icestate.set(modstr)

        sccod, scstr, scdsc = libicepap.status_get_stopcode(status)
        if sccod != None:
            icestate.set(scstr)

        if(libicepap.status_isready(status)):
            icestate.set("READY")
            # if motor is ready then no need to investigate deeper
            return icestate

        if(libicepap.status_ismoving(status)):
            icestate.set("MOVING")

        if(not libicepap.status_ispoweron(status)):
            icestate.set("POWEROFF")

        discod, disstr, disdsc = libicepap.status_get_disable(status)
        if discod != None:
            icestate.set(disstr)

        if not icestate.MOVING:
          # it seems it is not safe to call warning and/or alarm commands
          # while homing motor, so let's not ask if motor is moving
          if(libicepap.status_warning(status)):
              warn_str = self.libgroup.warning(axis.libaxis)
              warn_dsc = "warning condition: \n" + str(warn_str)
              icestate.create_state("WARNING",  warn_dsc)
              icestate.set("WARNING")

          alarm_str = self.libgroup.alarm(axis.libaxis)
          if alarm_str != 'NO':
              alarm_dsc = "alarm condition: " + str(alarm_str)
              icestate.create_state("ALARMDESC",  alarm_dsc)
              icestate.set("ALARMDESC")

        return icestate

    def prepare_move(self, motion):
        """
        Called once before a single axis motion,
        positions in motor units
        """
        self.log_info("prepare_move(%fstps) called for axis %r" %
            (motion.target_pos, motion.axis.name))
        pass

    def start_one(self, motion):
        """
        Called on a single axis motion,
        returns immediately,
        positions in motor units
        """
        self.log_info("start_one(%fsteps) called for axis %r" % 
            (motion.target_pos, motion.axis.name))
        target_positions = libicepap.PosList()
        target_positions[motion.axis.libaxis] = motion.target_pos
        self.libgroup.move(target_positions)

    def start_all(self, *motion_list):
        """
        Called once per controller with all the axis to move
        returns immediately,
        positions in motor units
        """
        self.log_info("start_all() called")
        target_positions = libicepap.PosList()
        for motion in motion_list:
            target_positions[motion.axis.libaxis] = motion.target_pos
        self.libgroup.move(target_positions)

    def stop(self, axis):
        """Stops smoothly an axis motion"""
        self.log_info("stop() called for axis %r" % axis.name)
        self.libgroup.stop(axis.libaxis)

    def stop_all(self, *motion_list):
        """Stops smoothly all the moving axis given"""
        self.log_info("stop_all() called")
        axis_list = []
        for motion in motion_list:
            axis_list.append(motion.axis.libaxis)
        self.libgroup.stop(axis_list)

    def home_search(self, axis, switch):
        """Launch a homing sequence"""
        cmd = "HOME " + ("+1" if switch > 0 else "-1")
        # TODO: MP17Nov14: missing argin on position to set at home
        # TODO: MP17Nov14: missing home search in IcePAP library
        self.libgroup.ackcommand(cmd, axis.libaxis)
        # IcePAP status is not immediately MOVING after home search command is sent
        time.sleep(0.2)

    def home_state(self, axis):
        """Returns the current axis state while homing"""
        return self.state(axis)

    def limit_search(self, axis, limit):
        """
        Launch a limitswitch search sequence
        the sign of the argin gives the search direction
        """
        cmd = "SRCH"
        if limit>0:
            cmd += " LIM+"
        else:
            cmd += " LIM-"
        
        # TODO: MP17Nov14: missing limit search in IcePAP library
        self.libgroup.ackcommand(cmd, axis.libaxis)
        # TODO: MG18Nov14: remove this sleep (state is not immediately MOVING)
        time.sleep(0.1)

    def initialize_encoder(self, encoder):
        """Encoder initialization"""
        self.log_info("initialize_encoder() called for axis %r" % encoder.name)

        # Get axis config from bliss config
        # address form is XY : X=rack {0..?} Y=driver {1..8}
        encoder.address = encoder.config.get("address", int)

        # Get optional encoder input to read
        try:
            enctype = string.upper(encoder.config.get("type"))
        except:
            enctype = "ENCIN"

        # Minium check on encoder input
        if enctype not in ['ENCIN', 'ABSENC', 'INPOS', 'MOTOR']:
            raise ValueError('Invalid encoder type')
        encoder.enctype = enctype

        # Create an IcePAP lib axis object for each encoder
        # as there is no encoder objects in the lib
        device  = self.libdevice
        address = encoder.address
        name    = encoder.name
        encoder.libaxis = libicepap.Axis(device, address, name)

        # Add the axis to the default IcePAP lib group
        self.libgroupenc.add_axis(encoder.libaxis)

    def read_encoder(self, encoder):
        """Returns encoder position in encoder units"""
        self.log_info("read_encoder() called for encoder %r" % encoder.name)

        # Prepare the command to acces directly the encoder input
        cmd = ' '.join(['?ENC', encoder.enctype])
        ret = self.libgroupenc.command(cmd, encoder.libaxis)

        # Return encoder steps
        return int(ret)

    def set_encoder(self, encoder, steps):
        """Set encoder position to a new value given in encoder units"""
        self.log_info("set_encoder(%f) called for encoder %r" % 
            (steps, encoder.name))

        # Prepare the command to acces directly the encoder input
        cmd = ' '.join(['ENC', encoder.enctype, '%d'%steps])
        self.libgroupenc.ackcommand(cmd, encoder.libaxis)

        # No need to return the current encoder position
        return

    def log_level(self, lvl):
        """Changes IcePAP and eMotion libraries verbose level"""

        # Change in the eMotion library
        log.level(lvl)

        # Value mapping between the two libraries
        #        eMotion == IcePAP
        #   NOTSET ==  0 == 0 == DBG_NONE
        #   DEBUG  == 10 == 4 == DBG_DATA
        #   INFO   == 20 == 2 == DBG_TRACE
        #   WARNING== 30 ==
        #   ERROR  == 40 == 1 == DBG_ERROR
        #   CRITIC == 50 ==
        #
        val = {
            log.NOTSET: 0,
            log.DEBUG: 4,
            log.INFO: 2,
            log.ERROR: 1,
        }[lvl]

        # Change in the IcePAP library
        self.libdevice.set_verbose(val)

        # Always return the current eMotion level
        self.log_info("log_level(%s) called, lib(%d)" %
                      (log.getLevelName(lvl), val))
        return log.level()

    def log_error(self, msg):
        """Logging method"""
        log.error(_ICEPAP_TAB + msg)

    def log_info(self, msg):
        """Logging method"""
        log.info(_ICEPAP_TAB + msg)

    @object_method()
    def get_id(self, axis):
        """Returns the unique string identifier of the specified axis"""
        self.log_info("get_id() called for axis %r" % axis.name)
        return self.libgroup.command("?ID", axis.libaxis)

    @object_method(name='MotToSync')
    def mot_to_sync(self, axis):
        """
        Broadcast the concerned DRIVER signal to all IcePAP system
        components (DRIVERs, CONTROLLERs, MASTER DB9 SYNCHRO connector)
        """

        # remove any previous multiplexer rule
        _cmd = "PMUX REMOVE"
        axis.libaxis.system().command(_cmd)

	# set the new multiplexer rule
        _cmd = "PMUX HARD B%d"%(axis.address)
        axis.libaxis.system().command(_cmd)

	# set which signal the DRIVER has to send to multiplexer
        _cmd = "SYNCPOS MEASURE"
        axis.libaxis.ackcommand(_cmd)
