# How to use Session map

Bliss builds a graph of instances created in the session. 

This is in fact a dynamic map where every instance is a node related to other nodes.
Thanks to this map we can access instances at realtime, collect information and interact.

Let's go further with some code.

## Basic Map

```python
BLISS [1]: from bliss.common import session
BLISS [2]: m = session.get_current().map  # the map
BLISS [3]: len(m)
  Out [3]: 5
BLISS [4]: list(m)  # list of node ids
  Out [4]: ['session', 'controllers', 'comms', 'counters','axes']
BLISS [5]: m['session']  # accessing an element
  Out [5]: {'instance': 'session', 'tag': 'session', '_logger': <Logger session (WARNING)>}
BLISS [6]: m.G  # the DiGrap low-level container
  Out [6]: <networkx.classes.digraph.DiGraph object at 0x7fdc4fa435c0>
BLISS [7]: m.G.nodes  # listing directly DiGraph nodes
  Out [7]: NodeView(('session', 'controllers', 'comms', 'counters','axes'))
BLISS [8]: m.draw_pygraphviz()
```
{% dot session_map_basic.svg
strict digraph  {
	node [label="\N"];
	session;
	controllers;
	session -> controllers;
	comms;
	session -> comms;
	counters;
	session -> counters;
    axes;
    session -> axes;
}
%}

We can see that `map.G` is an instance of DiGraph from networkx module and that has a length of 5.
We can also list the names of basic nodes of a session.


## More complex map

```python
BLISS [3]: from bliss.common import session
BLISS [4]: m = session.get_current().map  # the map instance
BLISS [5]: roby = config.get('roby')
BLISS [6]: len(m)
  Out [6]: 7 
BLISS [7]: list(m)
  Out [7]: ['session', 'controllers', 'comms', 'counters', 'axes', 140483187066584, 140483253486984]
BLISS [9]: m.draw_pygraphviz()
```

{% dot session_map_complex.svg
strict digraph  {
	node [label="\N"];
	session;
	controllers;
	session -> controllers;
	comms;
	session -> comms;
	counters;
    session -> counters;
	axes;
    session -> axes;
    mockup;
    controllers -> mockup;
    roby;
    mockup -> roby;
    axes -> roby;

}
%}

After getting `roby` the map increases the size to 7. In fact, also the controller `mockup` was initialized.


## Node IDs

Going a bit more indeep about how we identify nodes we can have two tipes:

* Strings, identified by the string itself
* Other Instances, identified by python id(instance) number

## Registering nodes

In the following code we will register two nodes: the first is a `string` node, the second is an instance of a just defined class A.

You can notice some facts:

 * The first argument is **the instance** that you want to register
    *  If it is a string the string itself (e.g. 'my_node')
    *  If it is an instance give it as a reference (e.g. myinst in the case above or self inside a class)
 * If no parent is given the instance will be registered under "controllers"
 * Going through `session.get_current().map.G[node_instance]` you can retrive node informations like *weakref*, *logger* and others.

```python
BLISS [1]: from bliss.common import session
BLISS [2]: m = session.get_current().map
BLISS [3]: m.register('my_node')
BLISS [4]: class A():
      ...:     pass
BLISS [5]: myinst = A()
BLISS [6]: m.register(myinst, parents_list=['my_node','counters'])
BLISS [7]: m.draw_pygraphviz()
```
{% dot session_map_addnode.svg
strict digraph  {
	node [label="\N"];
	session	 [ label=session, ];
	controllers	 [ label=controllers, ];
	session -> controllers;
	comms	 [ label=comms,];
	session -> comms;
	counters	 [ label=counters,];
	session -> counters;
    axes;
    session -> axes;
	my_node	 [ label=my_node, ];
	controllers -> my_node;
	140415995035040	 [ label=140415995035040];
	my_node -> 140415995035040;
	counters -> 140415995035040;
}
%}

Conceptually we registered the instance `a` of the `class A` as a child of my_node and counters. If we were asked for what is it, we could suppose that is a counter for my_node. Just an example anyway.

For more examples on how to register a device, see: [Logging a controller](dev_maplog_controller.md)

# Map Advanced features

The map is in fact a picture `picture` of the runtime state of the session.

Through the map we can:

  * visualize the map of existing instances
  * get instance references and, with this, access every method/attribute
  * introspect attributes

## Visualize the map

As simple as:

```python
from bliss.common import session
session.get_current().map.draw_pygraphviz()
```

or with matplotlib:

```python
from bliss.common import session
session.get_current().map.draw_matplotlib()
```

If you want to visualize only one part you can give a node as an argument
and you will be given a partial view of the map.

```python
roby = config.get('roby')
m = session.get_current().map

# draw with matplotlib
m.draw_matplotlib(roby)

# draw with pygraphviz
m.draw_pygraphviz(roby)

## Introspection

You can use the same approach to introspect the map passing a specific argument:

```python
from bliss.common import session
m = session.get_current().map
# will try to visualize instance attributes 'port' and 'ip')
m.draw_pygraphviz(format_node="inst.port+inst.ip")
# will try to visualize instance 'controller' attribute as node text
m.draw_pygraphviz(format_node="inst.controller")
# will try to visualize instance 'conn' attribute and if does not exist the id
m.draw_pygraphviz(format_node="inst.conn->id")
```
This `mini language` can be used to visualize instance attributes.
We have the `+` operator that will visualize more than one attribute separated by a space
and we have the `->` operator that will define an order: try to visualize the first, if None
try to visualize the second and so on.

This kind of visualization is a high level interface intended for representing in an human
friendly way all instances.

If you need something more machine-friendly the way to go is:

```python
m = session.get_current().map
m.update_labels(format_string="tag->inst.name->class->id")
```

This will update the label attribute of each node inside the DiGraph with the values
computed from the instance through the format_string. 

More detailed information about the mini-language can be retrieved with:

```
from bliss.common import session
help(session.get_current().map.format_node)
```

## Access instance references

Instances can be accessed through the DiGraph.

```python
TEST_SESSION [16]: m = session.get_current().map
TEST_SESSION [17]: [node for node in m]
Out [16]: ['session', 'controllers', 'comms', 'counters', 'axes', 140483187066584, 140483253486984]
TEST_SESSION [10]: [m[node].get('instance') for node in m]
Out [10]: ['session', 'controllers', 'comms', 'counters', 'axes', <weakref at 0x7fc4ce6c8d18; to 'Mockup' at 0x7fc4ca7646d8>, <weakref at 0x7fc4ce6c8e08; to 'MockupAxis' at 0x7fc4ce6bc588>]
TEST_SESSION [11]: [m[node].get('name') for node in m]
Out [11]:  [None, None, None, None, None, '8d6318d713ee6beb9efbb5be322b8dde', 'roby']
```
