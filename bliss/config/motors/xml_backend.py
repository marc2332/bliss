import xml.etree.cElementTree as ElementTree
from . import get_controller_class, add_controller, add_group


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
    return _load_config(ElementTree.fromstring(config_xml))


def load_cfg(config_file):
    return _load_config(ElementTree.parse(config_file))


def _load_config(config_tree):
    for controller_config in config_tree.findall("controller"):
        controller_name = controller_config.get("name")
        controller_class_name = controller_config.get("class")
        if controller_name is None:
            controller_name = "%s_%d" % (
                controller_class_name, id(controller_config))

        controller_class = get_controller_class(controller_class_name)

        add_controller(
            controller_name,
            XmlDictConfig(controller_config),
            load_axes(controller_config),
            controller_class)

    for group_node in config_tree.findall("group"):
        group_name = group_node.get('name')
        if group_name is None:
            raise RuntimeError("%s: group with no name" % group_node)
        add_group(group_name, XmlDictConfig(group_node), load_axes(group_node))


def load_axes(config_node):
    """Return list of (axis name, axis_class_name, axis_config_node)"""
    axes = []
    for axis_config in config_node.findall('axis'):
        axis_name = axis_config.get("name")
        if axis_name is None:
            raise RuntimeError(
                "%s: configuration for axis does not have a name" %
                config_node)
        axis_class_name = axis_config.get("class")
        axes.append((axis_name, axis_class_name, XmlDictConfig(axis_config)))
    return axes
