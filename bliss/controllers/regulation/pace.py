import numpy
import gevent
from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.logtools import log_info, log_debug, log_error
from bliss.common.regulation import lazy_init
from bliss.controllers.regulator import Controller
from bliss.controllers.regulator import Loop as RegulationLoop


class Loop(RegulationLoop):
    def axis_position(self):
        return self.output.read()

    @lazy_init
    def regulation_stop(self):
        self._controller.stop_regulation(self)

    @lazy_init
    def regulation_start(self):
        self._controller.start_regulation(self)

    @property
    @lazy_init
    def regulation_state(self):
        output = self._controller.hw_controller.get_output_state(self.channel)
        return output is True and "ON" or "OFF"

    @lazy_init
    def __info__(self):
        ctrl_name = (
            self.controller.name
            if self.controller.name is not None
            else self.controller.__class__.__name__
        )
        in_unit = self.input.config.get("unit", "N/A")
        in_value = self.input.read()
        out_unit = self.output.config.get("unit", "N/A")
        out_value = self.output.read()
        if self.channel:
            out_state = self.output_state
        else:
            out_state = "???"

        lines = ["\n"]
        lines.append(f"=== Loop: {self.name} ===")
        lines.append(f"controller : {ctrl_name}")
        lines.append(f"inlet pressure [{self.input.name}]  : {in_value:.3f} {in_unit}")
        lines.append(
            f"current pressure [{self.output.name}] : {out_value:.3f} {out_unit}"
        )
        lines.append(f"output state : {out_state}")

        lines.append(f"\n=== Setpoint ===")
        lines.append(f"setpoint: {self.setpoint:.3f} {out_unit}")
        lines.append(f"ramprate: {self.ramprate:.3f} {out_unit}/s")
        lines.append(f"ramping: {self.is_ramping()}")

        return "\n".join(lines)


