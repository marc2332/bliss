import sys

def create_objects_from_config_node(item_cfg_node):
    module = __import__('bliss.controllers.%s' % item_cfg_node['class'], fromlist=[None])
    klass = getattr(module, item_cfg_node['class'])
    item_name = item_cfg_node["name"]
    o = klass(item_name, item_cfg_node)
    return { item_name: o }
