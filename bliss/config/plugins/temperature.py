from __future__ import absolute_import
import logging
from bliss.common import log

def create_objects_from_config_node(config, item_cfg_node):
    log.info("--->On create_objects_from_config_node:")
    log.info("----create_objects_from_config_node: config:::: %s" % (config))
    log.info("%s" % type(config))
    log.info("----create_objects_from_config_node: item_cfg_node::: %s" % (item_cfg_node))
    log.info("%s" % type(item_cfg_node))
    parent_node = item_cfg_node.parent
    log.info("----create_objects_from_config_node: parent::: %s" % (parent_node))
    log.info("%s" % type(parent_node))
    item_name = item_cfg_node['name']

    module = __import__('bliss.controllers.temperature.%s' % parent_node['class'], fromlist=[None])
    
    inputs = list()
    outputs = list()
    loops = list()
    names = dict()
    for category, objects in [('inputs', inputs),('outputs', outputs), ('ctrl_loops', loops)]:
      log.info("...... category: %s , objects: %s" % (category,objects))
      for config_item in parent_node.get(category):
          log.info("...........config_item: %s" % (config_item))
          name = config_item.get("name")
          objects.append((name, config_item))
          names.setdefault(category, list()).append(name)
    log.info("inputs: %s" % (inputs))
    log.info("outputs: %s" % (outputs))
    log.info("ctrl_loops: %s" % (loops))
                  
    controller_class = getattr(module, parent_node["class"])
    controller = controller_class(parent_node, inputs, outputs, loops)
    
    cache_dict = dict()
    for category in ('inputs', 'outputs', 'ctrl_loops'):
        cache_dict.update(dict(zip(names[category], [controller]*len(names[category]))))

    #controller.initialize()
    o = controller.get_object(item_name)
    if item_name in dict(loops).keys():
        referenced_object = o.config['input'][1:]
        if referenced_object in controller._objects:
           # referencing an object in same controller
           o._TCtrlLoop__input = controller._objects[referenced_object]
        else:
           o._TCtrlLoop__input = config.get(referenced_object)
	referenced_object = o.config['output'][1:]
        if referenced_object in controller._objects:
           # referencing an object in same controller
           o._TCtrlLoop__output = controller._objects[referenced_object]
        else:
           o._TCtrlLoop__output = config.get(referenced_object)
	
    log.info("--->Leaving o::: %s" % (o))
    log.info("--->Leaving cache_dict::: %s " % (cache_dict))
    log.info("--->Leaving create_objects_from_config_node: ")
    return { item_name: o}, cache_dict
    
def create_object_from_cache(config, name, controller):
    log.info("--->On create_objects_from_cache:")
    log.info("--->create_objects_from_cache:config::: %s" % (config))
    log.info("%s" % type(config))
    log.info("--->create_objects_from_cache:name::: %s" % (name))
    log.info("%s" % type(name))
    log.info("--->create_objects_from_cache:controller %s" % (controller))
    log.info("%s" % type(controller))
    o = controller.get_object(name)
    log.info("--->Leaving o::: %s" % (o))
    log.info("%s" % type(o))
    log.info("--->Leaving create_objects_from_cache: ")
    return o
