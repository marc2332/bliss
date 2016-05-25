from __future__ import absolute_import

def __find_class(cfg_node):
    klass_name = cfg_node['class']

    if 'package' in cfg_node:
        module_name = cfg_node['package']
    elif 'module' in cfg_node:
        module_name = 'bliss.controllers.%s' % cfg_node['module']
    else:
        # discover module and class name
        module_name = 'bliss.controllers.%s' % klass_name
        try:
            module = __import__(module_name, fromlist=[None])
        except ImportError:         # try in file in lower case
            module_name = 'bliss.controllers.%s' % klass_name.lower()
            module = __import__(module_name, fromlist=[None])
        try:
            klass = getattr(module, klass_name)
        except AttributeError:      # try with camelcase
            klass_name = ''.join((x.capitalize() for x in klass_name.split('_')))

    module = __import__(module_name, fromlist=[None])
    klass = getattr(module, klass_name)

    return klass


def create_objects_from_config_node(config, item_cfg_node):
    klass = __find_class(item_cfg_node)
        
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
