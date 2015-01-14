def create_objects_from_config_node(item_cfg_node):
    try:
        module = __import__('bliss.controllers.%s' % item_cfg_node['class'], fromlist=[None])
    except ImportError:
        sys.excepthook(*sys.exc_info())
    else:
        try:
            klass = getattr(module, item_cfg_node['class'])
        except AttributeError:
            sys.excepthook(*sys.exc_info())
        else:
            try:
                o = klass(item_name, item_cfg_node)
            except:
                sys.excepthook(*sys.exc_info())
    return { item_cfg_node["name"]: o }
