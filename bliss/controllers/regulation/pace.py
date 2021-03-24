from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.logtools import log_info, log_debug, log_error
from bliss.controllers.regulator import Controller

class PaceController:
    MODES = ["LIN", "MAX"]
    UNITS = ["ATM", "BAR", "MBAR", "PA", "HPA", "KPA", "MPA", "TORR", "KG/M2"]

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

    def query_command(self, cmd):
        log_debug(self, "query_command", cmd)
        if not cmd.endswith("?"):
            cmd += "?"

        resp = self.raw_putget(cmd)
        try:
            _, val = resp.split()
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

    def set_mode(self, channel, mode):
        umode = mode.upper()
        if umode not in self.MODES:
            raise ValueError(f"Invalid mode {umode}")
        self.send_command(f"SOUR{channel:1d}:SLEW:MODE {umode}")

    def get_mode(self, channel):
        cmd = f"SOUR{channel:1d}:SLEW:MODE"
        resp = self.query_command(cmd)
        return str(resp)

    def set_setpoint(self, channel, value):
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

    def get_pressure(self, channel):
        cmd = f":SENS{channel:1d}:PRES"
        resp = self.query_command(cmd)
        return float(resp)

class Pace(Controller):

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
        """
        self.hw_controller = PaceController(self.config)

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        if tinput.channel is None:
            tinput._channel = 1 
        tinput.config["unit"] = self.hw_controller.get_unit(tinput.channel)

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        if toutput.channel is None:
            toutput._channel = 1
        toutput.config["unit"] = self.hw_controller.get_unit(toutput.channel)

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        tloop._channel = tloop.output.channel

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
        return self.hw_controller.get_pressure(tinput.channel)

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
        return self.hw_controller.get_pressure(toutput.channel)

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
        pass

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        It must NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        pass

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
        self.hw_controller.get_setpoint(tloop.channel)
        
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
        raise NotImplementedError

    def stop_ramp(self, tloop):
        """
        Stop the current ramping to a setpoint
        It must NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        raise NotImplementedError

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
        raise NotImplementedError

    def set_ramprate(self, tloop, rate):
        """
        Set the ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           rate:   ramp rate (in input unit per second)
        """
        log_info(self, "Controller:set_ramprate: %s %s" % (tloop, rate))
        raise NotImplementedError

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
        raise NotImplementedError

    # ------ raw methods (optional) ------------------------

    def Wraw(self, string):
        """
        A string to write to the controller
        Raises NotImplementedError if not defined by inheriting class

        Args:
           string:  the string to write
        """
        log_info(self, "Controller:Wraw:")
        raise NotImplementedError

    def Rraw(self):
        """
        Reading the controller
        Raises NotImplementedError if not defined by inheriting class

        returns:
           answer from the controller
        """
        log_info(self, "Controller:Rraw:")
        raise NotImplementedError

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
        raise NotImplementedError

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

