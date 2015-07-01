from __future__ import absolute_import

def create_objects_from_config_node(config, item_cfg_node):
    module = __import__('bliss.controllers.%s' % item_cfg_node['class'], fromlist=[None])
    klass = getattr(module, item_cfg_node['class'])
    item_name = item_cfg_node["name"]
    referenced_objects = dict()
    for name, value in item_cfg_node.iteritems():
        if isinstance(value, str) and value.startswith("$"):
            # convert reference to item from config
            item_cfg_node[name]=config.get(value)  
            referenced_objects[name]=item_cfg_node[name]

    o = klass(item_name, item_cfg_node)

    for name, object in referenced_objects.iteritems():
        if hasattr(o, name):
           continue
           #raise RuntimeError("'%s` member would be shadowed by reference in yml config file." % name)
        else:
            setattr(o, name, object) #add_property(o, name, object)

    return { item_name: o }
