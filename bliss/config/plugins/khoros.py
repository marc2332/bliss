from __future__ import absolute_import

def create_objects_from_config_node(config, item_cfg_node):
    try:
        module = __import__('bliss.controllers.%s' % item_cfg_node['class'], fromlist=[None])
    except ImportError:         # try in file in lower case
        module = __import__('bliss.controllers.%s' % item_cfg_node['class'].lower(), fromlist=[None])
    klass_name = item_cfg_node['class']
    try:
        klass = getattr(module, klass_name)
    except AttributeError:      # try with camelcase
        klass_name = ''.join((x.capitalize() for x in klass_name.split('_')))
        klass = getattr(module, klass_name)
        
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
