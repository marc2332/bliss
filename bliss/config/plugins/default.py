def create_objects_from_config_node(config, item_cfg_node):
    item_name = item_cfg_node["name"]
    for name, value in item_cfg_node.iteritems():
        if isinstance(value, str) and value.startswith("$"):
            # convert reference to item from config
            item_cfg_node[name]=config.get(value)  
    
    return { item_name: item_cfg_node }
