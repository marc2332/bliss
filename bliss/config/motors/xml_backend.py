import xml.etree.cElementTree as ElementTree
from . import get_controller_class, add_controller


class XmlListConfig(list):

    def __init__(self, aList):
        for element in aList:
            if element:
                # treat like dict
                if len(element) == 1 or element[0].tag != element[1].tag:
                    self.append(XmlDictConfig(element))
                # treat like list
                elif element[0].tag == element[1].tag:
                    self.append(XmlListConfig(element))
            elif element.text:
                text = element.text.strip()
                if text:
                    self.append(text)


class XmlDictConfig(dict):

    def __init__(self, parent_element):
        self.parent_element = parent_element

        if parent_element.items():
            self.update(dict(parent_element.items()))
        for element in parent_element:
            if element:
                # treat like dict - we assume that if the first two tags
                # in a series are different, then they are all different.
                if len(element) == 1 or element[0].tag != element[1].tag:
                    aDict = XmlDictConfig(element)
                # treat like list - we assume that if the first two tags
                # in a series are the same, then the rest are the same.
                else:
                    # here, we put the list in dictionary; the key is the
                    # tag name the list elements all share in common, and
                    # the value is the list itself
                    aDict = {element[0].tag: XmlListConfig(element)}
                # if the tag has attributes, add those to the dict
                if element.items():
                    aDict.update(dict(element.items()))
                self.update({element.tag: aDict})
            # this assumes that if you've got an attribute in a tag,
            # you won't be having any text.
            elif element.items():
                self.update({element.tag: dict(element.items())})
            # finally, if there are no child tags and no attributes, extract
            # the text
            else:
                self.update({element.tag: element.text})


def load_cfg_fromstring(config_xml):
    """Load configuration from xml string

    Args:
        config_xml (str): string holding xml representation of config

    Returns:
        None
    """
    return _load_config(ElementTree.fromstring(config_xml))


def load_cfg(config_file):
    """Load configuration from xml file

    Args:
        config_file (str): full path to configuration file

    Returns:
        None
    """
    return _load_config(ElementTree.parse(config_file), config_file)


def _load_config(config_tree, config_file=None):

    for controller_config in config_tree.findall("controller"):
        controller_name = controller_config.get("name")
        controller_class_name = controller_config.get("class")
        if controller_name is None:
            controller_name = "%s_%d" % (
                controller_class_name, id(controller_config))

        controller_class = get_controller_class(controller_class_name)

        config = XmlDictConfig(controller_config)
        config.config_file = config_file
        config.root = config_tree

        add_controller(
            controller_name,
            config,
            load_axes(controller_config, config_tree, config_file),
            load_encoders(controller_config, config_tree, config_file),
            controller_class)

    """
    for group_node in config_tree.findall("group"):
        group_name = group_node.get('name')
        if group_name is None:
            raise RuntimeError("%s: group with no name" % group_node)
        config = XmlDictConfig(group_node)
        config.config_file = config_file
        config.root = config_tree
        add_group(group_name, config, load_axes(group_node))
    """

def _load_objects(object_tag, config_node, config_tree, config_file):
    objects = []
    for object_config in config_node.findall(object_tag):
        object_name = object_config.get("name")
        if object_name is None:
            raise RuntimeError(
                "%s: configuration for %s does not have a name" %
                config_node, object_tag)
        object_class_name = object_config.get("class")
        config = XmlDictConfig(object_config)
        config.config_file = config_file
        config.root = config_tree
        objects.append((object_name, object_class_name, config))
    return objects


def load_axes(config_node, config_tree=None, config_file=None):
    """Return list of (axis name, axis_class_name, axis_config_node)"""
    return _load_objects("axis", config_node, config_tree, config_file)


def load_encoders(config_node, config_tree=None, config_file=None):
    """Return list of (encoder name, encoder_class_name, encoder_config_node)"""
    return _load_objects("encoder", config_node, config_tree, config_file)


def write_setting(config_dict, setting_name, setting_value):
    config_node = config_dict.parent_element

    setting_node = config_node.find("settings")
    if setting_node is None:
        setting_node = ElementTree.SubElement(config_node, "settings")
    setting_element = setting_node.find(setting_name)
    if setting_element is None:
        setting_element = ElementTree.SubElement(
            setting_node, setting_name, {"value": str(setting_value)})
    else:
        setting_element.set("value", str(setting_value))


def commit_settings(config_dict):
    if config_dict.config_file is not None:
        config_dict.root.write(config_dict.config_file)
    else:
        pass  # ElementTree.dump(config_dict.root)


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
            try:
                return converter(property_attrs.get("value"))
            except AttributeError:
                return converter(property_attrs)
        else:
            if default is not None:
                return default

            raise KeyError("no property '%s` in config" % property_name)

