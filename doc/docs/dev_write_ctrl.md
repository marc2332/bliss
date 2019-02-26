# Writing a BLISS controller

Here you can find somt tips about the wrinting of a BLISS controller.


## __str__ and __repr__ methods

If implemented in a Python class, `__repr__` and `__str__` methods are
used to return information about an object instantiating this class.

* `__str__` should print a readable message
* `__repr__` should print a message that is unambigous (e.g. name of an identifier, class name, etc).

`__str__` is called:

* when the object is passed to the print() function.
* ???

`__repr__` method is called:

* when user type the name of the object in a python shell (or in the BLISS shell)


By default when no `__str__` or `__repr__` methods are defined, the
`__repr__` returns the name of the class (Length) and `__str__` calls
`__repr__`.

If a class defines `__repr__` but not `__str__`, then `__repr__` is
also used when an “informal” string representation of instances of
that class is required.


    BLISS [2]: myaxis
      Out [2]: Comes from __repr__
    
    BLISS [3]: print("%r" % myaxis)
    Comes from __repr__
    
    BLISS [4]: print(myaxis)
    Comes from __str__
