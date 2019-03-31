# Writing a BLISS controller

Here you can find somt tips about the wrinting of a BLISS controller.

## @autocomplete_property decorator

in many controllers the `@property` decorator is heavily used to protect certain attributes of the instance or to limit the access to read-only. When using the bliss command line interface the autocompletion will __not__ suggeste any completion based on the return value of the method underneath the property. This is a wanted behavior e.g. in case this would trigger hardware communication. There are however also usecases where a _deeper_ autocompletion is wanted. E.g. the `.counter` namespace of a controller. If implemented as `@property`

    BLISS [1]: lima_simulator.counters.

would not show any autocompletion suggestions. To enable _deeper_ autocompletion there is a special decorator called `@autocomplete_property` that can be imported via `from bliss.common.utils import autocomplete_property`. Using the `@autocomplete_property` decorator befor the `def counters(self):` method of the controller would e.g. result in 

    BLISS [1]: lima_simulator.counters.
                                      _roi1_
                                      _roi2_
                                      _bpm_

autocompletion suggestions. 

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
