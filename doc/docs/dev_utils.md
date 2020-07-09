# BLISS utils

`bliss.common.utils` module contains a collection of classes and functions used
to ease programming BLISS.



## class handling

### wrap_methods(from_object, target_object):

### add_property(inst, name, method):


## data structures operations

### grouped(iterable, n):
Group elements of an iterable n by n.  
Return a zip object.  
`s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ...`
Excedentary elements are discarded.

```python
DEMO [8]: from bliss.common.utils import grouped
DEMO [5]: list(grouped([1,2,3,4,5], 2))
 Out [5]: [(1, 2), (3, 4)]
```

### grouped_with_tail(iterable, n):

Like `grouped()`, but do not remove last elements if they not reach the given
length `n`.

```python
DEMO [09]: from bliss.common.utils import grouped_with_tail
DEMO [10]: list(grouped_with_tail([1,2,3,4,5], 2))
 Out [10]: [[1, 2], [3, 4], [5]]
```

### flatten_gen(items):
Flatten nested structures.

```python
DEMO [11]: from bliss.common.utils import flatten_gen
DEMO [13]: list(flatten_gen([1, [2, 3,[4, 5], 6]]))
 Out [13]: [1, 2, 3, 4, 5, 6]
```

### flatten(items):
Idem but return a list.

```python
CYRIL [14]: from bliss.common.utils import flatten
CYRIL [15]: flatten([1, [2, 3,[4, 5], 6]])
  Out [15]: [1, 2, 3, 4, 5, 6]
```

### merge(items):

Merge a list of list, first level only.
```
merge([ [1,2], [3] ]) -> [1,2,3]
merge([ [1,2], [[3,4]], [5] ]) -> [1,2,[3,4],5]
```

```python
DEMO [16]: from bliss.common.utils import merge
DEMO [17]: merge([ [1,2], [[3,4]], [5] ])
 Out [17]: [1, 2, [3, 4], 5]
```

### all_equal(iterable):


## Objects customization

Functions to add custom attributes and commands to an object.

Decorators for set/get methods to access to custom attributes

### add_object_method(obj, methode)

### object_method()

Decorator to add a custom method to an object.

The same as add_object_method but its purpose is to be used as a decorator to
the controller method which is to be exported as object method.

Return a method where _object_method_ attribute is filled with a dict of
elements to characterize it.

### object_method_type()

### add_object_attribute()

### object_attribute_type_get()

### object_attribute_get()

### object_attribute_type_set()

### object_attribute_set()

### set_custom_members

Creates custom methods and attributes for `<target_obj>` object
using `<src_object>` object definitions.  
Populates `__custom_methods_list` and `__custom_attributes_dict` for tango
device server.


### with_custom_members

A class decorator to enable custom attributes and custom methods.



## Various classes and functions

### Null

### StripIt(object)
Encapsulate object with a short str/repr/format.  
Useful to have in log messages since it only computes the representation if the
log message is recorded.

### periodic_exec


### safe_get

### common_prefix


### human_time_fmt


### Statistics
Calculate statistics from a profiling dictionary

* `key` == function name
* `values` == list of tuple (`start_time`, `end_time`)

```python

DEMO [29]: from bliss.common.utils import Statistics
DEMO [30]: profile = {"init()":[(0.1, 0.22)], "finalize()":[(0.01, 0.045)]}
DEMO [31]: Statistics(profile)
 Out [31]: func_name    min        mean       max            std
           -----------  ---------  ---------  ---------  -------
           finalize()   35.000ms   35.000ms   35.000ms   0.00000
           init()       120.000ms  120.000ms  120.000ms  0.00000
```



### autocomplete_property

A custom property class that will be added to jedi's ALLOWED_DESCRIPTOR_ACCESS


### UserNamespace


### deep_update
Do a deep merge of one dict into another.

## Types

### is_basictype

### is_complextype

### is_mutsequence

### is_mutmapping

### is_sametype

## Tree

### prudent_update(d, u):

Updates a MutableMapping or MutalbeSequence 'd'
from another one 'u'.
The update is done trying to minimize changes: the
update is done only on leaves of the tree if possible.
This is to preserve the original object as much as possible.


### update_node_info(node, d)

## math rounding

### rounder

### round


## Shell

### ShellStr

## Network

### get_open_ports(n):


## Colors

* `PURPLE(msg) `
* `CYAN(msg) `
* `DARKCYAN(msg) `
* `BLUE(msg) `
* `GREEN(msg) `
* `YELLOW(msg) `
* `RED(msg) `
* `UNDERLINE(msg)`
* `BOLD(msg) `


## Help/Errors

### ErrorWithTraceback

### WrappedMethod

### shorten_signature
By default it is removing the annotation of each parameter or replacing it with a custum one.

### custom_error_msg


### TypeguardTypeError


### typeguardTypeError_to_hint


### typecheck_var_args_pattern


### modify_annotations
Modify the annotation in an existing signature.

### is_pattern
Return true if the input string is a pattern for `get_matching_names`.

### get_matching_names
Search a pattern into a list of names (unix pattern style).

## Messages

### nonblocking_print

