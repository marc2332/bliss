# Adding logging and mapping capabilities to Controller

## Logging and Mapping

Logging and Mapping instances are strictly related in Bliss: every device should register himself before gaining those features.

## How to Register a device

    from bliss.common import mapping
    from bliss.common.logtools import LogMixin

    class MyController(LogMixin):
        def __init__(self, *args, **kwargs):
            mapping.register(self)
            ...
            self._logger.info("HI, I am born")

The preceding is a barebone example of how to register a device inside device map and send an INFO logging message.

Key points are the following:

### Add LogMixin to the device

This will add _logger method to class that will be the entry point for all logging operations and will also raise an exception if the logging will be used before device is mapped inside bliss device map.

### Register the device

This is done calling `mapping.register` passing at list the self parameter. If _logger methods are used before the registration this will fail raising an exception; for this reason mapping.register should be called as soon as possible.

## How to Create a nice device map

The map is in fact a Graph that wants to register every relevant instance of a Beamline, including Controller, Connections, Devices, Axis, and so on.
When registering a device it is convenient to add as much information as possible in order to have an usefull map that can be used to represent the beamline or to apply any sort of desired handler.
For this reason is important to add:
* parents_list: a list containing the parents of the instance, in case of a device it will be the controller instance, in case of a communication it will be a controller but also "comms".
* children_list: a list containing children istances as comms, transactions, devices, axis
* tag: this should be the best suited name to represent the instance.

Some Examples:

Here we have a Motor that is child of a controller

    mapping.register(self, parents_list=[self.controller], tag=str(self))

Here we have a controller with a child connection

    mapping.register(self, children_list=[self._cnx])

Here we have a serial connection that we also want to be child of "beamline"->"comms"

    mapping.register(self, parents_list=["comms"])


To explain the flexibility here we are mapping inside a Command class (that is self) and self._fd is a child socket, in fact we are inside Command but we are recording all links beetween them. The result will something like this:

    "beamline" --> "devices" -> Command -> Socket
               \-> "comms" ------------->/

In fact instances that will not have parents wil be childs of "beamline"->"devices" by default
and later eventually remapped if we register another instance as parent of Command.

    self._fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    mapping.register(self._fd, parents_list=[self, "comms"], tag=f"Socket[{local_host}:{local_port}",

There is no problem if you want to register the same device twice or even more times: it will automatically remap adding or removing links if necessary.
In general this is convenient for example when you want to log as soon as possible and then after creating let's say a Socket you want to register it a child.

The Bliss barebone map is something like this:

    beamline -> devices
             -> sessions
             -> comms
             -> counters

Those Graph nodes are in fact string and they constitute the root to wich all other nodes will be attached.
Be aware that all instances, if nothing is specify, will be child of devices, 


## Logging Instance Methods

TODO