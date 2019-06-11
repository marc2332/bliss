# XPS Python class
#
#  for XPS-Q8 Firmware Precision Platform V1.2.x
#
#  See Programmer's manual for more information on XPS function calls
#
# These are modified versions of the original XPS python driver code,
# found at https://www.newport.com/p/XPS-Q4 link XPS-Q_Drivers, modified to
# use Bliss comm sockets with considerable tidying.
# Each method returns a list comprising [errorcode, values ...]


from bliss.comm.util import get_comm, TCP


class XPS:
    def __init__(self, config_dict):
        comm_opt = {"ctype": "tcp", "timeout": 30.0, "port": 5001}
        self._sock = get_comm(config_dict, **comm_opt)

    # Send command and get return
    def __sendAndReceive(self, command):
        try:
            ans = self._sock.write_readline(command.encode(), eol=",EndOfAPI")
            reply = ans.decode()
        except:
            return [-1, "socket write_readline failed"]
        else:
            pos = reply.find(",")
            return [int(reply[:pos]), reply[pos + 1 :]]

    # Send command and get return
    def __sendAndReceiveWithDecode(self, command):
        try:
            ans = self._sock.write_readline(command.encode(), eol=",EndOfAPI")
            reply = ans.decode()
        except:
            return [-1, "socket write_readline failed"]
        else:
            tokens = reply.split(",")
            results = []
            for item in tokens:
                try:
                    results.append(eval(item))
                except:
                    results.append(item)
        return results

    # GetLibraryVersion
    def GetLibraryVersion(self):
        return "XPS-Q8 Firmware Precision Platform V1.2.x"

    # Get controller motion kernel minimum and maximum time load
    def ControllerMotionKernelMinMaxTimeLoadGet(self):
        command = (
            "ControllerMotionKernelMinMaxTimeLoadGet("
            + "double *,double *,double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Reset controller motion kernel min/max time load
    def ControllerMotionKernelMinMaxTimeLoadReset(self):
        command = "ControllerMotionKernelMinMaxTimeLoadReset()"
        return self.__sendAndReceive(command)

    # Get controller motion kernel time load
    def ControllerMotionKernelTimeLoadGet(self):
        command = (
            "ControllerMotionKernelTimeLoadGet(double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Get controller corrector period and calculation time
    def ControllerRTTimeGet(self):
        command = "ControllerRTTimeGet(double *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Read slave controller status
    def ControllerSlaveStatusGet(self):
        command = "ControllerSlaveStatusGet(int *)"
        return self.__sendAndReceive(command)

    # Return the slave controller status string
    def ControllerSlaveStatusStringGet(self, SlaveControllerStatusCode):
        command = (
            "ControllerSlaveStatusStringGet("
            + str(SlaveControllerStatusCode)
            + ",char *)"
        )
        return self.__sendAndReceive(command)

    # Synchronize controller corrector ISR
    def ControllerSynchronizeCorrectorISR(self, ModeString):
        command = "ControllerSynchronizeCorrectorISR(" + ModeString + ")"
        return self.__sendAndReceive(command)

    # Get controller current status and reset the status
    def ControllerStatusGet(self):
        command = "ControllerStatusGet(int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Read controller current status
    def ControllerStatusRead(self):
        command = "ControllerStatusRead(int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Return the controller status string
    def ControllerStatusStringGet(self, ControllerStatusCode):
        command = "ControllerStatusStringGet(" + str(ControllerStatusCode) + ",char *)"
        return self.__sendAndReceive(command)

    # Return elapsed time from controller power on
    def ElapsedTimeGet(self):
        command = "ElapsedTimeGet(double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Return the error string corresponding to the error code
    def ErrorStringGet(self, ErrorCode):
        command = "ErrorStringGet(" + str(ErrorCode) + ",char *)"
        return self.__sendAndReceive(command)

    # Return firmware version
    def FirmwareVersionGet(self):
        command = "FirmwareVersionGet(char *)"
        return self.__sendAndReceive(command)

    # Execute a TCL script from a TCL file
    def TCLScriptExecute(self, TCLFileName, TaskName, ParametersList):
        command = (
            "TCLScriptExecute("
            + TCLFileName
            + ","
            + TaskName
            + ","
            + ParametersList
            + ")"
        )
        return self.__sendAndReceive(command)

    # Execute a TCL script from a TCL file and wait the end of execution to return
    def TCLScriptExecuteAndWait(self, TCLFileName, TaskName, InputParametersList):
        command = (
            "TCLScriptExecuteAndWait("
            + TCLFileName
            + ","
            + TaskName
            + ","
            + InputParametersList
            + ",char *)"
        )
        return self.__sendAndReceive(command)

    # Execute a TCL script with defined priority
    def TCLScriptExecuteWithPriority(
        self, TCLFileName, TaskName, TaskPriorityLevel, ParametersList
    ):
        command = (
            "TCLScriptExecuteWithPriority("
            + TCLFileName
            + ","
            + TaskName
            + ","
            + TaskPriorityLevel
            + ","
            + ParametersList
            + ")"
        )
        return self.__sendAndReceive(command)

    # Kill TCL Task
    def TCLScriptKill(self, TaskName):
        command = "TCLScriptKill(" + TaskName + ")"
        return self.__sendAndReceive(command)

    # Kill all TCL Tasks
    def TCLScriptKillAll(self):
        command = "TCLScriptKillAll()"
        return self.__sendAndReceive(command)

    # TimerGet :  Get a timer
    def TimerGet(self, TimerName):
        command = "TimerGet(" + TimerName + ",int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Set a timer
    def TimerSet(self, TimerName, FrequencyTicks):
        command = "TimerSet(" + TimerName + "," + str(FrequencyTicks) + ")"
        return self.__sendAndReceive(command)

    # Reboot the controller
    def Reboot(self):
        command = "Reboot()"
        return self.__sendAndReceive(command)

    # Log in
    def Login(self, Name, Password):
        command = "Login(" + Name + "," + Password + ")"
        return self.__sendAndReceive(command)

    # Close all socket beside the one used to send this command
    def CloseAllOtherSockets(self):
        command = "CloseAllOtherSockets()"
        return self.__sendAndReceive(command)

    # Return hardware date and time
    def HardwareDateAndTimeGet(self):
        command = "HardwareDateAndTimeGet(char *)"
        return self.__sendAndReceive(command)

    # Set hardware date and time
    def HardwareDateAndTimeSet(self, DateAndTime):
        command = "HardwareDateAndTimeSet(" + DateAndTime + ")"
        return self.__sendAndReceive(command)

    # ** OBSOLETE ** Add an event
    def EventAdd(
        self,
        PositionerName,
        EventName,
        EventParameter,
        ActionName,
        ActionParameter1,
        ActionParameter2,
        ActionParameter3,
    ):
        command = (
            "EventAdd("
            + PositionerName
            + ","
            + EventName
            + ","
            + EventParameter
            + ","
            + ActionName
            + ","
            + ActionParameter1
            + ","
            + ActionParameter2
            + ","
            + ActionParameter3
            + ")"
        )
        return self.__sendAndReceive(command)

    # ** OBSOLETE ** Read events and actions list
    def EventGet(self, PositionerName):
        command = "EventGet(" + PositionerName + ",char *)"
        return self.__sendAndReceive(command)

    # ** OBSOLETE ** Delete an event
    def EventRemove(self, PositionerName, EventName, EventParameter):
        command = (
            "EventRemove("
            + PositionerName
            + ","
            + EventName
            + ","
            + EventParameter
            + ")"
        )
        return self.__sendAndReceive(command)

    # ** OBSOLETE ** Wait an event
    def EventWait(self, PositionerName, EventName, EventParameter):
        command = (
            "EventWait(" + PositionerName + "," + EventName + "," + EventParameter + ")"
        )
        return self.__sendAndReceive(command)

    # Configure one or several events
    def EventExtendedConfigurationTriggerSet(
        self,
        ExtendedEventName,
        EventParameter1,
        EventParameter2,
        EventParameter3,
        EventParameter4,
    ):
        command = "EventExtendedConfigurationTriggerSet("
        for i in range(len(ExtendedEventName)):
            command += "," if i > 0 else ""
            command += str(ExtendedEventName[i]) + "," + str(EventParameter1[i]) + ","
            command += str(EventParameter2[i]) + "," + str(EventParameter3[i]) + ","
            command += str(EventParameter4[i])
        command += ")"
        return self.__sendAndReceive(command)

    # Read the event configuration
    def EventExtendedConfigurationTriggerGet(self):
        command = "EventExtendedConfigurationTriggerGet(char *)"
        return self.__sendAndReceive(command)

    # Configure one or several actions
    def EventExtendedConfigurationActionSet(
        self,
        ExtendedActionName,
        ActionParameter1,
        ActionParameter2,
        ActionParameter3,
        ActionParameter4,
    ):
        command = "EventExtendedConfigurationActionSet("
        for i in range(len(ExtendedActionName)):
            command += "," if i > 0 else ""
            command += ExtendedActionName[i] + "," + str(ActionParameter1[i]) + ","
            command += str(ActionParameter2[i]) + "," + str(ActionParameter3[i]) + ","
            command += str(ActionParameter4[i])
        command += ")"
        return self.__sendAndReceive(command)

    # Read the action configuration
    def EventExtendedConfigurationActionGet(self):
        command = "EventExtendedConfigurationActionGet(char *)"
        return self.__sendAndReceive(command)

    # Launch the last event and action configuration and return an ID
    def EventExtendedStart(self):
        command = "EventExtendedStart(int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Read all event and action configurations
    def EventExtendedAllGet(self):
        command = "EventExtendedAllGet(char *)"
        return self.__sendAndReceive(command)

    # Read the event and action configuration defined by ID
    def EventExtendedGet(self, ID):
        command = "EventExtendedGet(" + str(ID) + ",char *,char *)"
        return self.__sendAndReceive(command)

    # Remove the event and action configuration defined by ID
    def EventExtendedRemove(self, ID):
        command = "EventExtendedRemove(" + str(ID) + ")"
        return self.__sendAndReceive(command)

    # Wait events from the last event configuration
    def EventExtendedWait(self):
        command = "EventExtendedWait()"
        return self.__sendAndReceive(command)

    # Read different mnemonique type
    def GatheringConfigurationGet(self):
        command = "GatheringConfigurationGet(char *)"
        return self.__sendAndReceive(command)

    # Configuration acquisition
    def GatheringConfigurationSet(self, Type):
        command = "GatheringConfigurationSet("
        command += ",".join([a for a in Type])
        command += ")"
        return self.__sendAndReceive(command)

    # Maximum number of samples and current number during acquisition
    def GatheringCurrentNumberGet(self):
        command = "GatheringCurrentNumberGet(int *,int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Stop acquisition and save data
    def GatheringStopAndSave(self):
        command = "GatheringStopAndSave()"
        return self.__sendAndReceive(command)

    # Acquire a configured data
    def GatheringDataAcquire(self):
        command = "GatheringDataAcquire()"
        return self.__sendAndReceive(command)

    # Get a data line from gathering buffer
    def GatheringDataGet(self, IndexPoint):
        command = "GatheringDataGet(" + str(IndexPoint) + ",char *)"
        return self.__sendAndReceive(command)

    # Get multiple data lines from gathering buffer
    def GatheringDataMultipleLinesGet(self, IndexPoint, NumberOfLines):
        command = (
            "GatheringDataMultipleLinesGet("
            + str(IndexPoint)
            + ","
            + str(NumberOfLines)
            + ",char *)"
        )
        return self.__sendAndReceive(command)

    # Empty the gathered data in memory to start new gathering from scratch
    def GatheringReset(self):
        command = "GatheringReset()"
        return self.__sendAndReceive(command)

    # Start a new gathering
    def GatheringRun(self, DataNumber, Divisor):
        command = "GatheringRun(" + str(DataNumber) + "," + str(Divisor) + ")"
        return self.__sendAndReceive(command)

    # Re-start the stopped gathering to add new data
    def GatheringRunAppend(self):
        command = "GatheringRunAppend()"
        return self.__sendAndReceive(command)

    # Stop the data gathering (without saving to file)
    def GatheringStop(self):
        command = "GatheringStop()"
        return self.__sendAndReceive(command)

    # Configuration acquisition
    def GatheringExternalConfigurationSet(self, Type):
        command = "GatheringExternalConfigurationSet("
        command += ",".join([a for a in Type])
        command += ")"
        return self.__sendAndReceive(command)

    # Read different mnemonique type
    def GatheringExternalConfigurationGet(self):
        command = "GatheringExternalConfigurationGet(char *)"
        return self.__sendAndReceive(command)

    # Maximum number of samples and current number during acquisition
    def GatheringExternalCurrentNumberGet(self):
        command = "GatheringExternalCurrentNumberGet(int *,int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Get a data line from external gathering buffer
    def GatheringExternalDataGet(self, IndexPoint):
        command = "GatheringExternalDataGet(" + str(IndexPoint) + ",char *)"
        return self.__sendAndReceive(command)

    # Stop acquisition and save data
    def GatheringExternalStopAndSave(self):
        command = "GatheringExternalStopAndSave()"
        return self.__sendAndReceive(command)

    # Get global array value
    def GlobalArrayGet(self, Number):
        command = "GlobalArrayGet(" + str(Number) + ",char *)"
        return self.__sendAndReceive(command)

    # Set global array value
    def GlobalArraySet(self, Number, ValueString):
        command = "GlobalArraySet(" + str(Number) + "," + ValueString + ")"
        return self.__sendAndReceive(command)

    # Get double global array value
    def DoubleGlobalArrayGet(self, Number):
        command = "DoubleGlobalArrayGet(" + str(Number) + ",double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Set double global array value
    def DoubleGlobalArraySet(self, Number, DoubleValue):
        command = "DoubleGlobalArraySet(" + str(Number) + "," + str(DoubleValue) + ")"
        return self.__sendAndReceive(command)

    # Read analog input or analog output for one or few input
    def GPIOAnalogGet(self, GPIOName):
        command = "GPIOAnalogGet("
        command += ",".join([name + ",double *" for name in GPIOName])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Set analog output for one or few output
    def GPIOAnalogSet(self, GPIOName, AnalogOutputValue):
        command = "GPIOAnalogSet("
        command += ",".join(
            [
                GPIOName[i] + "," + str(AnalogOutputValue[i])
                for i in range(len(GPIOName))
            ]
        )
        command += ")"
        return self.__sendAndReceive(command)

    # Read analog input gain (1, 2, 4 or 8) for one or few input
    def GPIOAnalogGainGet(self, GPIOName):
        command = "GPIOAnalogGainGet("
        command += ",".join([name + ",int *" for name in GPIOName])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Set analog input gain (1, 2, 4 or 8) for one or few input
    def GPIOAnalogGainSet(self, GPIOName, AnalogInputGainValue):
        command = "GPIOAnalogGainSet("
        command += ",".join(
            [
                GPIOName[i] + "," + str(AnalogInputGainValue[i])
                for i in range(len(GPIOName))
            ]
        )
        command += ")"
        return self.__sendAndReceive(command)

    # Read digital output or digital input
    def GPIODigitalGet(self, GPIOName):
        command = "GPIODigitalGet(" + GPIOName + ",unsigned short *)"
        return self.__sendAndReceiveWithDecode(command)

    # Set Digital Output for one or few output TTL
    def GPIODigitalSet(self, GPIOName, Mask, DigitalOutputValue):
        command = (
            "GPIODigitalSet("
            + GPIOName
            + ","
            + str(Mask)
            + ","
            + str(DigitalOutputValue)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Return setpoint accelerations
    def GroupAccelerationSetpointGet(self, GroupName, nbElement):
        command = "GroupAccelerationSetpointGet(" + GroupName
        command += "".join([",double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Enable Analog Tracking mode on selected group
    def GroupAnalogTrackingModeEnable(self, GroupName, Type):
        command = "GroupAnalogTrackingModeEnable(" + GroupName + "," + Type + ")"
        return self.__sendAndReceive(command)

    # Disable Analog Tracking mode on selected group
    def GroupAnalogTrackingModeDisable(self, GroupName):
        command = "GroupAnalogTrackingModeDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Return corrector outputs
    def GroupCorrectorOutputGet(self, GroupName, nbElement):
        command = "GroupCorrectorOutputGet(" + GroupName
        command += "".join([",double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Return current following errors
    def GroupCurrentFollowingErrorGet(self, GroupName, nbElement):
        command = "GroupCurrentFollowingErrorGet(" + GroupName
        command += "".join([",double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Start home search sequence
    def GroupHomeSearch(self, GroupName):
        command = "GroupHomeSearch(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Start home search sequence and execute a displacement
    def GroupHomeSearchAndRelativeMove(self, GroupName, TargetDisplacement):
        command = "GroupHomeSearchAndRelativeMove(" + GroupName
        command += "".join(["," + str(Target) for Target in TargetDisplacement])
        command += ")"
        return self.__sendAndReceive(command)

    # Start the initialization
    def GroupInitialize(self, GroupName):
        command = "GroupInitialize(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Start the initialization with no encoder reset
    def GroupInitializeNoEncoderReset(self, GroupName):
        command = "GroupInitializeNoEncoderReset(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Start the initialization with encoder calibration
    def GroupInitializeWithEncoderCalibration(self, GroupName):
        command = "GroupInitializeWithEncoderCalibration(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Set group interlock disable
    def GroupInterlockDisable(self, GroupName):
        command = "GroupInterlockDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Set group interlock enable
    def GroupInterlockEnable(self, GroupName):
        command = "GroupInterlockEnable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Modify Jog parameters on selected group and activate the continuous move
    def GroupJogParametersSet(self, GroupName, Velocity, Acceleration):
        command = "GroupJogParametersSet(" + GroupName
        for i in range(len(Velocity)):
            command += "," + str(Velocity[i]) + "," + str(Acceleration[i])
        command += ")"
        return self.__sendAndReceive(command)

    # Get Jog parameters on selected group
    def GroupJogParametersGet(self, GroupName, nbElement):
        command = "GroupJogParametersGet(" + GroupName
        command += "".join([",double *,double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Get Jog current on selected group
    def GroupJogCurrentGet(self, GroupName, nbElement):
        command = "GroupJogCurrentGet(" + GroupName
        command += "".join([",double *,double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Enable Jog mode on selected group
    def GroupJogModeEnable(self, GroupName):
        command = "GroupJogModeEnable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Disable Jog mode on selected group
    def GroupJogModeDisable(self, GroupName):
        command = "GroupJogModeDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Kill the group
    def GroupKill(self, GroupName):
        command = "GroupKill(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Set Motion disable on selected group
    def GroupMotionDisable(self, GroupName):
        command = "GroupMotionDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Set Motion enable on selected group
    def GroupMotionEnable(self, GroupName):
        command = "GroupMotionEnable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Return group or positioner status
    def GroupMotionStatusGet(self, GroupName, nbElement):
        command = "GroupMotionStatusGet(" + GroupName
        command += "".join([",int *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Abort a move
    def GroupMoveAbort(self, GroupName):
        command = "GroupMoveAbort(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Abort quickly a move
    def GroupMoveAbortFast(self, GroupName, AccelerationMultiplier):
        command = (
            "GroupMoveAbortFast(" + GroupName + "," + str(AccelerationMultiplier) + ")"
        )
        return self.__sendAndReceive(command)

    # Do an absolute move
    def GroupMoveAbsolute(self, GroupName, TargetPositions):
        command = "GroupMoveAbsolute(" + GroupName
        command += "".join(["," + str(pos) for pos in TargetPositions])
        command += ")"
        return self.__sendAndReceive(command)

    # Do a relative move
    def GroupMoveRelative(self, GroupName, TargetDisplacements):
        command = "GroupMoveRelative(" + GroupName
        command += "".join(["," + str(pos) for pos in TargetDisplacements])
        command += ")"
        return self.__sendAndReceive(command)

    # Return corrected profiler positions
    def GroupPositionCorrectedProfilerGet(self, GroupName, PositionX, PositionY):
        command = (
            "GroupPositionCorrectedProfilerGet("
            + GroupName
            + ","
            + str(PositionX)
            + ","
            + str(PositionY)
            + ",double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # GroupPositionCurrentGet :  Return current positions
    def GroupPositionCurrentGet(self, GroupName, nbElement):
        command = "GroupPositionCurrentGet(" + GroupName
        command += "".join([",double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Return PCO raw encoder positions
    def GroupPositionPCORawEncoderGet(self, GroupName, PositionX, PositionY):
        command = (
            "GroupPositionPCORawEncoderGet("
            + GroupName
            + ","
            + str(PositionX)
            + ","
            + str(PositionY)
            + ",double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Return setpoint positions
    def GroupPositionSetpointGet(self, GroupName, nbElement):
        command = "GroupPositionSetpointGet(" + GroupName
        command += "".join([",double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Return target positions
    def GroupPositionTargetGet(self, GroupName, nbElement):
        command = "GroupPositionTargetGet(" + GroupName
        command += "".join([",double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Execute an action in referencing mode
    def GroupReferencingActionExecute(
        self, PositionerName, ReferencingAction, ReferencingSensor, ReferencingParameter
    ):
        command = (
            "GroupReferencingActionExecute("
            + PositionerName
            + ","
            + ReferencingAction
            + ","
            + ReferencingSensor
            + ","
            + str(ReferencingParameter)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Enter referencing mode
    def GroupReferencingStart(self, GroupName):
        command = "GroupReferencingStart(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Exit referencing mode
    def GroupReferencingStop(self, GroupName):
        command = "GroupReferencingStop(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Return group status
    def GroupStatusGet(self, GroupName):
        command = "GroupStatusGet(" + GroupName + ",int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Return the group status string corresponding to the group status code
    def GroupStatusStringGet(self, GroupStatusCode):
        command = "GroupStatusStringGet(" + str(GroupStatusCode) + ",char *)"
        return self.__sendAndReceive(command)

    # Return current velocities
    def GroupVelocityCurrentGet(self, GroupName, nbElement):
        command = "GroupVelocityCurrentGet(" + GroupName
        command += "".join([",double *" for i in range(nbElement)])
        command += ")"
        return self.__sendAndReceiveWithDecode(command)

    # Put all groups in 'Not initialized' state
    def KillAll(self):
        command = "KillAll()"
        return self.__sendAndReceive(command)

    # Restart the Controller
    def RestartApplication(self):
        command = "RestartApplication()"
        return self.__sendAndReceive(command)

    # Read dynamic parameters for one axe of a group for a future analog tracking position
    def PositionerAnalogTrackingPositionParametersGet(self, PositionerName):
        command = (
            "PositionerAnalogTrackingPositionParametersGet("
            + PositionerName
            + ",char *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update dynamic parameters for one axe of a group for a future analog tracking position
    def PositionerAnalogTrackingPositionParametersSet(
        self, PositionerName, GPIOName, Offset, Scale, Velocity, Acceleration
    ):
        command = (
            "PositionerAnalogTrackingPositionParametersSet("
            + PositionerName
            + ","
            + GPIOName
            + ","
            + str(Offset)
            + ","
            + str(Scale)
            + ","
            + str(Velocity)
            + ","
            + str(Acceleration)
            + ")"
        )
        return self.__sendAndReceive(command)

    #  Read dynamic parameters for one axe of a group for a future analog tracking velocity
    def PositionerAnalogTrackingVelocityParametersGet(self, PositionerName):
        command = (
            "PositionerAnalogTrackingVelocityParametersGet("
            + PositionerName
            + ",char *,double *,double *,double *,int *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update dynamic parameters for one axe of a group for a future analog tracking velocity
    def PositionerAnalogTrackingVelocityParametersSet(
        self,
        PositionerName,
        GPIOName,
        Offset,
        Scale,
        DeadBandThreshold,
        Order,
        Velocity,
        Acceleration,
    ):
        command = (
            "PositionerAnalogTrackingVelocityParametersSet("
            + PositionerName
            + ","
            + GPIOName
            + ","
            + str(Offset)
            + ","
            + str(Scale)
            + ","
            + str(DeadBandThreshold)
            + ","
            + str(Order)
            + ","
            + str(Velocity)
            + ","
            + str(Acceleration)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read backlash value and status
    def PositionerBacklashGet(self, PositionerName):
        command = "PositionerBacklashGet(" + PositionerName + ",double *,char *)"
        return self.__sendAndReceiveWithDecode(command)

    # Set backlash value
    def PositionerBacklashSet(self, PositionerName, BacklashValue):
        command = (
            "PositionerBacklashSet(" + PositionerName + "," + str(BacklashValue) + ")"
        )
        return self.__sendAndReceive(command)

    # Enable the backlash
    def PositionerBacklashEnable(self, PositionerName):
        command = "PositionerBacklashEnable(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Disable the backlash
    def PositionerBacklashDisable(self, PositionerName):
        command = "PositionerBacklashDisable(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Abort CIE08 compensated PCO mode
    def PositionerCompensatedPCOAbort(self, PositionerName):
        command = "PositionerCompensatedPCOAbort(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Get current status of CIE08 compensated PCO mode
    def PositionerCompensatedPCOCurrentStatusGet(self, PositionerName):
        command = (
            "PositionerCompensatedPCOCurrentStatusGet(" + PositionerName + ",int *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Enable CIE08 compensated PCO mode execution
    def PositionerCompensatedPCOEnable(self, PositionerName):
        command = "PositionerCompensatedPCOEnable(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Load file to CIE08 compensated PCO data buffer
    def PositionerCompensatedPCOFromFile(self, PositionerName, DataFileName):
        command = (
            "PositionerCompensatedPCOFromFile("
            + PositionerName
            + ","
            + DataFileName
            + ")"
        )
        return self.__sendAndReceive(command)

    # Load data lines to CIE08 compensated PCO data buffer
    def PositionerCompensatedPCOLoadToMemory(self, PositionerName, DataLines):
        command = (
            "PositionerCompensatedPCOLoadToMemory("
            + PositionerName
            + ","
            + DataLines
            + ")"
        )
        return self.__sendAndReceive(command)

    # Reset CIE08 compensated PCO data buffer
    def PositionerCompensatedPCOMemoryReset(self, PositionerName):
        command = "PositionerCompensatedPCOMemoryReset(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Prepare data for CIE08 compensated PCO mode
    def PositionerCompensatedPCOPrepare(
        self, PositionerName, ScanDirection, StartPosition
    ):
        command = (
            "PositionerCompensatedPCOPrepare(" + PositionerName + "," + ScanDirection
        )
        command += "".join(["," + str(pos) for pos in StartPosition])
        command += ")"
        return self.__sendAndReceive(command)

    # Set data to CIE08 compensated PCO data buffer
    def PositionerCompensatedPCOSet(self, PositionerName, Start, Stop, Distance, Width):
        command = (
            "PositionerCompensatedPCOSet("
            + PositionerName
            + ","
            + str(Start)
            + ","
            + str(Stop)
            + ","
            + str(Distance)
            + ","
            + str(Width)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read frequency compensation notch filters parameters
    def PositionerCompensationFrequencyNotchsGet(self, PositionerName):
        command = (
            "PositionerCompensationFrequencyNotchsGet("
            + PositionerName
            + ",double *,double *,double *,double *,double *,double *,double *,"
            + "double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update frequency compensation notch filters parameters
    def PositionerCompensationFrequencyNotchsSet(
        self,
        PositionerName,
        NotchFrequency1,
        NotchBandwidth1,
        NotchGain1,
        NotchFrequency2,
        NotchBandwidth2,
        NotchGain2,
        NotchFrequency3,
        NotchBandwidth3,
        NotchGain3,
    ):
        command = (
            "PositionerCompensationFrequencyNotchsSet("
            + PositionerName
            + ","
            + str(NotchFrequency1)
            + ","
            + str(NotchBandwidth1)
            + ","
            + str(NotchGain1)
            + ","
            + str(NotchFrequency2)
            + ","
            + str(NotchBandwidth2)
            + ","
            + str(NotchGain2)
            + ","
            + str(NotchFrequency3)
            + ","
            + str(NotchBandwidth3)
            + ","
            + str(NotchGain3)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read second order low-pass filter parameters
    def PositionerCompensationLowPassTwoFilterGet(self, PositionerName):
        command = (
            "PositionerCompensationLowPassTwoFilterGet(" + PositionerName + ",double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update second order low-pass filter parameters
    def PositionerCompensationLowPassTwoFilterSet(
        self, PositionerName, CutOffFrequency
    ):
        command = (
            "PositionerCompensationLowPassTwoFilterSet("
            + PositionerName
            + ","
            + str(CutOffFrequency)
            + ")"
        )
        return self.__sendAndReceive(command)

    # PositionerCompensationNotchModeFiltersGet :  Read notch mode filters parameters
    def PositionerCompensationNotchModeFiltersGet(self, PositionerName):
        command = (
            "PositionerCompensationNotchModeFiltersGet("
            + PositionerName
            + ",double *,double *,double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update notch mode filters parameters
    def PositionerCompensationNotchModeFiltersSet(
        self,
        PositionerName,
        NotchModeFr1,
        NotchModeFa1,
        NotchModeZr1,
        NotchModeZa1,
        NotchModeFr2,
        NotchModeFa2,
        NotchModeZr2,
        NotchModeZa2,
    ):
        command = (
            "PositionerCompensationNotchModeFiltersSet("
            + PositionerName
            + ","
            + str(NotchModeFr1)
            + ","
            + str(NotchModeFa1)
            + ","
            + str(NotchModeZr1)
            + ","
            + str(NotchModeZa1)
            + ","
            + str(NotchModeFr2)
            + ","
            + str(NotchModeFa2)
            + ","
            + str(NotchModeZr2)
            + ","
            + str(NotchModeZa2)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read phase correction filters parameters
    def PositionerCompensationPhaseCorrectionFiltersGet(self, PositionerName):
        command = (
            "PositionerCompensationPhaseCorrectionFiltersGet("
            + PositionerName
            + ",double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update phase correction filters parameters
    def PositionerCompensationPhaseCorrectionFiltersSet(
        self,
        PositionerName,
        PhaseCorrectionFn1,
        PhaseCorrectionFd1,
        PhaseCorrectionGain1,
        PhaseCorrectionFn2,
        PhaseCorrectionFd2,
        PhaseCorrectionGain2,
    ):
        command = (
            "PositionerCompensationPhaseCorrectionFiltersSet("
            + PositionerName
            + ","
            + str(PhaseCorrectionFn1)
            + ","
            + str(PhaseCorrectionFd1)
            + ","
            + str(PhaseCorrectionGain1)
            + ","
            + str(PhaseCorrectionFn2)
            + ","
            + str(PhaseCorrectionFd2)
            + ","
            + str(PhaseCorrectionGain2)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read spatial compensation notch filters parameters
    def PositionerCompensationSpatialPeriodicNotchsGet(self, PositionerName):
        command = (
            "PositionerCompensationSpatialPeriodicNotchsGet("
            + PositionerName
            + ",double *,double *,double *,double *,double *,double *,double *,"
            + "double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update spatial compensation notch filters parameters
    def PositionerCompensationSpatialPeriodicNotchsSet(
        self,
        PositionerName,
        SpatialNotchStep1,
        SpatialNotchBandwidth1,
        SpatialNotchGain1,
        SpatialNotchStep2,
        SpatialNotchBandwidth2,
        SpatialNotchGain2,
        SpatialNotchStep3,
        SpatialNotchBandwidth3,
        SpatialNotchGain3,
    ):
        command = (
            "PositionerCompensationSpatialPeriodicNotchsSet("
            + PositionerName
            + ","
            + str(SpatialNotchStep1)
            + ","
            + str(SpatialNotchBandwidth1)
            + ","
            + str(SpatialNotchGain1)
            + ","
            + str(SpatialNotchStep2)
            + ","
            + str(SpatialNotchBandwidth2)
            + ","
            + str(SpatialNotchGain2)
            + ","
            + str(SpatialNotchStep3)
            + ","
            + str(SpatialNotchBandwidth3)
            + ","
            + str(SpatialNotchGain3)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Update filters parameters
    def PositionerCorrectorNotchFiltersSet(
        self,
        PositionerName,
        NotchFrequency1,
        NotchBandwidth1,
        NotchGain1,
        NotchFrequency2,
        NotchBandwidth2,
        NotchGain2,
    ):
        command = (
            "PositionerCorrectorNotchFiltersSet("
            + PositionerName
            + ","
            + str(NotchFrequency1)
            + ","
            + str(NotchBandwidth1)
            + ","
            + str(NotchGain1)
            + ","
            + str(NotchFrequency2)
            + ","
            + str(NotchBandwidth2)
            + ","
            + str(NotchGain2)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read filters parameters
    def PositionerCorrectorNotchFiltersGet(self, PositionerName):
        command = (
            "PositionerCorrectorNotchFiltersGet("
            + PositionerName
            + ",double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update PIDBase parameters
    def PositionerCorrectorPIDBaseSet(
        self, PositionerName, MovingMass, StaticMass, Viscosity, Stiffness
    ):
        command = (
            "PositionerCorrectorPIDBaseSet("
            + PositionerName
            + ","
            + str(MovingMass)
            + ","
            + str(StaticMass)
            + ","
            + str(Viscosity)
            + ","
            + str(Stiffness)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read PIDBase parameters
    def PositionerCorrectorPIDBaseGet(self, PositionerName):
        command = (
            "PositionerCorrectorPIDBaseGet("
            + PositionerName
            + ",double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update corrector parameters
    def PositionerCorrectorPIDFFAccelerationSet(
        self,
        PositionerName,
        ClosedLoopStatus,
        KP,
        KI,
        KD,
        KS,
        IntegrationTime,
        DerivativeFilterCutOffFrequency,
        GKP,
        GKI,
        GKD,
        KForm,
        KFeedForwardAcceleration,
        KFeedForwardJerk,
    ):
        command = (
            "PositionerCorrectorPIDFFAccelerationSet("
            + PositionerName
            + ","
            + str(ClosedLoopStatus)
            + ","
            + str(KP)
            + ","
            + str(KI)
            + ","
            + str(KD)
            + ","
            + str(KS)
            + ","
            + str(IntegrationTime)
            + ","
            + str(DerivativeFilterCutOffFrequency)
            + ","
            + str(GKP)
            + ","
            + str(GKI)
            + ","
            + str(GKD)
            + ","
            + str(KForm)
            + ","
            + str(KFeedForwardAcceleration)
            + ","
            + str(KFeedForwardJerk)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read corrector parameters
    def PositionerCorrectorPIDFFAccelerationGet(self, PositionerName):
        command = (
            "PositionerCorrectorPIDFFAccelerationGet("
            + PositionerName
            + ",bool *,double *,double *,double *,double *,double *,double *,"
            + "double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update corrector parameters
    def PositionerCorrectorP2IDFFAccelerationSet(
        self,
        PositionerName,
        ClosedLoopStatus,
        KP,
        KI,
        KI2,
        KD,
        KS,
        IntegrationTime,
        DerivativeFilterCutOffFrequency,
        GKP,
        GKI,
        GKD,
        KForm,
        KFeedForwardAcceleration,
        KFeedForwardJerk,
        SetpointPositionDelay,
    ):
        command = (
            "PositionerCorrectorP2IDFFAccelerationSet("
            + PositionerName
            + ","
            + str(ClosedLoopStatus)
            + ","
            + str(KP)
            + ","
            + str(KI)
            + ","
            + str(KI2)
            + ","
            + str(KD)
            + ","
            + str(KS)
            + ","
            + str(IntegrationTime)
            + ","
            + str(DerivativeFilterCutOffFrequency)
            + ","
            + str(GKP)
            + ","
            + str(GKI)
            + ","
            + str(GKD)
            + ","
            + str(KForm)
            + ","
            + str(KFeedForwardAcceleration)
            + ","
            + str(KFeedForwardJerk)
            + ","
            + str(SetpointPositionDelay)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read corrector parameters
    def PositionerCorrectorP2IDFFAccelerationGet(self, PositionerName):
        command = (
            "PositionerCorrectorP2IDFFAccelerationGet("
            + PositionerName
            + ",bool *,double *,double *,double *,double *,double *,double *,double *,"
            + "double *,double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update corrector parameters
    def PositionerCorrectorPIDFFVelocitySet(
        self,
        PositionerName,
        ClosedLoopStatus,
        KP,
        KI,
        KD,
        KS,
        IntegrationTime,
        DerivativeFilterCutOffFrequency,
        GKP,
        GKI,
        GKD,
        KForm,
        KFeedForwardVelocity,
    ):
        command = (
            "PositionerCorrectorPIDFFVelocitySet("
            + PositionerName
            + ","
            + str(ClosedLoopStatus)
            + ","
            + str(KP)
            + ","
            + str(KI)
            + ","
            + str(KD)
            + ","
            + str(KS)
            + ","
            + str(IntegrationTime)
            + ","
            + str(DerivativeFilterCutOffFrequency)
            + ","
            + str(GKP)
            + ","
            + str(GKI)
            + ","
            + str(GKD)
            + ","
            + str(KForm)
            + ","
            + str(KFeedForwardVelocity)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read corrector parameters
    def PositionerCorrectorPIDFFVelocityGet(self, PositionerName):
        command = (
            "PositionerCorrectorPIDFFVelocityGet("
            + PositionerName
            + ",bool *,double *,double *,double *,double *,double *,double *,"
            + "double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update corrector parameters
    def PositionerCorrectorPIDDualFFVoltageSet(
        self,
        PositionerName,
        ClosedLoopStatus,
        KP,
        KI,
        KD,
        KS,
        IntegrationTime,
        DerivativeFilterCutOffFrequency,
        GKP,
        GKI,
        GKD,
        KForm,
        KFeedForwardVelocity,
        KFeedForwardAcceleration,
        Friction,
    ):
        command = (
            "PositionerCorrectorPIDDualFFVoltageSet("
            + PositionerName
            + ","
            + str(ClosedLoopStatus)
            + ","
            + str(KP)
            + ","
            + str(KI)
            + ","
            + str(KD)
            + ","
            + str(KS)
            + ","
            + str(IntegrationTime)
            + ","
            + str(DerivativeFilterCutOffFrequency)
            + ","
            + str(GKP)
            + ","
            + str(GKI)
            + ","
            + str(GKD)
            + ","
            + str(KForm)
            + ","
            + str(KFeedForwardVelocity)
            + ","
            + str(KFeedForwardAcceleration)
            + ","
            + str(Friction)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read corrector parameters
    def PositionerCorrectorPIDDualFFVoltageGet(self, PositionerName):
        command = (
            "PositionerCorrectorPIDDualFFVoltageGet("
            + PositionerName
            + ",bool *,double *,double *,double *,double *,double *,double *,double *,"
            + "double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update corrector parameters
    def PositionerCorrectorPIPositionSet(
        self, PositionerName, ClosedLoopStatus, KP, KI, IntegrationTime
    ):
        command = (
            "PositionerCorrectorPIPositionSet("
            + PositionerName
            + ","
            + str(ClosedLoopStatus)
            + ","
            + str(KP)
            + ","
            + str(KI)
            + ","
            + str(IntegrationTime)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read corrector parameters
    def PositionerCorrectorPIPositionGet(self, PositionerName):
        command = (
            "PositionerCorrectorPIPositionGet("
            + PositionerName
            + ",bool *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update corrector parameters
    def PositionerCorrectorSR1AccelerationSet(
        self,
        PositionerName,
        ClosedLoopStatus,
        KP,
        KI,
        KV,
        ObserverFrequency,
        CompensationGainVelocity,
        CompensationGainAcceleration,
        CompensationGainJerk,
    ):
        command = (
            "PositionerCorrectorSR1AccelerationSet("
            + PositionerName
            + ","
            + str(ClosedLoopStatus)
            + ","
            + str(KP)
            + ","
            + str(KI)
            + ","
            + str(KV)
            + ","
            + str(ObserverFrequency)
            + ","
            + str(CompensationGainVelocity)
            + ","
            + str(CompensationGainAcceleration)
            + ","
            + str(CompensationGainJerk)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read corrector parameters
    def PositionerCorrectorSR1AccelerationGet(self, PositionerName):
        command = (
            "PositionerCorrectorSR1AccelerationGet("
            + PositionerName
            + ",bool *,double *,double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update SR1 corrector observer parameters
    def PositionerCorrectorSR1ObserverAccelerationSet(
        self, PositionerName, ParameterA, ParameterB, ParameterC
    ):
        command = (
            "PositionerCorrectorSR1ObserverAccelerationSet("
            + PositionerName
            + ","
            + str(ParameterA)
            + ","
            + str(ParameterB)
            + ","
            + str(ParameterC)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read SR1 corrector observer parameters
    def PositionerCorrectorSR1ObserverAccelerationGet(self, PositionerName):
        command = (
            "PositionerCorrectorSR1ObserverAccelerationGet("
            + PositionerName
            + ",double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update SR1 corrector output acceleration offset
    def PositionerCorrectorSR1OffsetAccelerationSet(
        self, PositionerName, AccelerationOffset
    ):
        command = (
            "PositionerCorrectorSR1OffsetAccelerationSet("
            + PositionerName
            + ","
            + str(AccelerationOffset)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read SR1 corrector output acceleration offset
    def PositionerCorrectorSR1OffsetAccelerationGet(self, PositionerName):
        command = (
            "PositionerCorrectorSR1OffsetAccelerationGet("
            + PositionerName
            + ",double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Read corrector type
    def PositionerCorrectorTypeGet(self, PositionerName):
        command = "PositionerCorrectorTypeGet(" + PositionerName + ",char *)"
        return self.__sendAndReceive(command)

    # Set current velocity and acceleration cut off frequencies
    def PositionerCurrentVelocityAccelerationFiltersSet(
        self,
        PositionerName,
        CurrentVelocityCutOffFrequency,
        CurrentAccelerationCutOffFrequency,
    ):
        command = (
            "PositionerCurrentVelocityAccelerationFiltersSet("
            + PositionerName
            + ","
            + str(CurrentVelocityCutOffFrequency)
            + ","
            + str(CurrentAccelerationCutOffFrequency)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get current velocity and acceleration cut off frequencies
    def PositionerCurrentVelocityAccelerationFiltersGet(self, PositionerName):
        command = (
            "PositionerCurrentVelocityAccelerationFiltersGet("
            + PositionerName
            + ",double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Get driver filters parameters
    def PositionerDriverFiltersGet(self, PositionerName):
        command = (
            "PositionerDriverFiltersGet("
            + PositionerName
            + ",double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set driver filters parameters
    def PositionerDriverFiltersSet(
        self,
        PositionerName,
        KI,
        NotchFrequency,
        NotchBandwidth,
        NotchGain,
        LowpassFrequency,
    ):
        command = (
            "PositionerDriverFiltersSet("
            + PositionerName
            + ","
            + str(KI)
            + ","
            + str(NotchFrequency)
            + ","
            + str(NotchBandwidth)
            + ","
            + str(NotchGain)
            + ","
            + str(LowpassFrequency)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get driver stage and gage position offset
    def PositionerDriverPositionOffsetsGet(self, PositionerName):
        command = (
            "PositionerDriverPositionOffsetsGet("
            + PositionerName
            + ",double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # PositionerDriverStatusGet :  Read positioner driver status
    def PositionerDriverStatusGet(self, PositionerName):
        command = "PositionerDriverStatusGet(" + PositionerName + ",int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Return the positioner driver status string corresponding to the positioner error code
    def PositionerDriverStatusStringGet(self, PositionerDriverStatus):
        command = (
            "PositionerDriverStatusStringGet("
            + str(PositionerDriverStatus)
            + ",char *)"
        )
        return self.__sendAndReceive(command)

    # Read analog interpolated encoder amplitude values
    def PositionerEncoderAmplitudeValuesGet(self, PositionerName):
        command = (
            "PositionerEncoderAmplitudeValuesGet("
            + PositionerName
            + ",double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Read analog interpolated encoder calibration parameters
    def PositionerEncoderCalibrationParametersGet(self, PositionerName):
        command = (
            "PositionerEncoderCalibrationParametersGet("
            + PositionerName
            + ",double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # PositionerErrorGet :  Read and clear positioner error code
    def PositionerErrorGet(self, PositionerName):
        command = "PositionerErrorGet(" + PositionerName + ",int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Read only positioner error code without clear it
    def PositionerErrorRead(self, PositionerName):
        command = "PositionerErrorRead(" + PositionerName + ",int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Return the positioner status string corresponding to the positioner error code
    def PositionerErrorStringGet(self, PositionerErrorCode):
        command = "PositionerErrorStringGet(" + str(PositionerErrorCode) + ",char *)"
        return self.__sendAndReceive(command)

    # Get excitation signal mode
    def PositionerExcitationSignalGet(self, PositionerName):
        command = (
            "PositionerExcitationSignalGet("
            + PositionerName
            + ",int *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set excitation signal mode
    def PositionerExcitationSignalSet(
        self, PositionerName, Mode, Frequency, Amplitude, Time
    ):
        command = (
            "PositionerExcitationSignalSet("
            + PositionerName
            + ","
            + str(Mode)
            + ","
            + str(Frequency)
            + ","
            + str(Amplitude)
            + ","
            + str(Time)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read positioner hardware status
    def PositionerHardwareStatusGet(self, PositionerName):
        command = "PositionerHardwareStatusGet(" + PositionerName + ",int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Return the positioner hardware status string corresponding to the positioner error code
    def PositionerHardwareStatusStringGet(self, PositionerHardwareStatus):
        command = (
            "PositionerHardwareStatusStringGet("
            + str(PositionerHardwareStatus)
            + ",char *)"
        )
        return self.__sendAndReceive(command)

    # Get hard interpolator parameters
    def PositionerHardInterpolatorFactorGet(self, PositionerName):
        command = "PositionerHardInterpolatorFactorGet(" + PositionerName + ",int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Set hard interpolator parameters
    def PositionerHardInterpolatorFactorSet(self, PositionerName, InterpolationFactor):
        command = (
            "PositionerHardInterpolatorFactorSet("
            + PositionerName
            + ","
            + str(InterpolationFactor)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read external latch position
    def PositionerHardInterpolatorPositionGet(self, PositionerName):
        command = (
            "PositionerHardInterpolatorPositionGet(" + PositionerName + ",double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Return maximum velocity and acceleration of the positioner
    def PositionerMaximumVelocityAndAccelerationGet(self, PositionerName):
        command = (
            "PositionerMaximumVelocityAndAccelerationGet("
            + PositionerName
            + ",double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Read motion done parameters
    def PositionerMotionDoneGet(self, PositionerName):
        command = (
            "PositionerMotionDoneGet("
            + PositionerName
            + ",double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update motion done parameters
    def PositionerMotionDoneSet(
        self,
        PositionerName,
        PositionWindow,
        VelocityWindow,
        CheckingTime,
        MeanPeriod,
        TimeOut,
    ):
        command = (
            "PositionerMotionDoneSet("
            + PositionerName
            + ","
            + str(PositionWindow)
            + ","
            + str(VelocityWindow)
            + ","
            + str(CheckingTime)
            + ","
            + str(MeanPeriod)
            + ","
            + str(TimeOut)
            + ")"
        )
        return self.__sendAndReceive(command)

    # PositionerPositionCompareAquadBAlwaysEnable :  Enable AquadB signal in always mode
    def PositionerPositionCompareAquadBAlwaysEnable(self, PositionerName):
        command = "PositionerPositionCompareAquadBAlwaysEnable(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Read position compare AquadB windowed parameters
    def PositionerPositionCompareAquadBWindowedGet(self, PositionerName):
        command = (
            "PositionerPositionCompareAquadBWindowedGet("
            + PositionerName
            + ",double *,double *,bool *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set position compare AquadB windowed parameters
    def PositionerPositionCompareAquadBWindowedSet(
        self, PositionerName, MinimumPosition, MaximumPosition
    ):
        command = (
            "PositionerPositionCompareAquadBWindowedSet("
            + PositionerName
            + ","
            + str(MinimumPosition)
            + ","
            + str(MaximumPosition)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read position compare parameters
    def PositionerPositionCompareGet(self, PositionerName):
        command = (
            "PositionerPositionCompareGet("
            + PositionerName
            + ",double *,double *,double *,bool *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set position compare parameters
    def PositionerPositionCompareSet(
        self, PositionerName, MinimumPosition, MaximumPosition, PositionStep
    ):
        command = (
            "PositionerPositionCompareSet("
            + PositionerName
            + ","
            + str(MinimumPosition)
            + ","
            + str(MaximumPosition)
            + ","
            + str(PositionStep)
            + ")"
        )
        return self.__sendAndReceive(command)

    # PositionerPositionCompareEnable :  Enable position compare
    def PositionerPositionCompareEnable(self, PositionerName):
        command = "PositionerPositionCompareEnable(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Disable position compare
    def PositionerPositionCompareDisable(self, PositionerName):
        command = "PositionerPositionCompareDisable(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Get position compare PCO pulse parameters
    def PositionerPositionComparePulseParametersGet(self, PositionerName):
        command = (
            "PositionerPositionComparePulseParametersGet("
            + PositionerName
            + ",double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set position compare PCO pulse parameters
    def PositionerPositionComparePulseParametersSet(
        self, PositionerName, PCOPulseWidth, EncoderSettlingTime
    ):
        command = (
            "PositionerPositionComparePulseParametersSet("
            + PositionerName
            + ","
            + str(PCOPulseWidth)
            + ","
            + str(EncoderSettlingTime)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get position compare scan acceleration limit
    def PositionerPositionCompareScanAccelerationLimitGet(self, PositionerName):
        command = (
            "PositionerPositionCompareScanAccelerationLimitGet("
            + PositionerName
            + ",double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set position compare scan acceleration limit
    def PositionerPositionCompareScanAccelerationLimitSet(
        self, PositionerName, ScanAccelerationLimit
    ):
        command = (
            "PositionerPositionCompareScanAccelerationLimitSet("
            + PositionerName
            + ","
            + str(ScanAccelerationLimit)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get pre-corrector excitation signal mode
    def PositionerPreCorrectorExcitationSignalGet(self, PositionerName):
        command = (
            "PositionerPreCorrectorExcitationSignalGet("
            + PositionerName
            + ",double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set pre-corrector excitation signal mode
    def PositionerPreCorrectorExcitationSignalSet(
        self, PositionerName, Frequency, Amplitude, Time
    ):
        command = (
            "PositionerPreCorrectorExcitationSignalSet("
            + PositionerName
            + ","
            + str(Frequency)
            + ","
            + str(Amplitude)
            + ","
            + str(Time)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get the raw encoder position
    def PositionerRawEncoderPositionGet(self, PositionerName, UserEncoderPosition):
        command = (
            "PositionerRawEncoderPositionGet("
            + PositionerName
            + ","
            + str(UserEncoderPosition)
            + ",double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Return the difference between index of primary axis and secondary axis (only after homesearch)
    def PositionersEncoderIndexDifferenceGet(self, PositionerName):
        command = (
            "PositionersEncoderIndexDifferenceGet(" + PositionerName + ",double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Return adjusted displacement to get exact velocity
    def PositionerSGammaExactVelocityAjustedDisplacementGet(
        self, PositionerName, DesiredDisplacement
    ):
        command = (
            "PositionerSGammaExactVelocityAjustedDisplacementGet("
            + PositionerName
            + ","
            + str(DesiredDisplacement)
            + ",double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Read dynamic parameters for one axe of a group for a future displacement
    def PositionerSGammaParametersGet(self, PositionerName):
        command = (
            "PositionerSGammaParametersGet("
            + PositionerName
            + ",double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update dynamic parameters for one axe of a group for a future displacement
    def PositionerSGammaParametersSet(
        self, PositionerName, Velocity, Acceleration, MinimumTjerkTime, MaximumTjerkTime
    ):
        command = (
            "PositionerSGammaParametersSet("
            + PositionerName
            + ","
            + str(Velocity)
            + ","
            + str(Acceleration)
            + ","
            + str(MinimumTjerkTime)
            + ","
            + str(MaximumTjerkTime)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read SettingTime and SettlingTime
    def PositionerSGammaPreviousMotionTimesGet(self, PositionerName):
        command = (
            "PositionerSGammaPreviousMotionTimesGet("
            + PositionerName
            + ",double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Return the stage parameter
    def PositionerStageParameterGet(self, PositionerName, ParameterName):
        command = (
            "PositionerStageParameterGet("
            + PositionerName
            + ","
            + ParameterName
            + ",char *)"
        )
        return self.__sendAndReceive(command)

    # Save the stage parameter
    def PositionerStageParameterSet(
        self, PositionerName, ParameterName, ParameterValue
    ):
        command = (
            "PositionerStageParameterSet("
            + PositionerName
            + ","
            + ParameterName
            + ","
            + ParameterValue
            + ")"
        )
        return self.__sendAndReceive(command)

    # Read time flasher parameters
    def PositionerTimeFlasherGet(self, PositionerName):
        command = (
            "PositionerTimeFlasherGet("
            + PositionerName
            + ",double *,double *,double *,bool *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set time flasher parameters
    def PositionerTimeFlasherSet(
        self, PositionerName, MinimumPosition, MaximumPosition, TimeInterval
    ):
        command = (
            "PositionerTimeFlasherSet("
            + PositionerName
            + ","
            + str(MinimumPosition)
            + ","
            + str(MaximumPosition)
            + ","
            + str(TimeInterval)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Enable time flasher
    def PositionerTimeFlasherEnable(self, PositionerName):
        command = "PositionerTimeFlasherEnable(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Disable time flasher
    def PositionerTimeFlasherDisable(self, PositionerName):
        command = "PositionerTimeFlasherDisable(" + PositionerName + ")"
        return self.__sendAndReceive(command)

    # Read UserMinimumTarget and UserMaximumTarget
    def PositionerUserTravelLimitsGet(self, PositionerName):
        command = (
            "PositionerUserTravelLimitsGet(" + PositionerName + ",double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Update UserMinimumTarget and UserMaximumTarget
    def PositionerUserTravelLimitsSet(
        self, PositionerName, UserMinimumTarget, UserMaximumTarget
    ):
        command = (
            "PositionerUserTravelLimitsSet("
            + PositionerName
            + ","
            + str(UserMinimumTarget)
            + ","
            + str(UserMaximumTarget)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Set positioner warning following error limit
    def PositionerWarningFollowingErrorSet(self, PositionerName, WarningFollowingError):
        command = (
            "PositionerWarningFollowingErrorSet("
            + PositionerName
            + ","
            + str(WarningFollowingError)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get positioner warning following error limit
    def PositionerWarningFollowingErrorGet(self, PositionerName):
        command = "PositionerWarningFollowingErrorGet(" + PositionerName + ",double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Astrom & Hagglund based auto-tuning
    def PositionerCorrectorAutoTuning(self, PositionerName, TuningMode):
        command = (
            "PositionerCorrectorAutoTuning("
            + PositionerName
            + ","
            + str(TuningMode)
            + ",double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Astrom & Hagglund based auto-scaling
    def PositionerAccelerationAutoScaling(self, PositionerName):
        command = "PositionerAccelerationAutoScaling(" + PositionerName + ",double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Multiple axes PVT trajectory verification
    def MultipleAxesPVTVerification(self, GroupName, TrajectoryFileName):
        command = (
            "MultipleAxesPVTVerification(" + GroupName + "," + TrajectoryFileName + ")"
        )
        return self.__sendAndReceive(command)

    # Multiple axes PVT trajectory verification result get
    def MultipleAxesPVTVerificationResultGet(self, PositionerName):
        command = (
            "MultipleAxesPVTVerificationResultGet("
            + PositionerName
            + ",char *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Multiple axes PVT trajectory execution
    def MultipleAxesPVTExecution(self, GroupName, TrajectoryFileName, ExecutionNumber):
        command = (
            "MultipleAxesPVTExecution("
            + GroupName
            + ","
            + TrajectoryFileName
            + ","
            + str(ExecutionNumber)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Multiple axes PVT trajectory get parameters
    def MultipleAxesPVTParametersGet(self, GroupName):
        command = "MultipleAxesPVTParametersGet(" + GroupName + ",char *,int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Configure pulse output on trajectory
    def MultipleAxesPVTPulseOutputSet(
        self, GroupName, StartElement, EndElement, TimeInterval
    ):
        command = (
            "MultipleAxesPVTPulseOutputSet("
            + GroupName
            + ","
            + str(StartElement)
            + ","
            + str(EndElement)
            + ","
            + str(TimeInterval)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get pulse output on trajectory configuration
    def MultipleAxesPVTPulseOutputGet(self, GroupName):
        command = (
            "MultipleAxesPVTPulseOutputGet(" + GroupName + ",int *,int *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Multiple Axes Load PVT trajectory through function
    def MultipleAxesPVTLoadToMemory(self, GroupName, TrajectoryPart):
        command = (
            "MultipleAxesPVTLoadToMemory(" + GroupName + "," + TrajectoryPart + ")"
        )
        return self.__sendAndReceive(command)

    # Multiple Axes PVT trajectory reset in memory
    def MultipleAxesPVTResetInMemory(self, GroupName):
        command = "MultipleAxesPVTResetInMemory(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Enable the slave mode
    def SingleAxisSlaveModeEnable(self, GroupName):
        command = "SingleAxisSlaveModeEnable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Disable the slave mode
    def SingleAxisSlaveModeDisable(self, GroupName):
        command = "SingleAxisSlaveModeDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Set slave parameters
    def SingleAxisSlaveParametersSet(self, GroupName, PositionerName, Ratio):
        command = (
            "SingleAxisSlaveParametersSet("
            + GroupName
            + ","
            + PositionerName
            + ","
            + str(Ratio)
            + ")"
        )
        return self.__sendAndReceive(command)

    # SingleAxisSlaveParametersGet :  Get slave parameters
    def SingleAxisSlaveParametersGet(self, GroupName):
        command = "SingleAxisSlaveParametersGet(" + GroupName + ",char *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Set clamping disable on selected group
    def SingleAxisThetaClampDisable(self, GroupName):
        command = "SingleAxisThetaClampDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Set clamping enable on selected group
    def SingleAxisThetaClampEnable(self, GroupName):
        command = "SingleAxisThetaClampEnable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Enable the slave mode
    def SingleAxisThetaSlaveModeEnable(self, GroupName):
        command = "SingleAxisThetaSlaveModeEnable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Disable the slave mode
    def SingleAxisThetaSlaveModeDisable(self, GroupName):
        command = "SingleAxisThetaSlaveModeDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Set slave parameters
    def SingleAxisThetaSlaveParametersSet(self, GroupName, PositionerName, Ratio):
        command = (
            "SingleAxisThetaSlaveParametersSet("
            + GroupName
            + ","
            + PositionerName
            + ","
            + str(Ratio)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get slave parameters
    def SingleAxisThetaSlaveParametersGet(self, GroupName):
        command = "SingleAxisThetaSlaveParametersGet(" + GroupName + ",char *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Enable the slave mode
    def SpindleSlaveModeEnable(self, GroupName):
        command = "SpindleSlaveModeEnable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Disable the slave mode
    def SpindleSlaveModeDisable(self, GroupName):
        command = "SpindleSlaveModeDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Set slave parameters
    def SpindleSlaveParametersSet(self, GroupName, PositionerName, Ratio):
        command = (
            "SpindleSlaveParametersSet("
            + GroupName
            + ","
            + PositionerName
            + ","
            + str(Ratio)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get slave parameters
    def SpindleSlaveParametersGet(self, GroupName):
        command = "SpindleSlaveParametersGet(" + GroupName + ",char *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Modify Spin parameters on selected group and activate the continuous move
    def GroupSpinParametersSet(self, GroupName, Velocity, Acceleration):
        command = (
            "GroupSpinParametersSet("
            + GroupName
            + ","
            + str(Velocity)
            + ","
            + str(Acceleration)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get Spin parameters on selected group
    def GroupSpinParametersGet(self, GroupName):
        command = "GroupSpinParametersGet(" + GroupName + ",double *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Get Spin current on selected group
    def GroupSpinCurrentGet(self, GroupName):
        command = "GroupSpinCurrentGet(" + GroupName + ",double *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Stop Spin mode on selected group with specified acceleration
    def GroupSpinModeStop(self, GroupName, Acceleration):
        command = "GroupSpinModeStop(" + GroupName + "," + str(Acceleration) + ")"
        return self.__sendAndReceive(command)

    # XY trajectory verification
    def XYLineArcVerification(self, GroupName, TrajectoryFileName):
        command = "XYLineArcVerification(" + GroupName + "," + TrajectoryFileName + ")"
        return self.__sendAndReceive(command)

    # XY trajectory verification result get
    def XYLineArcVerificationResultGet(self, PositionerName):
        command = (
            "XYLineArcVerificationResultGet("
            + PositionerName
            + ",char *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # XY trajectory execution
    def XYLineArcExecution(
        self, GroupName, TrajectoryFileName, Velocity, Acceleration, ExecutionNumber
    ):
        command = (
            "XYLineArcExecution("
            + GroupName
            + ","
            + TrajectoryFileName
            + ","
            + str(Velocity)
            + ","
            + str(Acceleration)
            + ","
            + str(ExecutionNumber)
            + ")"
        )
        return self.__sendAndReceive(command)

    # XY trajectory get parameters
    def XYLineArcParametersGet(self, GroupName):
        command = (
            "XYLineArcParametersGet(" + GroupName + ",char *,double *,double *,int *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Configure pulse output on trajectory
    def XYLineArcPulseOutputSet(
        self, GroupName, StartLength, EndLength, PathLengthInterval
    ):
        command = (
            "XYLineArcPulseOutputSet("
            + GroupName
            + ","
            + str(StartLength)
            + ","
            + str(EndLength)
            + ","
            + str(PathLengthInterval)
            + ")"
        )
        return self.__sendAndReceive(command)

    # XYLineArcPulseOutputGet :  Get pulse output on trajectory configuration
    def XYLineArcPulseOutputGet(self, GroupName):
        command = (
            "XYLineArcPulseOutputGet(" + GroupName + ",double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # XY PVT trajectory verification
    def XYPVTVerification(self, GroupName, TrajectoryFileName):
        command = "XYPVTVerification(" + GroupName + "," + TrajectoryFileName + ")"
        return self.__sendAndReceive(command)

    # XY PVT trajectory verification result get
    def XYPVTVerificationResultGet(self, PositionerName):
        command = (
            "XYPVTVerificationResultGet("
            + PositionerName
            + ",char *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # XY PVT trajectory execution
    def XYPVTExecution(self, GroupName, TrajectoryFileName, ExecutionNumber):
        command = (
            "XYPVTExecution("
            + GroupName
            + ","
            + TrajectoryFileName
            + ","
            + str(ExecutionNumber)
            + ")"
        )
        return self.__sendAndReceive(command)

    # XY PVT trajectory get parameters
    def XYPVTParametersGet(self, GroupName):
        command = "XYPVTParametersGet(" + GroupName + ",char *,int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Configure pulse output on trajectory
    def XYPVTPulseOutputSet(self, GroupName, StartElement, EndElement, TimeInterval):
        command = (
            "XYPVTPulseOutputSet("
            + GroupName
            + ","
            + str(StartElement)
            + ","
            + str(EndElement)
            + ","
            + str(TimeInterval)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get pulse output on trajectory configuration
    def XYPVTPulseOutputGet(self, GroupName):
        command = "XYPVTPulseOutputGet(" + GroupName + ",int *,int *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # XY Load PVT trajectory through function
    def XYPVTLoadToMemory(self, GroupName, TrajectoryPart):
        command = "XYPVTLoadToMemory(" + GroupName + "," + TrajectoryPart + ")"
        return self.__sendAndReceive(command)

    # XY PVT trajectory reset in memory
    def XYPVTResetInMemory(self, GroupName):
        command = "XYPVTResetInMemory(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Return corrected profiler positions
    def XYZGroupPositionCorrectedProfilerGet(
        self, GroupName, PositionX, PositionY, PositionZ
    ):
        command = (
            "XYZGroupPositionCorrectedProfilerGet("
            + GroupName
            + ","
            + str(PositionX)
            + ","
            + str(PositionY)
            + ","
            + str(PositionZ)
            + ",double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Return PCO raw encoder positions
    def XYZGroupPositionPCORawEncoderGet(
        self, GroupName, PositionX, PositionY, PositionZ
    ):
        command = (
            "XYZGroupPositionPCORawEncoderGet("
            + GroupName
            + ","
            + str(PositionX)
            + ","
            + str(PositionY)
            + ","
            + str(PositionZ)
            + ",double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # XYZ trajectory verifivation
    def XYZSplineVerification(self, GroupName, TrajectoryFileName):
        command = "XYZSplineVerification(" + GroupName + "," + TrajectoryFileName + ")"
        return self.__sendAndReceive(command)

    # XYZ trajectory verification result get
    def XYZSplineVerificationResultGet(self, PositionerName):
        command = (
            "XYZSplineVerificationResultGet("
            + PositionerName
            + ",char *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # XYZ trajectory execution
    def XYZSplineExecution(self, GroupName, TrajectoryFileName, Velocity, Acceleration):
        command = (
            "XYZSplineExecution("
            + GroupName
            + ","
            + TrajectoryFileName
            + ","
            + str(Velocity)
            + ","
            + str(Acceleration)
            + ")"
        )
        return self.__sendAndReceive(command)

    # XYZ trajectory get parameters
    def XYZSplineParametersGet(self, GroupName):
        command = (
            "XYZSplineParametersGet(" + GroupName + ",char *,double *,double *,int *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # TZ PVT trajectory verification
    def TZPVTVerification(self, GroupName, TrajectoryFileName):
        command = "TZPVTVerification(" + GroupName + "," + TrajectoryFileName + ")"
        return self.__sendAndReceive(command)

    # TZ PVT trajectory verification result get
    def TZPVTVerificationResultGet(self, PositionerName):
        command = (
            "TZPVTVerificationResultGet("
            + PositionerName
            + ",char *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # TZ PVT trajectory execution
    def TZPVTExecution(self, GroupName, TrajectoryFileName, ExecutionNumber):
        command = (
            "TZPVTExecution("
            + GroupName
            + ","
            + TrajectoryFileName
            + ","
            + str(ExecutionNumber)
            + ")"
        )
        return self.__sendAndReceive(command)

    # TZ PVT trajectory get parameters
    def TZPVTParametersGet(self, GroupName):
        command = "TZPVTParametersGet(" + GroupName + ",char *,int *)"
        return self.__sendAndReceiveWithDecode(command)

    # Configure pulse output on trajectory
    def TZPVTPulseOutputSet(self, GroupName, StartElement, EndElement, TimeInterval):
        command = (
            "TZPVTPulseOutputSet("
            + GroupName
            + ","
            + str(StartElement)
            + ","
            + str(EndElement)
            + ","
            + str(TimeInterval)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get pulse output on trajectory configuration
    def TZPVTPulseOutputGet(self, GroupName):
        command = "TZPVTPulseOutputGet(" + GroupName + ",int *,int *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # TZ Load PVT trajectory through function
    def TZPVTLoadToMemory(self, GroupName, TrajectoryPart):
        command = "TZPVTLoadToMemory(" + GroupName + "," + TrajectoryPart + ")"
        return self.__sendAndReceive(command)

    # TZ PVT trajectory reset in memory
    def TZPVTResetInMemory(self, GroupName):
        command = "TZPVTResetInMemory(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Enable the focus mode
    def TZFocusModeEnable(self, GroupName):
        command = "TZFocusModeEnable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Disable the focus mode
    def TZFocusModeDisable(self, GroupName):
        command = "TZFocusModeDisable(" + GroupName + ")"
        return self.__sendAndReceive(command)

    # Get user maximum ZZZ target difference for tracking control
    def TZTrackingUserMaximumZZZTargetDifferenceGet(self, GroupName):
        command = (
            "TZTrackingUserMaximumZZZTargetDifferenceGet(" + GroupName + ",double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set user maximum ZZZ target difference for tracking control
    def TZTrackingUserMaximumZZZTargetDifferenceSet(
        self, GroupName, UserMaximumZZZTargetDifference
    ):
        command = (
            "TZTrackingUserMaximumZZZTargetDifferenceSet("
            + GroupName
            + ","
            + str(UserMaximumZZZTargetDifference)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Set user maximum ZZZ target difference for tracking control
    def FocusProcessSocketReserve(self):
        command = "FocusProcessSocketReserve()"
        return self.__sendAndReceive(command)

    # Set user maximum ZZZ target difference for tracking control
    def FocusProcessSocketFree(self):
        command = "FocusProcessSocketFree()"
        return self.__sendAndReceive(command)

    # Get soft (user defined) motor output DAC offsets
    def PositionerMotorOutputOffsetGet(self, PositionerName):
        command = (
            "PositionerMotorOutputOffsetGet("
            + PositionerName
            + ",double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Set soft (user defined) motor output DAC offsets
    def PositionerMotorOutputOffsetSet(
        self, PositionerName, PrimaryDAC1, PrimaryDAC2, SecondaryDAC1, SecondaryDAC2
    ):
        command = (
            "PositionerMotorOutputOffsetSet("
            + PositionerName
            + ","
            + str(PrimaryDAC1)
            + ","
            + str(PrimaryDAC2)
            + ","
            + str(SecondaryDAC1)
            + ","
            + str(SecondaryDAC2)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get raw encoder positions for single axis theta encoder
    def SingleAxisThetaPositionRawGet(self, GroupName):
        command = (
            "SingleAxisThetaPositionRawGet("
            + GroupName
            + ",double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Get raw encoder positions for single axis theta encoder
    def EEPROMCIESet(self, CardNumber, ReferenceString):
        command = "EEPROMCIESet(" + str(CardNumber) + "," + ReferenceString + ")"
        return self.__sendAndReceive(command)

    # Get raw encoder positions for single axis theta encoder
    def EEPROMDACOffsetCIESet(self, PlugNumber, DAC1Offset, DAC2Offset):
        command = (
            "EEPROMDACOffsetCIESet("
            + str(PlugNumber)
            + ","
            + str(DAC1Offset)
            + ","
            + str(DAC2Offset)
            + ")"
        )
        return self.__sendAndReceive(command)

    # Get raw encoder positions for single axis theta encoder
    def EEPROMDriverSet(self, PlugNumber, ReferenceString):
        command = "EEPROMDriverSet(" + str(PlugNumber) + "," + ReferenceString + ")"
        return self.__sendAndReceive(command)

    # Get raw encoder positions for single axis theta encoder
    def EEPROMINTSet(self, CardNumber, ReferenceString):
        command = "EEPROMINTSet(" + str(CardNumber) + "," + ReferenceString + ")"
        return self.__sendAndReceive(command)

    # Get raw encoder positions for single axis theta encoder
    def CPUCoreAndBoardSupplyVoltagesGet(self):
        command = (
            "CPUCoreAndBoardSupplyVoltagesGet("
            "double *,double *,double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Get raw encoder positions for single axis theta encoder
    def CPUTemperatureAndFanSpeedGet(self):
        command = "CPUTemperatureAndFanSpeedGet(double *,double *)"
        return self.__sendAndReceiveWithDecode(command)

    # Action list
    def ActionListGet(self):
        command = "ActionListGet(char *)"
        return self.__sendAndReceive(command)

    # Action extended list
    def ActionExtendedListGet(self):
        command = "ActionExtendedListGet(char *)"
        return self.__sendAndReceive(command)

    # API method list
    def APIExtendedListGet(self):
        command = "APIExtendedListGet(char *)"
        return self.__sendAndReceive(command)

    # API method list without extended API
    def APIListGet(self):
        command = "APIListGet(char *)"
        return self.__sendAndReceive(command)

    # Controller status list
    def ControllerStatusListGet(self):
        command = "ControllerStatusListGet(char *)"
        return self.__sendAndReceive(command)

    # Get the error list
    def ErrorListGet(self):
        command = "ErrorListGet(char *)"
        return self.__sendAndReceive(command)

    # Get general event list
    def EventListGet(self):
        command = "EventListGet(char *)"
        return self.__sendAndReceive(command)

    # Gathering type list
    def GatheringListGet(self):
        command = "GatheringListGet(char *)"
        return self.__sendAndReceive(command)

    # Gathering type extended list
    def GatheringExtendedListGet(self):
        command = "GatheringExtendedListGet(char *)"
        return self.__sendAndReceive(command)

    # External Gathering type list
    def GatheringExternalListGet(self):
        command = "GatheringExternalListGet(char *)"
        return self.__sendAndReceive(command)

    # Group status list
    def GroupStatusListGet(self):
        command = "GroupStatusListGet(char *)"
        return self.__sendAndReceive(command)

    # Internal hardware list
    def HardwareInternalListGet(self):
        command = "HardwareInternalListGet(char *)"
        return self.__sendAndReceive(command)

    # Smart hardware
    def HardwareDriverAndStageGet(self, PlugNumber):
        command = "HardwareDriverAndStageGet(" + str(PlugNumber) + ",char *,char *)"
        return self.__sendAndReceive(command)

    # ObjectsListGet :  Group name and positioner name
    def ObjectsListGet(self):
        command = "ObjectsListGet(char *)"
        return self.__sendAndReceive(command)

    # PositionerErrorListGet :  Positioner error list
    def PositionerErrorListGet(self):
        command = "PositionerErrorListGet(char *)"
        return self.__sendAndReceive(command)

    # Positioner hardware status list
    def PositionerHardwareStatusListGet(self):
        command = "PositionerHardwareStatusListGet(char *)"
        return self.__sendAndReceive(command)

    # Positioner driver status list
    def PositionerDriverStatusListGet(self):
        command = "PositionerDriverStatusListGet(char *)"
        return self.__sendAndReceive(command)

    # Get referencing action list
    def ReferencingActionListGet(self):
        command = "ReferencingActionListGet(char *)"
        return self.__sendAndReceive(command)

    # Get referencing sensor list
    def ReferencingSensorListGet(self):
        command = "ReferencingSensorListGet(char *)"
        return self.__sendAndReceive(command)

    # Return UserDatas values
    def GatheringUserDatasGet(self):
        command = (
            "GatheringUserDatasGet("
            + "double *,double *,double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Get controller motion kernel min/max periods
    def ControllerMotionKernelPeriodMinMaxGet(self):
        command = (
            "ControllerMotionKernelPeriodMinMaxGet("
            + "double *,double *,double *,double *,double *,double *)"
        )
        return self.__sendAndReceiveWithDecode(command)

    # Reset controller motion kernel min/max periods
    def ControllerMotionKernelPeriodMinMaxReset(self):
        command = "ControllerMotionKernelPeriodMinMaxReset()"
        return self.__sendAndReceive(command)

    # Get sockets current status
    def SocketsStatusGet(self):
        command = "SocketsStatusGet(char *)"
        return self.__sendAndReceive(command)

    # Test TCP/IP transfer
    def TestTCP(self, InputString):
        command = "TestTCP(" + InputString + ",char *)"
        return self.__sendAndReceive(command)

    # Execute an optional module
    def OptionalModuleExecute(self, ModuleFileName):
        command = "OptionalModuleExecute(" + ModuleFileName + ")"
        return self.__sendAndReceive(command)

    # Kill an optional module
    def OptionalModuleKill(self, TaskName):
        command = "OptionalModuleKill(" + TaskName + ")"
        return self.__sendAndReceive(command)
