from __future__ import absolute_import
import sys
from bliss.config import static
from khoros.core.measurement import CounterBase

def create_objects_from_config_node(config, item_cfg_node):
    module = __import__('bliss.controllers.%s' % item_cfg_node['class'], fromlist=[None])
    klass = getattr(module, item_cfg_node['class'])
    item_name = item_cfg_node["name"]
    for name, value in item_cfg_node.iteritems():
        if isinstance(value, str) and value.startswith("$"):
            # convert reference to item from config
            item_cfg_node[name]=config.get(value)  
    o = klass(item_name, item_cfg_node)

    if isinstance(o, CounterBase):
        static.register_counter(item_name)
    else:
        for property, value in o.__dict__.iteritems():
            if isinstance(value, CounterBase):
                static.register_counter(value.name)

    return { item_name: o }