class PaceController:
    MODES = ["LIN", "MAX"]
    UNITS = ["ATM", "BAR", "MBAR", "PA", "HPA", "KPA", "MPA", "TORR", "KG/M2"]
    STATUS = {
        1 << 0: "Vent complete",
        1 << 1: "Range change complete",
        1 << 2: "In-limits reached",
        1 << 3: "Zero complete",
        1 << 4: "Auto-zero started",
        1 << 5: "Fill time, timed-out",
        1 << 7: "Range compare alarm",
        1 << 8: "Switch contacts changed state",
    }

    def __init__(self, config):
        self.comm = get_comm(config)
        self._eol = "\r"
        global_map.register(self.comm, parents_list=[self, "comms"])

        self.init()

    def close(self):
        self.comm.close()

    def __info__(self):
        info = f"Communication : {self.comm.__info__()}"
        info += f"MAC address   : {self.mac_address}\n"
        info += f"PACE Model    : {self.model}\n"
        info += f"Serial Number : {self.serial_number}"
        return info

    def init(self):
        log_debug(self, "init")
        resp = self.raw_putget("*IDN?")
        if "PACE" in resp:
            self.model = resp.split(",")[1]
        else:
            raise RuntimeError("Cannot read PACE model")
        self.mac_address = self.query_command(":INST:MAC")
        self.serial_number = self.query_command(":INST:SN")

    def raw_putget(self, cmd):
        cmd += self._eol
        return self.comm.write_readline(cmd.encode(), eol=self._eol).decode()

    def send_command(self, cmd):
        log_debug(self, "send_command", cmd)
        cmd += self._eol
        self.comm.write(cmd.encode())
        self.check_error()

    def query_command(self, cmd, getindex=1):
        log_debug(self, "query_command", cmd)
        if not cmd.endswith("?"):
            cmd += "?"

        resp = self.raw_putget(cmd)
        try:
            values = resp.split()
            val = values[getindex]
            return val.strip(self._eol)
        except (ValueError, AttributeError) as e:
            log_error(self, str(e))
            raise (e)

    def check_error(self):
        log_debug(self, "check_error")
        resp = self.raw_putget("SYST:ERR?")
        if "No error" not in resp:
            errmsg = resp.split(",")[1]
            log_error(self, errmsg)
            raise RuntimeError(errmsg)

    def set_rampmode(self, channel, mode):
        umode = mode.upper()
        if umode not in self.MODES:
            raise ValueError(f"Invalid mode {umode}")
        self.send_command(f"SOUR{channel:1d}:SLEW:MODE {umode}")

    def get_rampmode(self, channel):
        cmd = f"SOUR{channel:1d}:SLEW:MODE"
        resp = self.query_command(cmd)
        return str(resp)

    def set_setpoint(self, channel, value):
        max_sp = self.get_in_pressure(channel)
        if value > max_sp:
            raise ValueError(f"Asked setpoint too high !! Max is {max_sp:.3f}")
        cmd = f":SOUR{channel:1d}:PRES {value:f}"
        self.send_command(cmd)

    def get_setpoint(self, channel):
        cmd = f":SOUR{channel:1d}:PRES"
        resp = self.query_command(cmd)
        return float(resp)

    def set_ramprate(self, channel, value):
        cmd = f"SOUR{channel:1d}:PRES:SLEW {value:f}"
        self.send_command(cmd)

    def get_ramprate(self, channel):
        cmd = f":SOUR{channel:1d}:PRES:SLEW"
        resp = self.query_command(cmd)
        return float(resp)

    def set_unit(self, channel, unit):
        sunit = unit.upper()
        if sunit not in self.UNITS:
            raise ValueError(f"Invalid unit {sunit}")
        cmd = f":UNIT{channel:1d}:PRES {sunit}"
        self.send_command(cmd)

    def get_unit(self, channel):
        cmd = f":UNIT{channel:1d}:PRES"
        resp = self.query_command(cmd)
        return str(resp)

    def get_out_pressure(self, channel):
        cmd = f":SENS{channel:1d}:PRES"
        resp = self.query_command(cmd)
        return float(resp)

    def get_in_pressure(self, channel):
        cmd = f":SOUR{channel:1d}:PRES:COMP"
        resp = self.query_command(cmd)
        return float(resp)

    def set_output_state(self, channel, value):
        intval = value is True and 1 or 0
        cmd = f":OUTP{channel:1d}:STAT {intval}"
        self.send_command(cmd)

    def get_output_state(self, channel):
        cmd = f":OUTP{channel:1d}:STAT"
        resp = self.query_command(cmd)
        return int(resp) == 1

    def is_in_limits(self, channel):
        cmd = f":SENS{channel:1d}:PRES:INL"
        resp = self.query_command(cmd, getindex=2)
        return int(resp) == 1

    def get_status(self):
        cmd = ":STAT:OPER:COND"
        state = int(self.query_command(cmd))
        status = ""
        for (value, text) in self.STATUS.items():
            if state & value:
                status += text
                status += "\n"
        return status


