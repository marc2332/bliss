# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import re
import numpy

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.utils import object_method
from bliss.common.utils import OrderedDict
from bliss.common.utils import grouped

from bliss.common.axis import AxisState

import pi_gcs
from bliss.comm.util import TCP

"""
Bliss controller for ethernet PI E712 piezo controller.
Copied from the preliminary E517 controller.
Programmed keeping in mind, that we might have a PI controller class, which could
be inherited to the E517, E712 etc.

Holger Witsch ESRF BLISS
Oct 2014

config example:
- class: PI_E712
  tcp:
    url: nscopepi712
  axes:
  - name: py
    channel: 1
    velocity: 100
    acceleration: 1.
    steps_per_unit: 1
    dc_dead_band: 10000000
    dc_settle_time: 0.05
    slop: 160000
    servo_mode: 1

  - name: px
    channel: 2
    velocity: 100
    acceleration: 1.
    steps_per_unit: 1
    dc_dead_band: 10000000
    dc_settle_time: 0.05
    slop: 80000
    servo_mode: 1
"""


class PI_E712(Controller):
    #POSSIBLE DATA TRIGGER SOURCE
    WAVEFORM=0
    MOTION=1
    EXTERNAL=3
    IMMEDIATELY=4

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.sock = None
        self.cname = "E712"

    def initialize(self):
        """
        Controller intialization : opens a single socket for all 3 axes.
        """
        self.sock = pi_gcs.get_pi_comm(self.config, TCP)

    def finalize(self):
        """
        Closes the controller socket.
        """
        if self.sock:
            self.sock.close()

    def initialize_axis(self, axis):
        """
        - Reads specific config
        - Adds specific methods
        - Switches piezo to ONLINE mode so that axis motion can be caused
          by move commands.

        Args:
            - <axis>
        Returns:
            - None
        """
        elog.info("initialize_axis() called for axis %r" % axis.name)

        self._hw_status = AxisState("READY")


        """ Documentation uses the word AxisID instead of channel
            Note: any function used as axis method must accept axis as an argument! Otherwise
                  you will see:
                  TypeError: check_power_cut() takes exactly 1 argument (2 given)
        """
        axis.channel = axis.config.get("channel", int)
        try:
            axis.paranoia_mode = axis.config.get("paranoia_mode")  # check error after each command
        except KeyError :
            axis.paranoia_mode = False

        self._gate_enabled = False

        # Updates cached value of closed loop status.
        axis.closed_loop = self._get_closed_loop_status(axis)
        self.check_power_cut()

        elog.debug("axis = %r" % axis.name)
        #elog.debug("axis.encoder = %r" % axis.encoder)
        #if axis.encoder:
            #elog.debug("axis = %r" % axis)

        #POSSIBLE DATA RECORDER TYPE
        axis.TARGET_POSITION_OF_AXIS=1
        axis.CURRENT_POSITION_OF_AXIS=2
        axis.POSITION_ERROR_OF_AXIS=3
        axis.CONTROL_VOLTAGE_OF_OUTPUT_CHAN=7
        axis.DDL_OUTPUT_OF_AXIS=13
        axis.OPEN_LOOP_CONTROL_OF_AXIS=14
        axis.CONTROL_OUTPUT_OF_AXIS=15
        axis.VOLTAGE_OF_OUTPUT_CHAN=16
        axis.SENSOR_NORMALIZED_OF_INPUT_CHAN=17
        axis.SENSOR_FILTERED_OF_INPUT_CHAN=18
        axis.SENSOR_ELECLINEAR_OF_INPUT_CHAN=19
        axis.SENSOR_MECHLINEAR_OF_INPUT_CHAN=20
        axis.SLOWED_TARGET_OF_AXIS=22

        #POSSIBLE DATA TRIGGER SOURCE
        axis.WAVEFORM=0
        axis.MOTION=1
        axis.EXTERNAL=3
        axis.IMMEDIATELY=4

        # supposed that we are on target on init
        axis._last_on_target = True
        
    def read_position(self, axis):
        """
        Returns position's setpoint or measured position.
        Measured position command is POS?
        Setpoint position is MOV? of VOL? or SVA? depending on closed-loop
        mode is ON or OFF.

        Args:
            - <axis> : bliss axis.
            - [<measured>] : boolean : if True, function returns measured position.
        Returns:
            - <position> : float : piezo position in Micro-meters or in Volts.
        """
        if axis._last_on_target:
            _pos = self._get_target_pos(axis)
            elog.debug("position read : %g" % _pos)
        else:                   # if moving return real position
            _pos = self._get_pos(axis)


        return _pos

    """ VELOCITY """
    def read_velocity(self, axis):
        """
        """
        # _ans should look like "A=+0012.0000"
        # removes 'X=' prefix
        _velocity = float(self.command("VEL? %s" % axis.channel))
        elog.debug("read_velocity : %g " % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.command("VEL %s %f" %
                     (axis.channel, new_velocity))
        elog.debug("velocity set : %g" % new_velocity)
        return self.read_velocity(axis)

    """ STATE """
    def state(self, axis):
        elog.debug("axis.closed_loop for axis %s is %s" % (axis.name, axis.closed_loop))

        if axis.closed_loop:
            if self._get_on_target_status(axis):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            elog.debug("CLOSED-LOOP is False")
            # ok for open loop mode...
            return AxisState("READY")

    """ MOVEMENTS """
    def prepare_move(self, motion):
        elog.debug("pass")
        pass

    def start_one(self, motion):
        """
        - Sends 'MOV' or 'SVA' depending on closed loop mode.

        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        """

###
###  hummm a bit dangerous to mix voltage and microns for the same command isnt'it ?
###
        if motion.axis.closed_loop:
            # Command in position.
            self.command("MOV %s %g" %
                         (motion.axis.channel, motion.target_pos))
            elog.debug("Command to piezo MOV %s %g"%
                       (motion.axis.channel, motion.target_pos))

        else:
            # Command in voltage.
            self.command("SVA %s %g" %
                         (motion.axis.channel, motion.target_pos))
            elog.debug("Command to piezo SVA %s %g"%
                       (motion.axis.channel, motion.target_pos))

    def stop(self, axis):
        """
        * HLT -> stop smoothly
        * STP -> stop asap
        * 24    -> stop asap
        """
        elog.debug("Stopping Piezo by opening loop")
        self._set_closed_loop(self, axis, False)
        #self.send_no_ans(axis, "SVO %s" % axis.channel)

    """ RAW COMMANDS """
    def raw_write(self, axis, com):
        self.sock.write("%s\n" % com)

    def raw_write_read(self, axis, com):
        return self.sock.write_readline("%s\n" % com)

    def get_identifier(self, axis):
        """
        Returns Identification information (\*IDN? command).
        """
        return self.command("*IDN?\n")


    def command(self, cmd, nb_line=1):
        """
        Method to send command to the controller
        """
        cmd = cmd.strip()
        need_reply = cmd.find('?') > -1
        if need_reply:
            if nb_line > 1:
                reply = self.sock.write_readlines(cmd + '\n', nb_line)
            else:
                reply = self.sock.write_readline(cmd + '\n')

            if not reply:       # it's an error
                errors = [self.name] + list(self.get_error())
                raise RuntimeError("Device {0} error nb {1} => ({2})".format(*errors))

            if nb_line > 1:
                parsed_reply = list()
                commands = cmd.split('\n')
                if len(commands) == nb_line: # one reply per command
                    for cmd, rep in zip(commands, reply):
                        space_pos = cmd.find(' ')
                        if space_pos > -1:
                            args = cmd[space_pos+1:]
                            parsed_reply.append(self._parse_reply(rep, args))
                        else:
                            parsed_reply.append(rep)
                else:           # a command with several replies
                    space_pos = cmd.find(' ')
                    if space_pos > -1:
                        args = cmd[space_pos+1:]
                        for arg, rep in zip(args.split(), reply):
                            parsed_reply.append(self._parse_reply(rep, arg))
                reply = parsed_reply
            else:
                space_pos = cmd.find(' ')
                if space_pos > -1:
                    reply = self._parse_reply(reply, cmd[space_pos+1:])
            return reply
        else:
            self.sock.write(cmd + '\n')

    def get_data(self, from_event_id=0, npoints=None, rec_table_id=None):
        """
        retrieved store data as a numpy structured array,
        struct name will be the data_type + motor name.
        i.e:
        Target_Position_of_<motor_name> or Current_Position_of_<motor_name>

        Args:
         - from_event_id from which point id you want to read
         - rec_table_id list of table you want to read, None means all
        """
        if rec_table_id is None: # All table
            #just ask the first table because they have the same synchronization
            nb_availabe_points = int(self.command("DRL? 1"))
            nb_availabe_points -= from_event_id
            if npoints is None:
                npoints = nb_availabe_points
            else:
                npoints = min(nb_availabe_points,npoints)
            cmd = "DRR? %d %d\n" % ((from_event_id + 1),npoints)
        else:
            rec_tables = ' '.join((str(x) for x in rec_table_id))
            nb_points = self.command("DRL? %s" % rec_tables,len(rec_table_id))
            if isinstance(nb_points, list):
                nb_points = min([int(x) for x in nb_points])
            else:
                nb_points = int(nb_points)
            point_2_read = nb_points - from_event_id
            if point_2_read < 0:
                point_2_read = 0
            elif(npoints is not None and
                 point_2_read > npoints):
                point_2_read = npoints
            cmd = "DRR? %d %d %s\n" % (from_event_id + 1, point_2_read,
                                       rec_tables)

        try:
            with self.sock._lock:
                self.sock._write(cmd)
                #HEADER
                header = dict()
                while 1:
                    line = self.sock.readline()
                    if not line:
                        return      # no data available
                    if line.find("END_HEADER") > -1:
                        break

                    key,value = (x.strip() for x in line[1:].split('='))
                    header[key] = value

                ndata = int(header['NDATA'])
                separator = chr(int(header['SEPARATOR']))
                sample_time = float(header['SAMPLE_TIME'])
                dim = int(header['DIM'])
                column_info = dict()
                keep_axes = {x.channel : x for x in self.axes.values()}
                for name_id in range(8):
                    try:
                        desc = header['NAME%d' % name_id]
                    except KeyError:
                        break
                    else:
                        axis_pos = desc.find('axis')
                        if axis_pos < 0:
                            axis_pos = desc.find('chan')
                        axis_id = int(desc[axis_pos+len('axis'):])
                        if axis_id in keep_axes:
                             new_desc = desc[:axis_pos] + \
                                        keep_axes[axis_id].name
                             column_info[name_id] = new_desc.replace(' ','_')

                dtype = [('timestamp','f8')]
                dtype += [(name,'f8') for name in column_info.values()]
                data = numpy.zeros(ndata,dtype=dtype)
                data['timestamp'] = numpy.arange(from_event_id,
                                                 from_event_id + ndata) * sample_time
                for line_id in range(ndata):
                    line = self.sock.readline().strip()
                    values = line.split(separator)
                    for column_id, name in column_info.iteritems():
                        data[name][line_id] = values[column_id]
                return data
        except:
            self.sock.close()   # safe in case of ctrl-c
            raise
        
    def set_recorder_data_type(self,*motor_data_type):
        """
        Configure the data recorder

        Args:
          motor_data_type should be a list of tuple with motor and datatype
          i.e: motor_data_type=[px,px.CURRENT_POSITION_OF_AXIS,
                                py,py.CURRENT_POSITION_OF_AXIS]
        """
        nb_recorder_table = len(motor_data_type) / 2
        if nb_recorder_table * 2 != len(motor_data_type):
            raise RuntimeError("Argument must be grouped by 2 "
                               "(motor1,data_type1,motor2,data_type2...)")
        
        self.command("SPA 1 0x16000300 %d" % nb_recorder_table)
        max_nb_recorder = int(self.command("TNR?"))
        if nb_recorder_table > max_nb_recorder:
            raise RuntimeError("Device %s too many recorder data, can only record %d" %
                               (self.name,max_nb_recorder))
        cmd = "DRC "
        cmd += ' '.join(('%d %s %d' % (rec_id+1,motor.channel,data_type)
                         for rec_id,(motor,data_type) in
                         enumerate(grouped(motor_data_type,2))))
        self.command(cmd)

    def start_recording(self, trigger_source, value=0, recorder_rate=None):
        """
        start recording data according to what was asked to record.
        @see set_recorder_data_type

        Args:
          - trigger_source could be WAVEFORM,MOTION,EXTERNAL,IMMEDIATELY
          - value for EXTERNAL value is the trigger input line (0 mean all)
          - recorder_rate if None max speed otherwise the period in seconds
        """
        if trigger_source not in (self.WAVEFORM,self.MOTION,
                                  self.EXTERNAL,self.IMMEDIATELY):
            raise RuntimeError("Device %s trigger source can only be:"
                               "WAVEFORM,MOTION,EXTERNAL or IMMEDIATELY")

        if recorder_rate is not None:
            cycle_time = float(self.command("SPA? 1 0xe000200"))
            rate = int(recorder_rate / cycle_time) # should be faster than asked
        else:
            rate = 1

        self.command("RTR %d" % rate)
        
        nb_recorder = int(self.command("TNR?"))
        cmd = "DRT "
        cmd += ' '.join(('%d %d %d' % (rec_id,trigger_source,value)
                         for rec_id in range(1,nb_recorder+1)))
        self.command(cmd)

    def get_recorder_data_rate(self):
        """
        return the rate of the data recording in seconds
        """
        cycle_time,rtr = self.command("SPA? 1 0xe000200\nRTR?",2)
        return float(cycle_time) * int(rtr)

    def output_position_gate(self, axis,
                             position_1, position_2, output=1):
        """
        This program an external gate on the specified output.
        If the motor position is in between the programmed positions,
        the signal is high.

        Args:
          - output by default first external output
        """
        cmd = "CTO {0} 2 {1} {0} 3 3 {0} 5 {2} {0} 6 {3} {0} 7 1".\
        format(output,axis.channel,position_1,position_2)
        self.command(cmd)
        error_id,error_msg = self.get_error()
        if error_id:
            errors = [self.name,error_id,error_msg]
            raise RuntimeError("Device {0} error nb {1} => ({2})".format(*errors))

    
    def _parse_reply(self, reply, args):
        args_pos = reply.find('=')
        if reply[:args_pos] != args: # weird
            print 'Weird thing happens with connection of %s' % self.name
            return reply
        else:
            return reply[args_pos+1:]
        
    def _get_pos(self, axis):
        """
        Args:
            - <axis> :
        Returns:
            - <position> Returns real position (POS? command) 

        Raises:
            ?
        """
        _pos = float(self.command("POS? %s" % axis.channel))

        return _pos

    def _get_target_pos(self, axis):
        """
        Returns last valid position setpoint ('MOV?' command).
        """
        axis.closed_loop = self._get_closed_loop_status(axis)
        if axis.closed_loop:
            _ans = self.command("MOV? %s" % axis.channel)
        else:
            _ans = self.command("SVA? %s" % axis.channel)

        return float(_ans)

    def _get_target_voltage(self, axis):
        """
        Returns last valid voltage setpoint ('SVA?' command).
        """
        return float(self.command("SVA? %s" % axis.channel))


    def _get_voltage(self, axis):
        """
        Returns Read Voltage Of Output Signal Channel (VOL? command)
        """
        return float(self.command("VOL? %s" % axis.channel))

    def _set_closed_loop(self, axis, onoff = True):
        """
        Sets Closed loop status (Servo state) (SVO command)
        """

        axis.closed_loop = onoff
        self.command("SVO %s %d" % (axis.channel, onoff))
        elog.debug("Piezo Servo %r" % onoff)


        # Only when closing loop: waits to be ON-Target.
        if onoff:
            _t0 = time.time()
            cl_timeout = .5

            _ont_state = self._get_on_target_status(axis)
            elog.info(u'axis {0:s} waiting to be ONTARGET'.format(axis.name))
            while (not _ont_state) and (time.time() - _t0) < cl_timeout:
                time.sleep(0.01)
                print ".",
                _ont_state = self._get_on_target_status(axis)
            if not _ont_state:
                elog.error('axis {0:s} NOT on-target'.format(axis.name))
                raise RuntimeError("Unable to close the loop : "
                                   "not ON-TARGET after %gs :( " % cl_timeout)
            else:
                elog.info('axis {0:s} ONT ok after {1:g} s'.format(axis.name, time.time() - _t0))

        # Updates bliss setting (internal cached) position.
        axis._position()  # "POS?"


    def _get_closed_loop_status(self, axis):
        """
        Returns Closed loop status (Servo state) (SVO? command)
        -> True/False
        """
        return bool(int(self.command("SVO? %s" % axis.channel)))

    def _get_on_target_status(self, axis):
        """
        -

        Args:
            - <>
        Returns:
            -
        Raises:
            - ?
        """
        """
        Returns On Target status (ONT? command).
        True/False
        """
        last_on_target = bool(int(self.command("ONT? %s" % axis.channel)))
        axis._last_on_target = last_on_target
        return last_on_target

    def get_error(self):
        _error_number = int(self.sock.write_readline("ERR?\n"))
        _error_str = pi_gcs.get_error_str(_error_number)

        return (_error_number, _error_str)

    def get_info(self, axis):
        """
        Returns a set of useful information about controller.
        Helpful to tune the device.

        Args:
            <axis> : bliss axis
        Returns:
            None
        Raises:
            ?
        """
        _infos = [
            ("Identifier                 ", "*IDN?"),
            ("Com level                  ", "CCL?"),
            ("GCS Syntax version         ", "CSV?"),
            ("Last error code            ", "ERR?"),
            ("Real Position              ", "POS? %s" % axis.channel),
            ("Closed loop status         ", "SVO? %s" % axis.channel),
            ("Output Voltage             ", "VOL? %s" % axis.channel),
            ("Setpoint Position          ", "MOV? %s" % axis.channel),
            ("On target                  ", "ONT? %s" % axis.channel),
            ("On target window           ", "SPA? %s 0x7000900" % axis.channel),
            ("On target settling time    ", "SPA? %s 0x7000901" % axis.channel),
            ("ADC Value of input signal  ", "TAD? %s" % axis.channel),
            ("Input Signal Position value", "TSP? %s" % axis.channel),
            ("Velocity                   ", "VEL? %s" % axis.channel),
            ("sensor Offset              ", "SPA? %s 0x2000200" % axis.channel),
            ("sensor Gain                ", "SPA? %s 0x2000300" % axis.channel),
            ("sensor gain 2nd order      ", "SPA? %s 0x2000400" % axis.channel),
            ("sensor gain 3rd order      ", "SPA? %s 0x2000500" % axis.channel),
            ("sensor gain 4th order      ", "SPA? %s 0x2000600" % axis.channel),

            ("Digital filter type        ", "SPA? %s 0x5000000" %
             axis.channel),
            ("Digital filter Bandwidth   ", "SPA? %s 0x5000001" %
             axis.channel),
            ("Digital filter order       ", "SPA? %s 0x5000002" %
             axis.channel),
        ]

        _txt = ""

        for text, cmd in _infos:
            _txt = _txt + "    %s %s\n" % (text, self.command(cmd))

        _txt = _txt + "    %s  \n%s\n" % \
            ("\nCommunication parameters",
             "\n".join(self.command("IFC?", 5)))

        return _txt

    def check_power_cut(self):
        """
        checks if command level is on 1, if 0 means power has been cut
        in that case, set command level to 1
        """
        _ans = self.command("CCL?")  # get command level
        elog.debug("command_level was : %d " % int(_ans))
        if _ans == "0":
            self.command("CCL 1 advanced")

    def get_sensor_coeffs(self, axis):
        """
        Returns a list with sensor coefficients:
        * Offset
        * Gain constant order
        * Gain 2nd order
        * Gain 3rd order
        * Gain 4th order
        """
        commands = '\n'.join(("SPA? %d 0x2000%d00" % (axis.channel, i+2))
                             for i in range(5))
        axis.coeffs = [float(x) for x in self.command(commands, 5)]
        return axis.coeffs

    def set_sensor_coeffs(self, axis, coeff, value):
        """
        Needed, when in the table, when senson works the opposite way
        Returns a list with sensor coefficients:
        * Offset
        * Gain constant order
        * Gain 2nd order
        * Gain 3rd order
        * Gain 4th order
        """
        self.command("SPA %s 0x2000%d00 %f" % (axis.channel, coeff+2, value))

    def _get_tns(self, axis):
        """Get Normalized Input Signal Value. Loop 10 times to straighten out noise"""
        accu = 0
        for _ in range(10):
            time.sleep(0.01)
            _ans = self.command("TNS? %s" % axis.channel)
            #elog.debug("TNS? %d : %r" % (axis.channel, _ans))
            if _ans != '0':
                accu += float(_ans)
                accu /= 2
        elog.debug("TNS? %r" % accu)
        # during tests with the piezojack, problems with a blocked socket
        # towards the controller were encountered. Usually, that was 
        # manifesting with 0 TNS readings. If The accumulated value of
        # TNS is 0, we're pretty sure the connection is broken.
        # Use self.finalize() to close the socket, it should be reopened
        # by the next communication attempt.
        if accu == 0:
            elog.info("%s##########################################################%s" %
                      (bcolors.GREEN+bcolors.BOLD, bcolors.ENDC))
            elog.info("%sPIEZO READ TNS, accu is zero, resetting socket connection!%s" %
                      (bcolors.GREEN+bcolors.BOLD, bcolors.ENDC))
            elog.info("%s##########################################################%s" %
                      (bcolors.GREEN+bcolors.BOLD, bcolors.ENDC))
            self.finalize()
        return accu

    def _get_tsp(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.command("TSP? %s" % axis.channel)
        elog.debug("TSP? %s" % _ans)
        return float(_ans)

    def _get_sva(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.command("SVA? %s" % axis.channel)
        elog.debug("SVA? %s" % _ans)
        return float(_ans)

    def _get_vol(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.command("VOL? %s" % axis.channel)
        elog.debug("VOL? %s" % _ans)
        return float(_ans)

    def _get_mov(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.command("MOV? %s" % axis.channel)
        elog.debug("MOV? %s" % _ans)
        return float(_ans)

    def _get_offset(self, axis):
        """read the offset SPA? 4 0x2000200 will yield 4 0x2000200=0.yxyxyxy+00"""
        return float(self.command("SPA? %s 0x2000200" % axis.channel))

    def _put_offset(self, axis, value):
        """write offset"""
        self.command("SPA %s 0x2000200 %f" % (axis.channel, value))
        axis.coeffs[0] = value

    def _get_tad(self, axis):
        """ TAD? delivers the ADC value"""

        accu = 0
        for _ in range(10):
            time.sleep(0.01)
            _ans = self.command("TAD? %s" % axis.channel)
            if _ans != '0':
                accu += float(_ans)
                accu /= 2
        elog.debug("TAD? %r" % accu)
        return accu

class bcolors:
    CSI="\x1B["
    BOLD = CSI + '1m'
    GREY = CSI + '100m'
    RED = CSI + '101m'
    GREEN = CSI + '102m'
    YELLOW = CSI + '103m'
    BLUE = CSI + '104m'
    MAGENTA = CSI + '105m'
    LIGHTBLUE = CSI + '106m'
    WHITE = CSI + '107m'
    ENDC = CSI + '0m'

