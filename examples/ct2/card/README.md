# CT2 low level card examples

The examples in this directory show how to work with the python
object that talks directly to the CT2 driver.

They are very close to the metal / low level examples.

You will probably never need to use something like this **unless** you are
implementing a new acquisition feature. For example, if you like to implement
the equivalent of *monitor* mode in spec (ie, instead of counting on time,
count until a channel reaches a certain value), then the examples here
might help you.
