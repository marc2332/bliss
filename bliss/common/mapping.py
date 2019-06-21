# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.import logging
import networkx as nx
from functools import wraps, partial
import weakref
import logging
import subprocess

__all__ = ["Map", "format_node"]

logger = logging.getLogger(__name__)


def map_id(node):
    """
    Helper to get the proper node map id
    it will be the string itself if a string
    if the node is integer we assume that is already an id

    it will be the id if a different instance

    Needed to avoid errors caused by changing of string id
    """
    return node if isinstance(node, (str, int)) else id(node)


class Map:
    def __init__(self):
        self.G = nx.DiGraph()
        self.handlers_list = []

        self.G.find_children = self.find_children
        self.G.find_predecessors = self.find_predecessors
        self.node_attributes_list = ["name", "address", "plugin"]
        self.__waiting_queue = []
        self.__lock = False

        self.register("session")
        self.register("controllers", parents_list=["session"])
        self.register("comms", parents_list=["session"])
        self.register("counters", parents_list=["session"])
        self.register("axes", parents_list=["session"])

    def _create_node(self, instance):
        logger.debug(f"register: Creating node:{instance} id:{id(instance)}")
        self.G.add_node(
            map_id(instance),
            instance=instance
            if isinstance(instance, str)
            else weakref.ref(instance, partial(self._trash_node, id_=map_id(instance))),
        )  # weakreference to the instance with callback on removal
        return self.G.node[map_id(instance)]

    def register(
        self, instance, parents_list=None, children_list=None, tag: str = None, **kwargs
    ):
        """
        Registers a devicename and instance inside a global device graph

        register(self)  # bareminimum
        register(self, children_list=[self.comm])  # with the communication layer
        register(self, parents_list=[self.controller])  # with parent controller
        register(self, tag=f"{host}:{port}")  # instance with proper name
        register(self, parents_list=['controllers','comms'])  # two parents

        If no parent is attached it will be 'controllers' and then eventually
        remapped if another instance will have as a child the other instance.

        There could be node parents in form of a string, system defined are:
            * 'controllers'
            * 'counters'
            * 'comms'

        Args:
            instance: instance of the object (usually self)
            parents_list: list of parent's instances
            children_list: list of children's instances
            tag: user tag to describe the instance in the more appropriate way
            kwargs: more key,value pairs attributes to be attached to the node

       
        ToDo:
            * Avoid recreation of nodes/edges if not necessary
        """
        if self.__lock:
            node_info = {
                "instance": instance,
                "parents_list": parents_list,
                "children_list": children_list,
                "tag": tag,
                "kwargs": kwargs,
            }

            self.__waiting_queue.append(("create", node_info))
        else:
            self._register(
                instance,
                parents_list=parents_list,
                children_list=children_list,
                tag=tag,
                **kwargs,
            )
            self.trigger_update()

    def _register(
        self, instance, parents_list=None, children_list=None, tag: str = None, **kwargs
    ):
        # get always a list of arguments
        if parents_list is None:
            parents_list = []
        if children_list is None:
            children_list = []

        if not isinstance(parents_list, list) or not isinstance(children_list, list):
            raise TypeError("parents_list and children_list should be of type list")

        # First create this node
        node = self._create_node(instance)

        # adding attributes
        if tag or isinstance(instance, str):  # tag creation
            node["tag"] = tag if tag else instance  # if is a string represent as self

        for attr in self.node_attributes_list:
            # Adding attributes from the node_attributes_list
            # attributes can be appended also at runtime
            try:
                node[attr] = getattr(instance, attr)
            except AttributeError:
                pass

        for key, value in kwargs.items():
            # populating self defined attributes
            if self.G.node[map_id(instance)].get(key):
                logger.debug("Overwriting node {key}")
            node[key] = value

        # parents
        for inst in parents_list:
            if map_id(inst) not in self.G:
                logger.debug(f"register: Creating parent:{inst} id:{map_id(inst)}")
                self.register(inst, children_list=[instance])  # register parents

        # children
        for inst in children_list:
            if map_id(inst) not in self.G:
                logger.debug(f"register: Creating child:{inst} id:{map_id(inst)}")
                self.register(inst, parents_list=[instance])  # register children

        # edges
        for parent in parents_list:
            # add parents
            self.G.add_edge(map_id(parent), map_id(instance))

        for child in children_list:
            # remap children removing the parent connection to controllers
            if (map_id("controllers"), map_id(child)) in self.G.edges:
                self.G.remove_edge(map_id("controllers"), map_id(child))
            # add child
            self.G.add_edge(map_id(instance), map_id(child))

        for parent in parents_list:
            # remap parents removing the parent connection to the device
            if (map_id("controllers"), map_id(instance)) in self.G.edges:
                self.G.remove_edge(map_id("controllers"), map_id(instance))
            # add child
            self.G.add_edge(map_id(parent), map_id(instance))

    def _trash_node(self, *args, id_=None):
        if id_ is None:
            return
        self.__waiting_queue.append(("delete", {"instance": id_}))
        if not self.__lock:
            self.trigger_update()

    def __len__(self):
        return len(self.G)

    def __getitem__(self, instance):
        return self.G.nodes[map_id(instance)]

    def __iter__(self):
        return iter(self.G)

    def instance_iter(self, tag):
        node_list = list(self.G[tag])
        for node_id in node_list:
            node = self.G.node.get(node_id)
            if node is not None:
                inst_ref = self.G.node.get(node_id)["instance"]
                inst = inst_ref()
                if inst:
                    yield inst

    def trigger_update(self):
        """
        Triggers execution of handler functions on the map
        """
        self.__lock = True  # no nested trigger update

        logger.debug(f"trigger_update: executing")
        try:
            while self.__waiting_queue:
                operation, node_info = self.__waiting_queue.pop()
                if operation == "delete":
                    self.delete(node_info["instance"])  # deleting node

                elif operation == "create":
                    instance = node_info["instance"]
                    parents_list = node_info["parents_list"]
                    children_list = node_info["children_list"]
                    tag = node_info["tag"]
                    kwargs = node_info["kwargs"]

                    self._register(
                        instance,
                        parents_list=parents_list,
                        children_list=children_list,
                        tag=tag,
                        **kwargs,
                    )
                else:
                    raise NotImplementedError

            self.add_parent_if_missing()
            for func in self.handlers_list:
                try:
                    func(self.G)
                except Exception:
                    logger.exception(
                        f"Failed trigger_update on map handlers for {func.__name__}"
                    )
                    raise
        finally:
            self.__lock = False  # we can trigger update again

        if self.__waiting_queue:
            # if in the meanwhile there are waiting nodes
            self.trigger_update()

    def find_predecessors(self, node):
        """
        Returns the predecessor of a node

        Args:
            node: instance or id(instance)
        Returns:
            list: id of predecessor nodes
        """
        id_ = map_id(node)
        return [n for n in self.G.predecessors(id_)]

    def find_children(self, node) -> list:
        """
        Args:
            node: instance or id(instance)
        Returns:
            list: id of child nodes
        """
        id_ = map_id(node)
        return [n for n in self.G.adj.get(id_)]

    def shortest_path(self, node1, node2):
        """
        Args:
            node1: instance or id(instance)
            node2: instance or id(instance)

        Returns:
            list: path fron node1 to node2

        Raises:
            networkx.exception.NodeNotFound
            networkx.exception.NetworkXNoPath
        """
        id_1 = map_id(node1)
        id_2 = map_id(node2)
        return nx.shortest_path(self.G, id_1, id_2)

    def create_partial_map(self, sub_G, node):
        """
        Create a partial map containing all nodes that have some
        direct or indirect connection with the given one

        Args:
            sub_G: nx.DiGraph object that will be populated
            node: instance or id(instance)

        Returns:
            networkx.DiGraph
        """
        # UPSTREAM part of the map
        # getting all simple path from the root node "session"
        # to the given node
        logger.debug(f"In create_partial_map of {node} map_id({map_id(node)})")
        paths = nx.all_simple_paths(self.G, "session", map_id(node))
        paths = list(paths)
        for path in map(nx.utils.pairwise, paths):
            for father, son in path:
                sub_G.add_node(
                    father, **self.G.nodes[father]
                )  # adds the node copying info
                sub_G.add_node(son, **self.G.nodes[son])  # adds the node copying info
                sub_G.add_path([father, son])

        # DOWNSTREAM part of the map
        # getting all nodes from the given node to the end of the map
        self.create_submap(sub_G, node)

    def create_submap(self, sub_G, node):
        """
        Create a submap starting from given node
        Args:
            sub_G: nx.DiGraph object that will be populated
            node: instance or id(instance) of the starting node

        Returns:
            networkx.DiGraph
        """
        id_ = map_id(node)
        sub_G.add_node(id_, **self.G.nodes[id_])  # adds the node copying info
        for n in self.G.adj.get(id_):
            if n not in sub_G.neighbors(id_):
                sub_G.add_path([id_, n])
                sub_G.nodes[id_]
                self.create_submap(sub_G, n)

    def delete(self, id_):
        """
        Removes the node from graph

        Args:
            id_: id of node to be deleted

        Returns:
            True: The node was removed
            False: The node was not in the graph
        """
        logger.debug(f"Calling mapping.delete for {id_}")
        if id_ in self.G:
            logger.debug(f"mapping.delete: Removing node id:{id_}")
            predecessors_id = self.find_predecessors(id_)
            children_id = self.find_children(id_)
            self.G.remove_node(id_)
            # Remaps parents edges on children
            if predecessors_id and children_id:
                for pred in predecessors_id:
                    for child in children_id:
                        self.G.add_edge(pred, child)
            return True
        return False

    def format_node(self, node, format_string):
        return format_node(self.G, node, format_string)

    def add_map_handler(self, func):
        self.handlers_list.append(func)

    def add_parent_if_missing(self):
        """
        Remaps nodes with missing parents to 'controllers'
        """
        for node in list(self.G):
            try:
                preds = list(self.G.predecessors(node))
            except nx.NetworkXError:
                continue
            else:
                if not preds and node != "session":
                    self.G.add_edge("controllers", node)
                    logger.debug(f"Added parent to {node}")

    def draw_matplotlib(
        self, ref_node=None, format_node: str = "tag->name->class->id"
    ) -> None:
        """
        Simple tool to draw the map with matplotlib

        Args:
            ref_node: If given a partial map will be drawn that includes
                      the given node and his area of interest
            format_node: Format string (according to Bliss map formatting)
                         that will the label of represented nodes
        """
        try:
            import matplotlib.pyplot as plt

            self.update_labels(format_node)
            if ref_node is not None:
                G = nx.DiGraph()
                self.create_partial_map(G, map_id(ref_node))
            else:
                G = self.G

            labels = {node: G.node[node]["label"] for node in G}
            nx.draw_networkx(G, with_labels=True, labels=labels)
            plt.show()
        except ModuleNotFoundError:
            logger.error("Missing matplotlib package")

    def save_to_dotfile(
        self, ref_node=None, filename: str = "graph", format_node: str = "name"
    ) -> None:
        """
        Creates a network description as a dotfile compatible with graphviz

        Args:
            ref_node: If given a partial map will be drawn that includes
                      the given node and his area of interest
            filename: name of the output file without extension, the function will
                      create a filename.dot and filename.png
            format_node: Format string (according to Bliss map formatting)
                         that will the label of represented nodes
        """
        try:
            from networkx.drawing.nx_agraph import graphviz_layout, to_agraph

            self.update_labels(format_node)
            if ref_node is not None:
                G = nx.DiGraph()
                self.create_partial_map(G, map_id(ref_node))
            else:
                G = self.G

            C = to_agraph(G)
            C.write(f"{filename}.dot")
        except ImportError:
            logger.error("Missing pygraphviz package")

    def draw_pygraphviz(
        self, ref_node=None, filename="graph", format_node="tag->name->class->id"
    ) -> None:
        """
        Simple tool to draw the map into graphviz format

        Args:
            ref_node: If given a partial map will be drawn that includes
                      the given node and his area of interest
            filename: name of the output file without extension, the function will
                      create a filename.dot and filename.png
            format_node: Format string (according to Bliss map formatting)
                         that will the label of represented nodes
        """
        self.save_to_dotfile(
            ref_node=ref_node, filename=filename, format_node=format_node
        )

        try:
            subprocess.run(["dot", f"{filename}.dot", "-Tpng", "-o", f"{filename}.png"])
        except FileNotFoundError:
            logger.error("Missing graphviz software")
            return
        try:
            subprocess.run(["xdg-open", f"{filename}.png"])
        except Exception:
            logger.exception("Exception opening xdg-open")

    def _update_key_for_nodes(
        self, format_string="tag->name->class->id", dict_key="label"
    ):
        """
        Create or recreate a key,value pair inside the node dictionary 
        according to a format string
        It is useful, for example, in order to create map that represents
        the graph passing node proper names to 'label' attribute that
        will be read by pygraphviz

        Args:
            format_string: formatting string (see method format_node for details)
            dict_key: the output key that will be used to store values inside node's dictionary

        Examples:
            >>> G.update_key_for_nodes("class", dict_key='logger_name')
            This creates a key,value pair inside the node's dict called
            'logger_name' and assigns the name of the instance class or empty

            >>> G.update_key_for_nodes("tag+address->id", dict_key='description')
            This creates a key,value pair inside the node's dict called
            'description' and assigns the tag plus address or if not found
            the id of the node
        """
        for n in self.G:
            value = self.format_node(n, format_string=format_string)
            self.G.node[n][dict_key] = value

    def update_labels(self, format_string="tag->name->class->id"):
        self._update_key_for_nodes(format_string, "label")


