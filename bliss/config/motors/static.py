class StaticConfig(object):

    def __init__(self, config_dict):
        self.config_dict = config_dict

    def get(self, property_name, converter=str, default=None):
        """Get static property

        Args:
            property_name (str): Property name
            converter (function): Default :func:`str`, Conversion function from configuration format to Python
            default: Default: None, default value for property

        Returns:
            Property value

        Raises:
            KeyError, ValueError
        """
        property_attrs = self.config_dict.get(property_name)
        if property_attrs is not None:
            return converter(property_attrs.get("value"))
        else:
            if default is not None:
                return default

            raise KeyError("no property '%s` in config" % property_name)
