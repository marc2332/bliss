from __future__ import absolute_import

def create_objects_from_config_node(config, item_cfg_node):
    parent_node = item_cfg_node.parent
    item_name = item_cfg_node['name']

    module = __import__('bliss.controllers.temperature.%s' % parent_node['class'], fromlist=[None])
    
    inputs = list()
    outputs = list()
    loops = list()
    names = dict()
    for category, objects in [('inputs', inputs),('outputs', outputs), ('ctrl_loops', loops)]:
      for config in parent_node.get(category):
          name = config.get("name")
          objects.append((name, config))
          names.setdefault(category, list()).append(name)

    controller_class = getattr(module, parent_node["class"])
    controller = controller_class(parent_node, inputs, outputs, loops)
    
    cache_dict = dict()
    for category in ('inputs', 'outputs', 'ctrl_loops'):
        cache_dict.update(dict(zip(names[category], [controller]*len(names[category]))))

    #controller._update_refs()
    #controller.initialize()
    o = controller.get_object(item_name)

    return { item_name: o}, cache_dict

def create_object_from_cache(config, name, controller):
    o = controller.get_object(name)
    return o