def format_node(graph, node, format_string="tag->name->class->id"):
    """
    It inspects the node attributes to create a proper representation

    It recognizes the following operators:
       * inst.
       * -> : apply a hierarchy, if the first on left is found it stops, 
              otherwise continues searching for an attribute
       * + : links two attributes in one

    Typical attribute names are:
       * id: id of instance
       * tag: defined argument during instantiation
       * class: class of the instance
       * inst: representation of instance
       * inst.name: attribute "name" of the instance (if present)
       * user defined: as long as they are defined inside the node's 
                       dictionary using register or later modifications

    Args:
       graph: DiGraph instance
       node: id of the node
       format_string: formatting string

    Returns:
       str: representation of the node according to the format string
    
    """
    G = graph
    n = node
    format_arguments = format_string.split("->")
    value = ""  # clears the dict_key
    reference = G.node[n].get("instance")
    inst = reference if isinstance(reference, str) else reference()
    if inst is None:
        raise RuntimeError(
            "Trying to get string representation of garbage collected node instance"
        )

    for format_arg in format_arguments:
        # known arguments
        all_args = []
        for arg in format_arg.split("+"):
            if arg == "id":
                all_args.append(str(n))
            elif arg == "class":
                if not isinstance(inst, str):
                    all_args.append(inst.__class__.__name__)
            elif arg.startswith("inst"):
                attr_name = arg[5:]  # separates inst. from the rest
                if len(attr_name) == 0:  # requested only instance
                    all_args.append(str(inst))
                if hasattr(inst, attr_name):
                    # if finds the attr assigns to dict_key
                    attr = getattr(inst, attr_name)
                    all_args.append(str(attr))
            else:
                val = G.node[n].get(arg)
                if val:
                    # if finds the value assigns to dict_key
                    all_args.append(str(val))
        if len(all_args):
            value = " ".join(all_args)
            break
    return value
