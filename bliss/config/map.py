from bliss.common.axis import Axis
from bliss.common.temperature import Input, Output, Loop
from bliss import global_map
from bliss.controllers.motor import CalcController


def register_axis(global_map, axis, add_to_axes=False):
    parents_list = [axis.controller]
    if add_to_axes:
        parents_list.append("axes")

    global_map.register(axis, parents_list=parents_list)


def register_temperature_object(global_map, obj, add_to_counters=False):
    parents_list = [obj.controller]
    if isinstance(obj, Loop):
        children_list = [obj.input, obj.output]
    else:
        if add_to_counters:
            parents_list.append("counters")
        children_list = []
    global_map.register(obj, parents_list=parents_list, children_list=children_list)


def update_map_for_object(instance_object):
    if isinstance(instance_object, Axis):
        build_motor_controller_map(instance_object.controller)
        register_axis(global_map, instance_object, add_to_axes=True)
    elif isinstance(instance_object, (Input, Output, Loop)):
        build_temperature_controller_map(instance_object.controller)
        register_temperature_object(global_map, instance_object, add_to_counters=True)


def build_motor_controller_map(controller):
    if isinstance(controller, CalcController):
        global_map.register(
            controller, children_list=list(controller.reals) + list(controller.pseudos)
        )
    else:
        for axis in controller.axes.values():
            register_axis(global_map, axis)
            for hook in axis.motion_hooks:
                global_map.register(hook, parents_list=["motion_hooks"])


def build_temperature_controller_map(controller):
    for obj in controller._objects.values():
        register_temperature_object(global_map, obj)