class Pace(Controller):
    def __init__(self, config):
        super().__init__(config)

        self._hw_controller = None
        self._channels = list()

    @property
    def hw_controller(self):
        if self._hw_controller is None:
            self._hw_controller = PaceController(self.config)
        return self._hw_controller

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
        """
        self.hw_controller

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        if tinput.channel is None:
            tinput._channel = 1
        config_unit = tinput.config.get("unit", None)
        if config_unit is not None:
            self.hw_controller.set_unit(tinput.channel, config_unit)
        ctrl_unit = self.hw_controller.get_unit(tinput.channel)
        tinput.config["unit"] = ctrl_unit.lower()
        for cnts in tinput._counters.values():
            cnts.unit = ctrl_unit.lower()

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        if toutput.channel is None:
            toutput._channel = 1
        config_unit = toutput.config.get("unit", None)
        if config_unit is not None:
            self.hw_controller.set_unit(toutput.channel, config_unit)
        ctrl_unit = self.hw_controller.get_unit(toutput.channel)
        toutput.config["unit"] = ctrl_unit.lower()
        for cnts in toutput._counters.values():
            cnts.unit = ctrl_unit.lower()

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        if tloop.output.channel != tloop.input.channel:
            raise ValueError("output channel != input channel on loop {tloop.name}")
        tloop._channel = tloop.output.channel
        tloop._force_ramping_from_current_pv = False
        tloop._wait_mode = tloop.WaitMode.RAMP
        self._channels.append(tloop.channel)
        ctrl_unit = tloop.output.config["unit"]
        tloop.axis._unit = ctrl_unit
        tloop.axis.limits = (0., numpy.inf)
        for cnts in tloop._counters.values():
            cnts.unit = ctrl_unit

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """
        Reads an Input class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object 

        Returns:
           read value  (in input unit)    
        """
        log_info(self, "Controller:read_input: %s" % (tinput))
        return self.hw_controller.get_in_pressure(tinput.channel)

    def read_output(self, toutput):
        """
        Reads an Output class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 

        Returns:
           read value (in output unit)         
        """
        log_info(self, "Controller:read_output: %s" % (toutput))
        return self.hw_controller.get_out_pressure(toutput.channel)

    def state_input(self, tinput):
        """
        Return a string representing state of an Input object.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log_info(self, "Controller:state_input: %s" % (tinput))
        raise NotImplementedError

    def state_output(self, toutput):
        """
        Return a string representing state of an Output object.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log_info(self, "Controller:state_output: %s" % (toutput))
        raise NotImplementedError

    # ------ PID methods ------------------------

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        It must NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))
        self.hw_controller.set_output_state(tloop.channel, True)

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        It must NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        self.hw_controller.set_output_state(tloop.channel, False)

    def set_kp(self, tloop, kp):
        """
        Set the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kp: the kp value
        """
        log_info(self, "Controller:set_kp: %s %s" % (tloop, kp))
        pass

    def get_kp(self, tloop):
        """
        Get the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           kp value
        """
        log_info(self, "Controller:get_kp: %s" % (tloop))
        pass

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki: the ki value
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        pass

    def get_ki(self, tloop):
        """
        Get the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           ki value
        """
        log_info(self, "Controller:get_ki: %s" % (tloop))
        pass

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd: the kd value
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        pass

    def get_kd(self, tloop):
        """
        Reads the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Output class type object 
        
        Returns:
           kd value
        """
        log_info(self, "Controller:get_kd: %s" % (tloop))
        pass

    # ------ setpoint methods ------------------------

    def set_setpoint(self, tloop, sp, **kwargs):
        """
        Set the current setpoint (target value).
        It must NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           sp:     setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:set_setpoint: %s %s" % (tloop, sp))
        raise NotImplementedError

    def get_setpoint(self, tloop):
        """
        Get the current setpoint (target value)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (float) setpoint value (in tloop.input unit).
        """
        log_info(self, "Controller:get_setpoint: %s" % (tloop))
        return self.hw_controller.get_setpoint(tloop.channel)

    def get_working_setpoint(self, tloop):
        """
        Get the current working setpoint (setpoint along ramping)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (float) working setpoint value (in tloop.input unit).
        """
        log_info(self, "Controller:get_working_setpoint: %s" % (tloop))
        raise NotImplementedError

    # ------ setpoint ramping methods (optional) ------------------------

    def start_ramp(self, tloop, sp, **kwargs):
        """
        Start ramping to a setpoint
        It must NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Replace 'Raises NotImplementedError' by 'pass' if the controller has ramping but doesn't have a method to explicitly starts the ramping.
        Else if this function returns 'NotImplementedError', then the Loop 'tloop' will use a SoftRamp instead.

        Args:
           tloop:  Loop class type object
           sp:       setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:start_ramp: %s %s" % (tloop, sp))
        self.hw_controller.set_output_state(tloop.channel, True)
        self.hw_controller.set_setpoint(tloop.channel, sp)
        gevent.sleep(.1)

    def stop_ramp(self, tloop):
        """
        Stop the current ramping to a setpoint
        It must NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        if not self.hw_controller.is_in_limits(tloop.channel):
            current = self.hw_controller.get_out_pressure(tloop.channel)
            self.hw_controller.set_setpoint(tloop.channel, current)

    def is_ramping(self, tloop):
        """
        Get the ramping status.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "Controller:is_ramping: %s" % (tloop))
        in_limits = self.hw_controller.is_in_limits(tloop.channel)
        return in_limits is False

    def set_ramprate(self, tloop, rate):
        """
        Set the ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           rate:   ramp rate (in input unit per second)
        """
        log_info(self, "Controller:set_ramprate: %s %s" % (tloop, rate))
        if rate == 0:
            self.hw_controller.set_rampmode(tloop.channel, "MAX")
        else:
            self.hw_controller.set_rampmode(tloop.channel, "LIN")
            self.hw_controller.set_ramprate(tloop.channel, rate)

    def get_ramprate(self, tloop):
        """
        Get the ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        
        Returns:
           ramp rate (in input unit per second)
        """
        log_info(self, "Controller:get_ramprate: %s" % (tloop))
        rampmode = self.hw_controller.get_rampmode(tloop.channel)
        if rampmode == "MAX":
            return 0.
        else:
            return self.hw_controller.get_ramprate(tloop.channel)

    # ------ raw methods (optional) ------------------------

    def Wraw(self, string):
        """
        A string to write to the controller
        Raises NotImplementedError if not defined by inheriting class

        Args:
           string:  the string to write
        """
        log_info(self, "Controller:Wraw:")
        self.hw_controller.send_command(string)

    def Rraw(self):
        """
        Reading the controller
        Raises NotImplementedError if not defined by inheriting class

        returns:
           answer from the controller
        """
        log_info(self, "Controller:Rraw:")
        raise NotImplementedError("Use either Wraw or WRraw")

    def WRraw(self, string):
        """
        Write then Reading the controller
        Raises NotImplementedError if not defined by inheriting class

        Args:
           string:  the string to write
        returns:
           answer from the controller
        """
        log_info(self, "Controller:WRraw:")
        return self.hw_controller.query_command(string)

    # --- controller method to set the Output to a given value (optional) -----------

    def set_output_value(self, toutput, value):
        """
        Set the value on the Output device.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput: Output class type object 
           value: value for the output device (in output unit)      
        """
        log_info(self, "Controller:set_output_value: %s %s" % (toutput, value))
        raise NotImplementedError

    # --- controller methods to handle the ramping on the Output (optional) -----------

    def start_output_ramp(self, toutput, value, **kwargs):
        """
        Start ramping on the output
        Raises NotImplementedError if not defined by inheriting class

        Replace 'Raises NotImplementedError' by 'pass' if the controller has output ramping but doesn't have a method to explicitly starts the output ramping.
        Else if this function returns 'NotImplementedError', then the output 'toutput' will use a SoftRamp instead.

        Args:
           toutput:  Output class type object 
           value:    target value for the output ( in output unit )
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:start_output_ramp: %s %s" % (toutput, value))
        raise NotImplementedError

    def stop_output_ramp(self, toutput):
        """
        Stop the current ramping on the output
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        """
        log_info(self, "Controller:stop_output_ramp: %s" % (toutput))
        raise NotImplementedError

    def is_output_ramping(self, toutput):
        """
        Get the output ramping status.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "Controller:is_output_ramping: %s" % (toutput))
        raise NotImplementedError

    def set_output_ramprate(self, toutput, rate):
        """
        Set the output ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
           rate:     ramp rate (in output unit per second)
        """
        log_info(self, "Controller:set_output_ramprate: %s %s" % (toutput, rate))
        raise NotImplementedError

    def get_output_ramprate(self, toutput):
        """
        Get the output ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        
        Returns:
           ramp rate (in output unit per second)
        """
        log_info(self, "Controller:get_output_ramprate: %s" % (toutput))
        raise NotImplementedError

    # --- Custom methods ------------------------------

    def __info__(self):
        infos = self.hw_controller.__info__()
        for chan in self._channels:
            state = self.hw_controller.get_output_state(chan)
            state = state is True and "ON" or "OFF"
            infos += f"\nCHANNEL {chan}: output is {state}"
        return infos
