import ACS

class Device(ACS.Device):

    def __init__ (self, address):
    
        super().__init__(address)
        
        self.about = self.About(self)
        self.control = self.Control(self)
        self.description = self.Description(self)
        self.move = self.Move(self)
        self.network = self.Network(self)
        self.res = self.Res(self)
        self.rotcomp = self.Rotcomp(self)
        self.rtin = self.Rtin(self)
        self.rtout = self.Rtout(self)
        self.status = self.Status(self)
        self.system = self.System(self)
        self.update = self.Update(self)
    
    class About():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.system.about"
            
        def getInstalledPackages(self):
            """
            Get list of packages installed on the device
            -------
            Returns
            -------
            value_string0: string: Comma separated list of packages
            """
            response = self.device.request(self.interface_name + ".getInstalledPackages")
            return response['result'][0]
    


    
        def getPackageLicense(self, pckg):
            """
            Get the license for a specific package
            
            Parameters
            ----------
            pckg:  string: Package name
            Returns
            -------
            value_string0: string: License for this package
            """
            response = self.device.request(self.interface_name + ".getPackageLicense", [pckg])
            return response['result'][0]
    


    
    
    class Control():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.amc.control"
            
        def MultiAxisPositioning(self, set1, set2, set3, target1, target2, target3):
            """
            Simultaneously set 3 axes positions
            and get positions to minimize network latency
            
            Parameters
            ----------
            set1:  axis1 otherwise pos1 target is ignored
            set2:  axis2 otherwise pos2 target is ignored
            set3:  axis3 otherwise pos3 target is ignored
            target1:  target position of axis 1
            target2:  target position of axis 2
            target3:  target position of axis 3
            Returns
            -------
            errNo: errNo
            ref1: ref1 Status
            ref2: ref2 Status
            ref3: ref3 Status
            refpos1: refpos1
            refpos2: refpos2
            refpos3: refpos3
            pos1: pos1
            pos2: pos2
            pos3: pos3
            """
            response = self.device.request(self.interface_name + ".MultiAxisPositioning", [set1, set2, set3, target1, target2, target3])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2], response['result'][3], response['result'][4], response['result'][5], response['result'][6], response['result'][7], response['result'][8], response['result'][9]
    


    
        def getActorName(self, axis):
            """
            Read the current actory name selected
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            actor_name: actor_name
            """
            response = self.device.request(self.interface_name + ".getActorName", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getActorParameters(self, axis):
            """
            Retrieves the actual valid actors parameters
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            actorname: actorname
            actor_type: actor_type
            freq_max: freq_max
            amp_max: amp_max
            sensor_dir: sensor_dir (boolean)
            actor_dir: actor_dir (boolean)
            sensorPitchPerTurn: sensorPitchPerTurn
            sensitivity: sensitivity
            stepsize: stepsize
            """
            response = self.device.request(self.interface_name + ".getActorParameters", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2], response['result'][3], response['result'][4], response['result'][5], response['result'][6], response['result'][7], response['result'][8], response['result'][9]
    


    
        def getActorParametersActorName(self, axis):
            """
            Control the actors parameter: actor name
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            actorname: actorname
            """
            response = self.device.request(self.interface_name + ".getActorParametersActorName", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getActorParametersByParamName(self, axis, paramname):
            """
            Get the actors parameters from their name ( search through an internal parameter list)
            
            Parameters
            ----------
            axis:  [0|1|2]
            paramname:  possible parameter:  actortype (0 to 2), fmax (> freqmin < freqmax controller),amax (> 0 < ampmax controller)
          sensor_dir(boolean), pitchofgrading(>0), sensitivity  ( 1 to 15) , stepsize (>0)
            Returns
            -------
            errNo: errNo
            value_string1: string of the value of the parameter selected
            """
            response = self.device.request(self.interface_name + ".getActorParametersByParamName", [axis, paramname])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getActorType(self, axis):
            """
            Read the current actory type selected
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            actor_type: actor_type  -- 0 = linear , 1 = goniometer,	2 = rotator
            """
            response = self.device.request(self.interface_name + ".getActorType", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlAmplitude(self, axis):
            """
            Retrieves  the amplitude of the actuator signal in mV.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            amplitude: amplitude  define in mV
            """
            response = self.device.request(self.interface_name + ".getControlAmplitude", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlAmplitudeInV(self, axis):
            """
            Retrieves  the amplitude of the actuator signal in V.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            amplitude: amplitude  define in V
            """
            response = self.device.request(self.interface_name + ".getControlAmplitudeInV", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlAutoReset(self, axis):
            """
            Retrieves if Resets the position for every time the reference position is detected.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean
            """
            response = self.device.request(self.interface_name + ".getControlAutoReset", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlFixOutputVoltage(self, axis):
            """
            Get the DC level on the output positioner if DC level is enabled
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            amplitude_mv: amplitude_mv  define in mV
            """
            response = self.device.request(self.interface_name + ".getControlFixOutputVoltage", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlFrequency(self, axis):
            """
            Get the frequency of the actuator signal in mHz
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            frequency: frequency define in mHz
            """
            response = self.device.request(self.interface_name + ".getControlFrequency", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlFrequencyInHz(self, axis):
            """
            Get the frequency of the actuator signal in Hz
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            frequency: frequency define in Hz
            """
            response = self.device.request(self.interface_name + ".getControlFrequencyInHz", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlMove(self, axis):
            """
            Retrieves the approach status of the actor to the target position
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            enable: enable boolean true: approach enabled , false: approach disabled
            """
            response = self.device.request(self.interface_name + ".getControlMove", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlOutput(self, axis):
            """
            Retrieves if output power is active on the drives
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean power status (true = VP100/VN100 enabled,false = VP100/VN100 disabled)
            """
            response = self.device.request(self.interface_name + ".getControlOutput", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlReferenceAutoUpdate(self, axis):
            """
            When set, every time the reference marking is hit the reference position will be updated.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value: value
            """
            response = self.device.request(self.interface_name + ".getControlReferenceAutoUpdate", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlTargetRange(self, axis):
            """
            Retrieves  the range around the target position in which the flag target status become active.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            targetrange: targetrange define in nm
            """
            response = self.device.request(self.interface_name + ".getControlTargetRange", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlValuesLTRTCC(self, axis):
            """
            Get  the amplitude and frequency values for both LT, RT and CC Modes
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            ampLT: ampLT
            ampRT: ampRT
            ampCC: ampCC
            freqLT: freqLT
            freqRT: freqRT
            freqCC: freqCC
            rangeLT: rangeLT
            rangeRT: rangeRT
            rangeCC: rangeCC
            """
            response = self.device.request(self.interface_name + ".getControlValuesLTRTCC", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2], response['result'][3], response['result'][4], response['result'][5], response['result'][6], response['result'][7], response['result'][8], response['result'][9]
    


    
        def getReferencePosition(self, axis):
            """
            Retrieves the reference position ( See getStatusReference for determining the validity)
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            referenceposition: referenceposition : For linear type actors the position is defined in nm for goniometer an rotator type actors it is µ°.
            """
            response = self.device.request(self.interface_name + ".getReferencePosition", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getReferencePositionInmm(self, axis):
            """
            Retrieves the reference position in mm( See getStatusReference for determining the validity)
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            referenceposition: referenceposition : For linear type actors the position is defined in mm for goniometer an rotator type actors it is °.
            """
            response = self.device.request(self.interface_name + ".getReferencePositionInmm", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getSensorEnabled(self, axis):
            """
            Get sensot power supply status
            
            Parameters
            ----------
            axis:  [1|2|3]
            Returns
            -------
            errNo: errNo
            value: value
            """
            response = self.device.request(self.interface_name + ".getSensorEnabled", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusMovingAllAxes(self):
            """
            Get Status of all axes
            -------
            Returns
            -------
            errNo: errNo
            moving1: moving1
            moving2: moving2
            moving3: moving3
            """
            response = self.device.request(self.interface_name + ".getStatusMovingAllAxes")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2], response['result'][3]
    


    
        def getTemperatureMode(self, axis):
            """
            Get the operational temperature mode of the device
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            the: the temperature mode of the positioner [0|1|2]
            """
            response = self.device.request(self.interface_name + ".getTemperatureMode", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def setActorParameters(self, axis, actorname, actortype, fmax, amax, sensor_dir, actor_dir, pitchofgrading, sensitivity, stepsize):
            """
            Set all the actors parameters
            
            Parameters
            ----------
            axis:  [0|1|2]
            actorname:  string
            actortype: 
            fmax: 
            amax: 
            sensor_dir: 
            actor_dir: 
            pitchofgrading: 
            sensitivity: 
            stepsize: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setActorParameters", [axis, actorname, actortype, fmax, amax, sensor_dir, actor_dir, pitchofgrading, sensitivity, stepsize])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setActorParametersActorName(self, axis, actorname):
            """
            Control the actors parameter: actor name
            
            Parameters
            ----------
            axis:  [0|1|2]
            actorname: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setActorParametersActorName", [axis, actorname])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setActorParametersByName(self, axis, actorname):
            """
            Control the actors parameters of an actor based on name ( search through an internal list)
            
            Parameters
            ----------
            axis:  [0|1|2]
            actorname: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setActorParametersByName", [axis, actorname])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setActorParametersByParamName(self, axis, paramname, paramvalue):
            """
            Control the actors parameters of an actor parameter  name ( search through an internal parameter list)  for integer paramaters
            
            Parameters
            ----------
            axis:  [0|1|2]
            paramname:  possible parameter:  actortype (0 to 2), fmax (> freqmin < freqmax controller),amax (> 0 < ampmax controller)
          sensor_dir(boolean), pitchofgrading(>0), sensitivity  ( 1 to 15) , stepsize (>0)
            paramvalue: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setActorParametersByParamName", [axis, paramname, paramvalue])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setActorParametersByParamNameBoolean(self, axis, paramname, paramvalue):
            """
            Control the actors parameters of an actor parameter  name ( search through an internal parameter list)  for boolean paramater
            
            Parameters
            ----------
            axis:  [0|1|2]
            paramname:  possible parameter: sensor_dir(boolean), actor_dir(boolean)
            paramvalue:  boolean
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setActorParametersByParamNameBoolean", [axis, paramname, paramvalue])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setActorParametersJson(self, axis, json_dict):
            """
            Select and override a positioner out of the Current default list only override given parameters set others default
            
            Parameters
            ----------
            axis:  [0|1|2]
            json_dict:  dict with override params
            Returns
            -------
            errNo: errNo errorCode
            """
            response = self.device.request(self.interface_name + ".setActorParametersJson", [axis, json_dict])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlAmplitude(self, axis, amplitude):
            """
            Set  the amplitude of the actuator signal in mV
            
            Parameters
            ----------
            axis:  [0|1|2]
            amplitude:  define in mV
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlAmplitude", [axis, amplitude])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlAmplitudeInV(self, axis, amplitudeinV):
            """
            Set  the amplitude of the actuator signal in V
            
            Parameters
            ----------
            axis:  [0|1|2]
            amplitudeinV:  define in V
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlAmplitudeInV", [axis, amplitudeinV])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlAutoReset(self, axis, enable):
            """
            Set if Resets the position for every time the reference position is detected.
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable:  boolean
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlAutoReset", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlFixOutputVoltage(self, axis, amplitude_mv):
            """
            Set the DC level on the output ( must perform  applyControlFixOutputVoltage to apply on the positioner)
            
            Parameters
            ----------
            axis:  [0|1|2]
            amplitude_mv:   define in mV
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlFixOutputVoltage", [axis, amplitude_mv])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlFrequency(self, axis, frequency):
            """
            Set  the frequency of the actuator signal in mHz
             Note: Approximate the slewrate of the motion controller  according to Input Frequency
            
            Parameters
            ----------
            axis:  [0|1|2]
            frequency:  define in  mHz
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlFrequency", [axis, frequency])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlFrequencyInHz(self, axis, frequencyinHz):
            """
            Set  the frequency of the actuator signal in Hz
            
            Parameters
            ----------
            axis:  [0|1|2]
            frequencyinHz:  define in  Hz
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlFrequencyInHz", [axis, frequencyinHz])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlMove(self, axis, enable):
            """
            Controls the approach of the actor to the target position
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable:  boolean true: eanble the approach , false: disable the approach
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlMove", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlOutput(self, axis, enable):
            """
            Controls the output power (VPP/VNN) of the selected axis.
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable:  boolean  true: enable drives, false: disable drives
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlOutput", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlReferenceAutoUpdate(self, axis, enable):
            """
            When set, every time the reference marking is hit the reference position will be updated.
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable:  boolean
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlReferenceAutoUpdate", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlTargetRange(self, axis, range):
            """
            Set  the range around the target position in which the flag target status become active.
            
            Parameters
            ----------
            axis:  [0|1|2]
            range:  define in nm
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlTargetRange", [axis, range])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlValuesLTRTCC(self, axis, amplitude, frequency, targetRange, mode):
            """
            Set  the amplitude and frequency values for LT, RT and CC Modes
            
            Parameters
            ----------
            axis:  [0|1|2]
            amplitude:  define in mV
            frequency:  frequency in Hz
            targetRange:  range
            mode:  mode
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlValuesLTRTCC", [axis, amplitude, frequency, targetRange, mode])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setEoTDetectBehaviour(self, axis, reso, distanceInEoT, distanceOutEoT, NbrofEoTtoTrigger):
            """
            Change Eot Settings to detect EOT  on the Fly .
            
            Parameters
            ----------
            axis:  [0|1|2]
            reso:  resolution of to change the timoueout of when  the EoTDetect function is called . reso * 100ms
            distanceInEoT:   Distancein nm  between two call of the  EoTDetect function   under which a EoT trigger will activated
            distanceOutEoT:   Distance in nm between two call of the  EoTDetect function   above a EoT will be deactivated
            NbrofEoTtoTrigger:  nbr of time EoT trigger needs to be activated prior to really activated the EoT Flag
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setEoTDetectBehaviour", [axis, reso, distanceInEoT, distanceOutEoT, NbrofEoTtoTrigger])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setReset(self, axis):
            """
            Resets the actual position to zero and marks the reference position as invalid.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setReset", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setReturnBool(self):
            """
            Returns true, can be used for testing
            -------
            Returns
            -------
            errNo: errNo
            value: value, always returns true
            """
            response = self.device.request(self.interface_name + ".setReturnBool")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def setSaveParams(self):
            """
            NOT Implemented
            -------
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setSaveParams")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setSensorEnabled(self, axis, value):
            """
            Set sensor power supply status
            
            Parameters
            ----------
            axis:  [1|2|3]
            value: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setSensorEnabled", [axis, value])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setTemperatureMode(self, axis, mode):
            """
            Set  the amplitude of the actuator signal using the LT, RT presets
            
            Parameters
            ----------
            axis:  [0|1|2]
            mode:  [0|1] (0=LT, 1=RT)
            Returns
            -------
            errNo: errNo
            amplitude: amplitude
            frequency: frequency
            targetrange: targetrange
            """
            response = self.device.request(self.interface_name + ".setTemperatureMode", [axis, mode])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2], response['result'][3]
    


    
    
    class Description():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.amc.description"
            
        def checkChassisNbr(self):
            """
            Get Chassis and Slot Number, only works when AMC is within a Rack
            -------
            Returns
            -------
            errNo: errNo errorCode
            slotNbr: slotNbr
            chassisNbr: chassisNbr
            """
            response = self.device.request(self.interface_name + ".checkChassisNbr")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2]
    


    
        def getActorParamNamesList(self):
            """
            dynamically get all Parameter-Names used in PositionerConf
            -------
            Returns
            -------
            errNo: errNo errorCode
            PositionerParamsList: PositionerParamsList
            """
            response = self.device.request(self.interface_name + ".getActorParamNamesList")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getDeviceType(self):
            """
            Get the Device type name as a string
            -------
            Returns
            -------
            errNo: errNo
            devicetype: devicetype Device name (AMC100, AMC300) with attached feature ( AMC100\\NUM, AMC100\\NUM\\PRO)
            """
            response = self.device.request(self.interface_name + ".getDeviceType")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getFeatures(self):
            """
            Return all features available, including descriptions
            -------
            Returns
            -------
            errNo: errNo
            features: features string of available features and their status
            """
            response = self.device.request(self.interface_name + ".getFeatures")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getFeaturesActivated(self):
            """
            Get the activated features and return as a string
            -------
            Returns
            -------
            errNo: errNo
            features: features activated on device [NUM, PRO]
            """
            response = self.device.request(self.interface_name + ".getFeaturesActivated")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getPositionersList(self):
            """
            dynamically get all the Positioners available in the setofconfigurationlist.lua file
            -------
            Returns
            -------
            errNo: errNo
            PositionersList: PositionersList
            """
            response = self.device.request(self.interface_name + ".getPositionersList")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getSensorBoard(self, axis):
            """
            Return which board has been detected on the PCie express extension
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            boardinfo: boardinfo  0: OL, 1: NUM, 2: RES
            """
            response = self.device.request(self.interface_name + ".getSensorBoard", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getWebServices(self):
            """
            Return all features available, including descriptions
            -------
            Returns
            -------
            errNo: errNo
            available: available webservices and their status
            """
            response = self.device.request(self.interface_name + ".getWebServices")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
    
    class Move():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.amc.move"
            
        def getControlContinuousBkwd(self, axis):
            """
            Check continuous movement in backward direction.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean true if movement backward is active , false otherwise
            """
            response = self.device.request(self.interface_name + ".getControlContinuousBkwd", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlContinuousFwd(self, axis):
            """
            Check continuous movement in forward direction
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean true if movement Fwd is active , false otherwise
            """
            response = self.device.request(self.interface_name + ".getControlContinuousFwd", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlEotOutputDeactive(self, axis):
            """
            Get the actual  status action on  EOT (End Of Travel)
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean If true, the output of the axis will be deactivated on positive EOT detection.
            """
            response = self.device.request(self.interface_name + ".getControlEotOutputDeactive", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlTargetPosition(self, axis):
            """
            Get the actual target position
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            position: position defined in nm for goniometer an rotator type actors it is µ°.
            """
            response = self.device.request(self.interface_name + ".getControlTargetPosition", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getGroundAxis(self, axis):
            """
            Pull axis piezo drive to GND actively
            only in AMC300
            
            Parameters
            ----------
            axis:  montion controler axis [0|1|2]
            Returns
            -------
            errNo: errNo 0 or error
            grounded: grounded true or false
            """
            response = self.device.request(self.interface_name + ".getGroundAxis", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getGroundAxisAutoOnTarget(self, axis):
            """
            Pull axis piezo drive to GND if positioner is in ground target range
            ONLY DUMMY RIGHT NOW
            only in AMC300
            
            Parameters
            ----------
            axis:  montion controler axis [0|1|2]
            Returns
            -------
            errNo: errNo 0 or error
            value: value true or false
            """
            response = self.device.request(self.interface_name + ".getGroundAxisAutoOnTarget", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getGroundTargetRange(self, axis):
            """
            Retrieves the range around the target position in which the auto grounding becomes active.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            targetrange: targetrange define in nm
            """
            response = self.device.request(self.interface_name + ".getGroundTargetRange", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getNSteps(self, axis):
            """
            Get the number of step that is applied for SetNsteps
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            nbrstep: nbrstep
            """
            response = self.device.request(self.interface_name + ".getNSteps", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getPosition(self, axis):
            """
            Get the actual  position of the actor
             The axis on the web application are indexed from 1 to 3
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            position: position defined in nm for goniometer an rotator type actors it is µ°.
            """
            response = self.device.request(self.interface_name + ".getPosition", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getPositionInmm(self, axis):
            """
            Get the actual  position of the actor
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            position: position defined in mm
            """
            response = self.device.request(self.interface_name + ".getPositionInmm", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def performNSteps(self, axis, backward):
            """
            Perform the OL command for N steps
            
            Parameters
            ----------
            axis:  [0|1|2]
            backward:  Selects the desired direction. False triggers a forward step, true a backward step
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".performNSteps", [axis, backward])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlContinuousBkwd(self, axis, enable):
            """
            Controls continuous movement in backward direction
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable:  If enabled a present movement in the opposite direction is stopped. The parameter "false" stops all movement of the axis regardless its direction
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlContinuousBkwd", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlContinuousFwd(self, axis, enable):
            """
            Controls continuous movement in forward direction
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable:  If enabled a present movement in the opposite direction is stopped. The parameter "false" stops all movement of the axis regardless its direction.
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlContinuousFwd", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlEotOutputDeactive(self, axis, enable):
            """
            Defines the behavior of the output on EOT (End Of Travel)
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable:  boolean  If enabled, the output of the axis will be deactivated on positive EOT detection.
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlEotOutputDeactive", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlTargetPosition(self, axis, target):
            """
            Set the Target position
            careful: the FPGA has a register of 48 bit in picometers, so the maximum positon in nm is now 2**47/1000
            
            Parameters
            ----------
            axis:  [0|1|2]
            target:  absolute position : For linear type actors the position is defined in nm for goniometer an rotator type actors it is µ°.
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlTargetPosition", [axis, target])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setGroundAxis(self, axis, enabled):
            """
            Pull axis piezo drive to GND actively
            only in AMC300
            this is used in MIC-Mode
            
            Parameters
            ----------
            axis:  motion controler axis [0|1|2]
            enabled:  true or false
            Returns
            -------
            errNo: errNo 0 or error
            """
            response = self.device.request(self.interface_name + ".setGroundAxis", [axis, enabled])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setGroundAxisAutoOnTarget(self, axis, enabled):
            """
            Pull axis piezo drive to GND if positioner is in ground target range
            ONLY DUMMY RIGHT NOW
            only in AMC300
            this is used in MIC-Mode
            
            Parameters
            ----------
            axis:  montion controler axis [0|1|2]
            enabled:  true or false
            Returns
            -------
            errNo: errNo 0 or error
            """
            response = self.device.request(self.interface_name + ".setGroundAxisAutoOnTarget", [axis, enabled])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setGroundTargetRange(self, axis, range):
            """
            Set  the range around the target position in which the auto grounding becomes active.
            
            Parameters
            ----------
            axis:  [0|1|2]
            range:  define in nm
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setGroundTargetRange", [axis, range])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setNSteps(self, axis, backward, step):
            """
            Set N steps and perform the OL command for N steps
            
            Parameters
            ----------
            axis:  [0|1|2]
            backward:  Selects the desired direction. False triggers a forward step, true a backward step
            step:  number of step
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setNSteps", [axis, backward, step])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def writeNSteps(self, axis, step):
            """
            set N steps
            
            Parameters
            ----------
            axis:  [0|1|2]
            step:  number of step
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".writeNSteps", [axis, step])
            errNo = self.device.handleError(response)
            return errNo
    


    
    
    class Network():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.system.network"
            
        def apply(self):
            """
            Apply temporary IP configuration and load it
            -------
            Returns
            -------
            Error: Error code
            """
            response = self.device.request(self.interface_name + ".apply")
            return response['result'][0]
    


    
        def discard(self):
            """
            Discard temporary IP configuration
            -------
            Returns
            -------
            Error: Error code
            """
            response = self.device.request(self.interface_name + ".discard")
            return response['result'][0]
    


    
        def getDefaultGateway(self):
            """
            Get the default gateway of the device
            -------
            Returns
            -------
            Default: Default gateway
            """
            response = self.device.request(self.interface_name + ".getDefaultGateway")
            return response['result'][0]
    


    
        def getDnsResolver(self, priority):
            """
            Get the DNS resolver
            
            Parameters
            ----------
            priority:  of DNS resolver (Usually: 0 = Default, 1 = Backup)
            Returns
            -------
            IP: IP address of DNS resolver
            """
            response = self.device.request(self.interface_name + ".getDnsResolver", [priority])
            return response['result'][0]
    


    
        def getEnableDhcpClient(self):
            """
            Get the state of DHCP client
            -------
            Returns
            -------
            value_boolean0: boolean: true = DHCP client enable, false = DHCP client disable
            """
            response = self.device.request(self.interface_name + ".getEnableDhcpClient")
            return response['result'][0]
    


    
        def getEnableDhcpServer(self):
            """
            Get the state of DHCP server
            -------
            Returns
            -------
            value_boolean0: boolean: true = DHCP server enable, false = DHCP server disable
            """
            response = self.device.request(self.interface_name + ".getEnableDhcpServer")
            return response['result'][0]
    


    
        def getIpAddress(self):
            """
            Get the IP address of the device
            -------
            Returns
            -------
            IP: IP address as string
            """
            response = self.device.request(self.interface_name + ".getIpAddress")
            return response['result'][0]
    


    
        def getProxyServer(self):
            """
            Get the proxy settings of the devide
            -------
            Returns
            -------
            Proxy: Proxy Server String, empty for no proxy
            """
            response = self.device.request(self.interface_name + ".getProxyServer")
            return response['result'][0]
    


    
        def getSubnetMask(self):
            """
            Get the subnet mask of the device
            -------
            Returns
            -------
            Subnet: Subnet mask as string
            """
            response = self.device.request(self.interface_name + ".getSubnetMask")
            return response['result'][0]
    


    
        def setDefaultGateway(self, gateway):
            """
            Set the default gateway of the device
            
            Parameters
            ----------
            gateway:  Default gateway as string
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setDefaultGateway", [gateway])
            return response['result'][0]
    


    
        def setDnsResolver(self, priority, resolver):
            """
            Set the DNS resolver
            
            Parameters
            ----------
            priority:  of DNS resolver (Usually: 0 = Default, 1 = Backup)
            resolver:  The resolver's IP address as string
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setDnsResolver", [priority, resolver])
            return response['result'][0]
    


    
        def setEnableDhcpClient(self, enable):
            """
            Enable or disable DHCP client
            
            Parameters
            ----------
            enable:  boolean: true = enable DHCP client, false = disable DHCP client
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setEnableDhcpClient", [enable])
            return response['result'][0]
    


    
        def setEnableDhcpServer(self, enable):
            """
            Enable or disable DHCP server
            
            Parameters
            ----------
            enable:  boolean: true = enable DHCP server, false = disable DHCP server
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setEnableDhcpServer", [enable])
            return response['result'][0]
    


    
        def setIpAddress(self, address):
            """
            Set the IP address of the device
            
            Parameters
            ----------
            address:  IP address as string
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setIpAddress", [address])
            return response['result'][0]
    


    
        def setProxyServer(self, proxyServer):
            """
            Set the proxy server of the device
            
            Parameters
            ----------
            proxyServer:  Proxy Server Setting as string
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setProxyServer", [proxyServer])
            return response['result'][0]
    


    
        def setSubnetMask(self, netmask):
            """
            Set the subnet mask of the device
            
            Parameters
            ----------
            netmask:  Subnet mask as string
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setSubnetMask", [netmask])
            return response['result'][0]
    


    
        def testInternetConnection(self):
            """
            Tests if the internet connection works (i.e.
            -------
            Returns
            -------
            successfull: successfull
            """
            response = self.device.request(self.interface_name + ".testInternetConnection")
            return response['result'][0]
    


    
        def verify(self):
            """
            Verify that temporary IP configuration is correct
            -------
            Returns
            -------
            Error: Error code
            """
            response = self.device.request(self.interface_name + ".verify")
            return response['result'][0]
    


    
    
    class Res():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.amc.res"
            
        def getChainGain(self, axis):
            """
            Get chain gain
            
            Parameters
            ----------
            axis:  number of axis
            Returns
            -------
            errNo: errNo
            gaincoeff: gaincoeff
            """
            response = self.device.request(self.interface_name + ".getChainGain", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getLutSn(self, axis):
            """
            get the identifier of the loaded lookuptable (will be empty if disabled)
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_string1: string : identifier
            """
            response = self.device.request(self.interface_name + ".getLutSn", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getMagnitudeAll(self, axis):
            """
            Get magnitude value at different states of the FPGA signal chain
            
            Parameters
            ----------
            axis:  axis [0|1|2]
            Returns
            -------
            errNo: errNo
            mag_a: mag_a range 0 .. 2^23
            mag_b: mag_b range 0 .. 2^23
            mag_norm: mag_norm magnitude normalized range 0 .. 2^23
            mag_cor: mag_cor magnitude corrected after linearization range 0 .. 2^23
            """
            response = self.device.request(self.interface_name + ".getMagnitudeAll", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2], response['result'][3], response['result'][4]
    


    
        def getMagnitudePermille(self, axis):
            """
            Get normalized magnitude and corrected magnitude in %
            
            Parameters
            ----------
            axis:  axis [0|1|2]
            Returns
            -------
            errNo: errNo
            mag_norm: mag_norm magnitude normalized  range in % [0...100%]
            mag_cor: mag_cor magnitude after linearization  range in % [0...100%]
            """
            response = self.device.request(self.interface_name + ".getMagnitudePermille", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2]
    


    
        def getMode(self):
            """
            Get mode of RES application
            -------
            Returns
            -------
            errNo: errNo
            mode: mode
            """
            response = self.device.request(self.interface_name + ".getMode")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getMuteOut(self, axis):
            """
            Get Codec output if it's muted or not
            
            Parameters
            ----------
            axis:  number of axis
            Returns
            -------
            errNo: errNo
            mutestatus: mutestatus boolean: true: output is mute, false: output is unmute
            """
            response = self.device.request(self.interface_name + ".getMuteOut", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def setChainGain(self, axis, gainconfig):
            """
            Set signal chain gain to control overall power
            
            Parameters
            ----------
            axis:  number of axis
            gainconfig:  0: 0dB ( power 600mVpkpk^2/R), 1 : -10 dB , 2 : -15 dB , 3 : -20 dB
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setChainGain", [axis, gainconfig])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setConfigurationFile(self, axis, content):
            """
            Load configuration file which either contains JSON parameters or the LUT file itself (as legacy support)
            
            Parameters
            ----------
            axis:  [0|1|2]
            content:   1k * 24 bit string or JSON File
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setConfigurationFile", [axis, content])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setCtrlDecimation(self, decim1, decim2, force):
            """
            for study change Configure the FPGA decimation factor of 1st and 2nd stage for TAP signal
            
            Parameters
            ----------
            decim1:  (range 2 .. 255)
            decim2:  (range 1 .. 255)
            force:  boolean true: force to write even though phase lock operation are not meet, false: only allow correct configuration
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setCtrlDecimation", [decim1, decim2, force])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setCtrlFilter(self, size1, size2, force):
            """
            for study change Configure the FPGA filter of 1st and 2nd stage for TAP signal
            
            Parameters
            ----------
            size1:  filter size 1st filter: 0 => 2, 1 => 4, 2 => 8, 3 => 16, 4 => 32, 5 => 64, 6 => 128, 7 => 256, 8 => bypass
            size2:  filter size 2nd filter: 0 => 2, 1 => 4, 2 => 8, 3 => 16, 4 => 32, 5 => 64, 6 => 128, 7 => 256, 8 => bypass
            force:  boolean true: force to write even though phase lock operation are not mt, false: only allow correct configuration
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setCtrlFilter", [size1, size2, force])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setGlobalEnable(self, enable):
            """
            control   Wave generator and decimation
            
            Parameters
            ----------
            enable:  0 disables wave generator and decimation, set 1 to synchronously start both.
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setGlobalEnable", [enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setLinTable(self, axis, content):
            """
            Load linearization table in compatible ANC350v5 format to be interpolated to 1024 values
            
            Parameters
            ----------
            axis:  [0|1|2]
            content:   1k * 24 bit string
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setLinTable", [axis, content])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setLinearization(self, enable):
            """
            Control if linearization is enabled or not
            
            Parameters
            ----------
            enable:  boolean ( true: enable linearization)
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setLinearization", [enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setLoadFactor(self, value):
            """
            Control Load Factor behavior
            
            Parameters
            ----------
            value:   0: do not load automatically, 1: load automatically every second 2: load the norm factor once
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setLoadFactor", [value])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setMode(self, mode):
            """
            Get mode of RES application
            
            Parameters
            ----------
            mode:  1: Individual mode with triple ortho frequency rejection method 2: Mic Mode with dual frequency  rejection method
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setMode", [mode])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setMuteOut(self, axis, enable):
            """
            Set Codec output to mute it or enable it
            
            Parameters
            ----------
            axis:  number of axis
            enable:  boolean true: mute output, false: unmute output
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setMuteOut", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setPositionRange(self, axis, range):
            """
            Set the range of the positioner
            
            Parameters
            ----------
            axis:  number of axis
            range:  nm , largest value supported is 548 mm
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setPositionRange", [axis, range])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRecordSignal(self, axis, timems):
            """
            Records all signals from register magnitude TAP and REF and COR and NORM   and position for verification purpose
            the files are log into the folder /opt/ecs/scripts/lua/log/ with respective name for each value and axis
            the function record a value every ms
            
            Parameters
            ----------
            axis:  [0|1|2|3(all)]
            timems:  time in ms as record time max 60000 ms
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRecordSignal", [axis, timems])
            errNo = self.device.handleError(response)
            return errNo
    


    
    
    class Rotcomp():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.amc.rotcomp"
            
        def getControlTargetRanges(self):
            """
            Checks if all three axis are in target range.
            -------
            Returns
            -------
            errNo: int32
            Error code, if there was an error, otherwise 0 for ok
            in_target_range: boolean
            true all three axes are in target range, false at least one axis is not in target range
            """
            response = self.device.request(self.interface_name + ".getControlTargetRanges")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getEnabled(self):
            """
            Gets the enabled status of the rotation compensation
            -------
            Returns
            -------
            errNo: int32
            Error code, if there was an error, otherwise 0 for ok
            enabled: boolean
            true Rotation compensation is enabled, false Rotation compensation is disabled
            """
            response = self.device.request(self.interface_name + ".getEnabled")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getLUT(self):
            """
            Gets the LUT file as JSON string
            -------
            Returns
            -------
            errNo: int32
            Error code, if there was an error, otherwise 0 for ok
            lut: string
            JSON string of the LUT file for the rotation compensation
            """
            response = self.device.request(self.interface_name + ".getLUT")
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def setEnabled(self):
            """
            Enables and disables the rotation compensation
            -------
            Returns
            -------
            errNo: int32
            Error code, if there was an error, otherwise 0 for ok
            """
            response = self.device.request(self.interface_name + ".setEnabled")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setLUT(self):
            """
            Sets the LUT file from a JSON string
            -------
            Returns
            -------
            errNo: int32
            Error code, if there was an error, otherwise 0 for ok
            """
            response = self.device.request(self.interface_name + ".setLUT")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def updateOffsets(self):
            """
            Updates the start offsets of the axes
            -------
            Returns
            -------
            errNo: int32
            Error code, if there was an error, otherwise 0 for ok
            """
            response = self.device.request(self.interface_name + ".updateOffsets")
            errNo = self.device.handleError(response)
            return errNo
    


    
    
    class Rtin():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.amc.rtin"
            
        def apply(self):
            """
            Apply all realtime input function
            -------
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".apply")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyRealTimeInChangePerPulse(self, axis):
            """
            Apply setRealTimeInChangePerPulse
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyRealTimeInChangePerPulse", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyRealTimeInFeedbackLoopMode(self, axis):
            """
            Apply setRealTimeInFeedbackLoopMode
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyRealTimeInFeedbackLoopMode", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyRealTimeInHsslClk(self, axis):
            """
            Apply setRealTimeInHsslClk
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyRealTimeInHsslClk", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyRealTimeInHsslGap(self, axis):
            """
            Apply setRealTimeInHsslGap
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyRealTimeInHsslGap", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyRealTimeInHsslHigh(self, axis):
            """
            Apply setRealTimeInHsslHigh
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyRealTimeInHsslHigh", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyRealTimeInHsslLow(self, axis):
            """
            Apply setRealTimeInHsslLow
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyRealTimeInHsslLow", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyRealTimeInMode(self, axis):
            """
            Apply setRealTimeInMode
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyRealTimeInMode", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyRealTimeInStepsPerPulse(self, axis):
            """
            Apply setRealTimeInStepsPerPulse
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyRealTimeInStepsPerPulse", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def discard(self):
            """
            Discard all values beting set and not yet applieds
            -------
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".discard")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def getControlAQuadBIn(self, axis):
            """
            check if  AQuadB input is enabled.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean
            """
            response = self.device.request(self.interface_name + ".getControlAQuadBIn", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlAQuadBInResolution(self, axis, tempvalue):
            """
            Get the resolution of AquadB
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            resolution: resolution ion nm
            """
            response = self.device.request(self.interface_name + ".getControlAQuadBInResolution", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlMoveGPIO(self, axis):
            """
            This function gets the status for real time input on the selected axis in closed-loop mode.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            enable: enable boolean true: approach enabled , false: approach disabled
            """
            response = self.device.request(self.interface_name + ".getControlMoveGPIO", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getRealTimeInChangePerPulse(self, axis, tempvalue):
            """
            Get the change in pm per pulse  of the realtime input when trigger and stepper mod is used
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean     if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            resolution: resolution to be added in current pos in nm
            """
            response = self.device.request(self.interface_name + ".getRealTimeInChangePerPulse", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getRealTimeInFeedbackLoopMode(self, axis, tempvalue):
            """
            Get if the realtime function must operate in close loop operation or open loop operation
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean    if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            mode: mode 0: open loop, 1 : close-loop
            """
            response = self.device.request(self.interface_name + ".getRealTimeInFeedbackLoopMode", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getRealTimeInHsslClk(self, axis, tempvalue):
            """
            Get the HSSL clock
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean     if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            clk: clk  clock  is given in nanoseconds
            """
            response = self.device.request(self.interface_name + ".getRealTimeInHsslClk", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getRealTimeInHsslGap(self, axis, tempvalue):
            """
            Get the HSSL Gap
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean     if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            gap: gap indicates the gap between the end of the HSSL word  and the beginning of the next HSSL word. The unit of G is HSSL clock cycles.
            """
            response = self.device.request(self.interface_name + ".getRealTimeInHsslGap", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getRealTimeInHsslHigh(self, axis, tempvalue):
            """
            Get the higher part of the HSSL resolution
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean    if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            highresolution: highresolution
            """
            response = self.device.request(self.interface_name + ".getRealTimeInHsslHigh", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getRealTimeInHsslLow(self, axis, tempvalue):
            """
            Get the lower part of the HSSL resolution
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean   if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            lowresolution: lowresolution
            """
            response = self.device.request(self.interface_name + ".getRealTimeInHsslLow", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getRealTimeInMode(self, axis, tempvalue):
            """
            Get the RealTime Input Mode
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean   if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            mode: mode see `RT_IN_MODES`
            """
            response = self.device.request(self.interface_name + ".getRealTimeInMode", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getRealTimeInStepsPerPulse(self, axis, tempvalue):
            """
            Get the change in step per pulse  of the realtime input when trigger and stepper mode is used
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean     if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            steps: steps number of steps to applied
            """
            response = self.device.request(self.interface_name + ".getRealTimeInStepsPerPulse", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def setControlAQuadBIn(self, axis, enable):
            """
            AQuadB input  enable.
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlAQuadBIn", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlAQuadBInResolution(self, axis, resolution):
            """
            Set the resolution of AquadB
            
            Parameters
            ----------
            axis:  [0|1|2]
            resolution:  ion nm
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlAQuadBInResolution", [axis, resolution])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlMoveGPIO(self, axis, enable):
            """
            This function sets the status for real time input on the selected axis in closed-loop mode.
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable:  boolean true: eanble the approach , false: disable the approach
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlMoveGPIO", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRealTimeInChangePerPulse(self, axis, resolution):
            """
            Set the change in pm per pulse  of the realtime input when trigger and stepper mod is used
            only used in closed loop operation
            
            Parameters
            ----------
            axis:  [0|1|2]
            resolution:  to be added in current pos in nm
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRealTimeInChangePerPulse", [axis, resolution])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRealTimeInFeedbackLoopMode(self, axis, mode):
            """
            Set if the realtime function must operate in close loop operation or open loop operation
            
            Parameters
            ----------
            axis:  [0|1|2]
            mode:  0: open loop, 1 : close-loop
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRealTimeInFeedbackLoopMode", [axis, mode])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRealTimeInHsslClk(self, axis, hssl_clk):
            """
            Set the HSSL clock
            
            Parameters
            ----------
            axis:  [0|1|2]
            hssl_clk:   clock  is given in nanoseconds: N = data/40 - 1
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRealTimeInHsslClk", [axis, hssl_clk])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRealTimeInHsslGap(self, axis, hssl_gap):
            """
            Set the HSSL Gaps
            
            Parameters
            ----------
            axis:  [0|1|2]
            hssl_gap:  indicates the gap between the end of the HSSL word and the beginning of the next HSSL word in units of HSSL clock cycles.
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRealTimeInHsslGap", [axis, hssl_gap])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRealTimeInHsslHigh(self, axis, resohigh):
            """
            Set the higher part of the HSSL resolution
            
            Parameters
            ----------
            axis:  [0|1|2]
            resohigh: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRealTimeInHsslHigh", [axis, resohigh])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRealTimeInHsslLow(self, axis, resolow):
            """
            Set the lower part of the HSSL resolution
            
            Parameters
            ----------
            axis:  [0|1|2]
            resolow: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRealTimeInHsslLow", [axis, resolow])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRealTimeInMode(self, axis, mode):
            """
            Set the setRealTime Input Mode
            
            Parameters
            ----------
            axis:  [0|1|2]
            mode:  see `RT_IN_MODES` @see realtime
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRealTimeInMode", [axis, mode])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setRealTimeInStepsPerPulse(self, axis, steps):
            """
            Set the change in step per pulse  of the realtime input when trigger and stepper mode is used
            only used in open loop operation
            
            Parameters
            ----------
            axis:  [0|1|2]
            steps:  number of steps to applied
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setRealTimeInStepsPerPulse", [axis, steps])
            errNo = self.device.handleError(response)
            return errNo
    


    
    
    class Rtout():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.amc.rtout"
            
        def apply(self):
            """
            Apply for all rtout function
            -------
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".apply")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applyAxis(self, axis):
            """
            Apply for rtout function of specific axis
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applyAxis", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def applySignalMode(self):
            """
            Apply value set by setSignalMode
            -------
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".applySignalMode")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def discard(self):
            """
            Discard all rtout value set by the set function(not applied yet)
            -------
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".discard")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def discardAxis(self, axis):
            """
            Discard rtout value of specific axis set by the set function(not applied yet)
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".discardAxis", [axis])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def discardSignalMode(self):
            """
            Discard value set by setSignalMode
            -------
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".discardSignalMode")
            errNo = self.device.handleError(response)
            return errNo
    


    
        def getControlAQuadBOut(self, axis, tempvalue):
            """
            Retrieves the if AquadB is enbled on RT OUT
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean    if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean
            """
            response = self.device.request(self.interface_name + ".getControlAQuadBOut", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlAQuadBOutClock(self, axis, tempvalue):
            """
            Get the AquadB clock
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean  if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            clock_in_ns: clock_in_ns Clock in multiples of 20ns. Minimum 2 (40ns), maximum 65535 (1,310700ms)
            """
            response = self.device.request(self.interface_name + ".getControlAQuadBOutClock", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getControlAQuadBOutResolution(self, axis, tempvalue):
            """
            Reading the AquadB resolution
            
            Parameters
            ----------
            axis:  [0|1|2]
            tempvalue:  boolean    if true get the tempory value ( from the set function)
            Returns
            -------
            errNo: errNo
            resolution: resolution Defines in nm
            """
            response = self.device.request(self.interface_name + ".getControlAQuadBOutResolution", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getSignalMode(self, tempvalue):
            """
            Control the real time output signal type
            
            Parameters
            ----------
            tempvalue: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".getSignalMode", [tempvalue])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def getTriggerConfig(self, axis, tempvalue):
            """
            Get the real time output trigger config
            
            Parameters
            ----------
            axis: 
            tempvalue:  boolean
            Returns
            -------
            errNo: errNo
            hih: hih
            low: low
            eps: eps
            mode: mode
            """
            response = self.device.request(self.interface_name + ".getTriggerConfig", [axis, tempvalue])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1], response['result'][2], response['result'][3], response['result'][4]
    


    
        def setControlAQuadBOut(self, axis, enable):
            """
            Set the if AquadB is enbled on RT OUT
            DEPRECATED: use setMode for enabling AQuadB
            
            Parameters
            ----------
            axis:  [0|1|2]
            enable: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlAQuadBOut", [axis, enable])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlAQuadBOutClock(self, axis, clock):
            """
            Set the AquadB clock
            
            Parameters
            ----------
            axis:  [0|1|2]
            clock:  Clock in multiples of 20ns. Minimum 2 (40ns), maximum 65535 (1,310700ms)
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlAQuadBOutClock", [axis, clock])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setControlAQuadBOutResolution(self, axis, resolution):
            """
            Set the AquadB resolution
            
            Parameters
            ----------
            axis:  [0|1|2]
            resolution:  Defines in nm
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setControlAQuadBOutResolution", [axis, resolution])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setSignalMode(self, mode):
            """
            Control the real time output signal type
            
            Parameters
            ----------
            mode:  mode : 0 TTL, mode : 1 LVDS
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setSignalMode", [mode])
            errNo = self.device.handleError(response)
            return errNo
    


    
        def setTriggerConfig(self, axis, hig, low, eps, mode):
            """
            Control the real time output trigger config
            
            Parameters
            ----------
            axis: 
            hig: 
            low: 
            eps: 
            mode: 
            Returns
            -------
            errNo: errNo
            """
            response = self.device.request(self.interface_name + ".setTriggerConfig", [axis, hig, low, eps, mode])
            errNo = self.device.handleError(response)
            return errNo
    


    
    
    class Status():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.amc.status"
            
        def getCombinedStatus(self, axis):
            """
            Get the combined status of a positioner axis and return the status as a string (to be used in the MOVE SW)
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_string1: string "MOVING","IN TARGET RANGE", "END OF TRAVEL", "READY", "PENDING", "UNKNOWN STATE"
            """
            response = self.device.request(self.interface_name + ".getCombinedStatus", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getFullCombinedStatus(self, axis):
            """
            Get the full combined status of a positioner axis and return the status as a string (to be used in the Webapplication)
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_string1: string "MOVING","IN TARGET RANGE", "END OF TRAVEL", "READY", "PENDING", "UNKNOWN STATE"
            """
            response = self.device.request(self.interface_name + ".getFullCombinedStatus", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getOlStatus(self, axis):
            """
            Get the Feedback status of the positioner
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            sensorstatus: sensorstatus 0: Positioner NUM is connected and has a sensor, 1: Positioner is connected but detected as OL, 2: positioner not connected , 3: RES positioner not connected
            """
            response = self.device.request(self.interface_name + ".getOlStatus", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getOlStatusStr(self, axis):
            """
            Get the Feedback status of the positioner and return the status as a string
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_string1: string "NUM positioner connected","OL positioner connected", "No positioner connected"
            """
            response = self.device.request(self.interface_name + ".getOlStatusStr", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusConnected(self, axis):
            """
            Retrieves the connected status.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean If true, the actor is connected
            """
            response = self.device.request(self.interface_name + ".getStatusConnected", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusEot(self, axis):
            """
            Retrieves the status of the end of travel (EOT) detection in backward direction or in forward direction.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean true= detected$
            """
            response = self.device.request(self.interface_name + ".getStatusEot", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusEotBkwd(self, axis):
            """
            Retrieves the status of the end of travel (EOT) detection in backward direction.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean true= detected
            """
            response = self.device.request(self.interface_name + ".getStatusEotBkwd", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusEotFwd(self, axis):
            """
            Retrieves the status of the end of travel (EOT) detection in forward direction.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean true= detected
            """
            response = self.device.request(self.interface_name + ".getStatusEotFwd", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusError(self, axis):
            """
            NOT Implemented
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            FEATURE_NOT_AVAILABLE: FEATURE_NOT_AVAILABLE
            """
            response = self.device.request(self.interface_name + ".getStatusError", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusFlash(self, axis):
            """
            NOT Implemented
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            FEATURE_NOT_AVAILABLE: FEATURE_NOT_AVAILABLE
            """
            response = self.device.request(self.interface_name + ".getStatusFlash", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusMoving(self, axis):
            """
            Retrieves the status of the output stage.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            status: status 0: Idle ,1 : Moving means the actor is actively driven by the output stage either for approaching or continous/single stepping and the output is active.
              2 : Pending means the output stage is driving but the output is deactivated i.e. by EOT or ECC_controlOutput.
            """
            response = self.device.request(self.interface_name + ".getStatusMoving", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusReference(self, axis):
            """
            Retrieves the status of the reference position.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean true= valid, false = not valid
            """
            response = self.device.request(self.interface_name + ".getStatusReference", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
        def getStatusTargetRange(self, axis):
            """
            Retrieves the target status.
            
            Parameters
            ----------
            axis:  [0|1|2]
            Returns
            -------
            errNo: errNo
            value_boolean1: boolean (true = within the target range, false: not ion the target range)
            """
            response = self.device.request(self.interface_name + ".getStatusTargetRange", [axis])
            errNo = self.device.handleError(response)
            return errNo, response['result'][1]
    


    
    
    class System():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.system"
            
        def apply(self):
            """
            Apply temporary system configuration
            -------
            Returns
            -------
            Error: Error code
            """
            response = self.device.request(self.interface_name + ".apply")
            return response['result'][0]
    


    
        def errorNumberToRecommendation(self, language, errNbr):
            """
            Get a recommendation for the error code
            
            Parameters
            ----------
            language:  integer: Language code
            errNbr:   interger: Error code to translate
            Returns
            -------
            value_string0: string: Error recommendation (currently returning an int = 0 until we have recommendations)
            """
            response = self.device.request(self.interface_name + ".errorNumberToRecommendation", [language, errNbr])
            return response['result'][0]
    


    
        def errorNumberToString(self, language, errNbr):
            """
            Get a description of an error code
            
            Parameters
            ----------
            language:  integer: Language code
            errNbr:   interger: Error code to translate
            Returns
            -------
            value_string0: string: Error description
            """
            response = self.device.request(self.interface_name + ".errorNumberToString", [language, errNbr])
            return response['result'][0]
    


    
        def factoryReset(self):
            """
            Reset the device to factory configuration on next boot
            -------
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".factoryReset")
            return response['result'][0]
    


    
        def getDeviceName(self):
            """
            Get the actual device name
            -------
            Returns
            -------
            value_string0: string: actual device name
            """
            response = self.device.request(self.interface_name + ".getDeviceName")
            return response['result'][0]
    


    
        def getFirmwareVersion(self):
            """
            Get the firmware version of the system
            -------
            Returns
            -------
            value_string0: string: The firmware version
            """
            response = self.device.request(self.interface_name + ".getFirmwareVersion")
            return response['result'][0]
    


    
        def getFluxCode(self):
            """
            Get the flux code of the system
            -------
            Returns
            -------
            value_string0: string: flux code
            """
            response = self.device.request(self.interface_name + ".getFluxCode")
            return response['result'][0]
    


    
        def getHostname(self):
            """
            Return device hostname
            -------
            Returns
            -------
            available: available
            """
            response = self.device.request(self.interface_name + ".getHostname")
            return response['result'][0]
    


    
        def getMacAddress(self):
            """
            Get the mac address of the system
            -------
            Returns
            -------
            value_string0: string: Mac address of the system
            """
            response = self.device.request(self.interface_name + ".getMacAddress")
            return response['result'][0]
    


    
        def getSerialNumber(self):
            """
            Get the serial number of the system
            -------
            Returns
            -------
            value_string0: string: Serial number
            """
            response = self.device.request(self.interface_name + ".getSerialNumber")
            return response['result'][0]
    


    
        def rebootSystem(self):
            """
            Reboot the system
            -------
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".rebootSystem")
            return response['result'][0]
    


    
        def setDeviceName(self, name):
            """
            Set custom name for the device
            
            Parameters
            ----------
            name:  string: device name
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setDeviceName", [name])
            return response['result'][0]
    


    
        def setSecureAccess(self, privateKey, certificate):
            """
            Set custom keys for SSL access
            
            Parameters
            ----------
            privateKey:  string: The private key in PEM format
            certificate:  string: The certificate for the private key in PEM format
            Returns
            -------
            error: error code
            """
            response = self.device.request(self.interface_name + ".setSecureAccess", [privateKey, certificate])
            return response['result'][0]
    


    
    
    class Update():

        def __init__(self, device):
            self.device = device
            self.interface_name = "com.attocube.system.update"
            
        def getLicenseUpdateProgress(self):
            """
            Get the progress of running license update
            -------
            Returns
            -------
            value_int0: int: error code
            value_int1: int: progress in percent
            """
            response = self.device.request(self.interface_name + ".getLicenseUpdateProgress")
            return response['result'][0], response['result'][1]
    


    
        def getSwUpdateProgress(self):
            """
            Get the progress of running update
            -------
            Returns
            -------
            value_int0: int: error code
            value_int1: int: progress in percent
            """
            response = self.device.request(self.interface_name + ".getSwUpdateProgress")
            return response['result'][0], response['result'][1]
    


    
        def licenseUpdateBase64(self):
            """
            Execute the license update with base64 file uploaded
            -------
            Returns
            -------
            value_int0: int: error code
            """
            response = self.device.request(self.interface_name + ".licenseUpdateBase64")
            return response['result'][0]
    


    
        def softwareUpdateBase64(self):
            """
            Execute the update with base64 file uploaded
            -------
            Returns
            -------
            value_int0: int: error code
            """
            response = self.device.request(self.interface_name + ".softwareUpdateBase64")
            return response['result'][0]
    


    
        def uploadLicenseBase64(self, offset, b64Data):
            """
            Upload new license file in format base 64
            
            Parameters
            ----------
            offset:  int: offset of the data
            b64Data:  string: base64 data
            Returns
            -------
            value_int0: int: error code
            """
            response = self.device.request(self.interface_name + ".uploadLicenseBase64", [offset, b64Data])
            return response['result'][0]
    


    
        def uploadSoftwareImageBase64(self, offset, b64Data):
            """
            Upload new firmware image in format base 64
            
            Parameters
            ----------
            offset:  int: offset of the data
            b64Data:  string: base64 data
            Returns
            -------
            value_int0: int: error code
            """
            response = self.device.request(self.interface_name + ".uploadSoftwareImageBase64", [offset, b64Data])
            return response['result'][0]
    


    
