# DataNode

This is the base class of the DataNodeContainer, ChannelDataNode and LimaImageChannelDataNode classes.
This object cannot have children nodes.

#### Attributes

* `db_name`: the full name of the node. Reflects the position of the node in the tree of nodes. 
* `name`: the short name for the node.
* `type`: the type of the node (str).
* `parent`: the parent node.
* `info`: info about the node.



# DataNodeContainer

This class inherit from the DataNode class and can have a list of children nodes.

* `type = container`

#### Methods

* `add_children(*child)`
* `children(from_id=0, to_id=-1)`
* `last_child()`



# ChannelDataNode

This class inherit from the DataNode class and is designed to hold data.

* `type = channel`

#### Attributes

* `shape`
* `dtype`
* `alias`

#### Methods

* `get(from_index, to_index=None)`



# LimaImageChannelDataNode

#### Methods

* `get(from_index, to_index=None)`



# Scan

This class inherit from the DataNodeContainer class and is designed for scans.

* `type = scan`

# DataNodeIterator

#### Methods

* `walk(self, filter=None, wait=True, ready_event=None)`
* `walk_events( filter=None, ready_event=None)`