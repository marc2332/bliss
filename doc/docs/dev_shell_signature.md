
by default the Bliss shell does not follow `properties` for signature hints
and auto completion. This is done to avoid unwanted code evaluation.

## autocomplete_property
if code inside a property should be evaluated for completion or signature
hints the [autocomplete_property](dev_write_ctrl.md#autocomplete_property-decorator)
might help.

```python
BLISS [28]: class C():
       ...:     @property
       ...:     def a(self):
       ...:          return numpy.array(range(3))
       ...:     @autocomplete_property
       ...:     def b(self):
       ...:          return numpy.array(range(3))
BLISS [29]: c=C()
 
# for the `normal` property...
BLISS [30]: c.a(        # no signature hints
BLISS [30]: c.a.        # no completion


# for the autocomplete_property property
BLISS [30]: c.b.
              all          argsort      clip      
              any          astype       compress  
              argmax       base         conj      
              
BLISS [30]: c.b.flags.
                       aligned         carray       
                       behaved         contiguous   
                       c_contiguous    f_contiguous 
                       
BLISS [30]: c.b.astype(
                       astype(dtype, order='K', casting='unsafe', subok=True, copy=True)
```

in order for the `autocomplete_property` to work the code inside the property is
evaluated by the shell first and a second time when hitting enter! 
This means it should never contain hardware communication or tigger 
actions that e.g. change a state.


## UserNamespace and UserNamedtuple

The `UserNamespace` is a namespace that
that uses [autocomplete_property](dev_write_ctrl.md#autocomplete_property-decorator) itself. It provides a 
signature completion in the Bliss shell also for its members.

To illustrate the usecase, fist an example what SimpleNamespace,
namedtuple or any other class that uses *normal* properties would do:

```python
BLISS [11]: from types import SimpleNamespace
BLISS [12]: s=SimpleNamespace(**{"a":a})
BLISS [13]: s.a(          # no signature suggestion in shell
```
the equivalent behaviour can be seen in a self-written class
as well

```python
BLISS [21]: class D():
       ...:     def a(self,kwarg=13):
       ...:         print(a)
       ...:     @property
       ...:     def b(self):
       ...:         return a
       ...:     @autocomplete_property
       ...:     def c(self):
       ...:         return a

BLISS [22]: d=D()
BLISS [23]: d.a(
                a(kwarg=13)        # signature suggestion in shell
BLISS [23]: d.b(
                                   # no signature suggestion in shell
                                   # because the code in the property
                                   # is not evaluated for the shell
                                   # signature completion
   BLISS [20]: d.c(
                a(self, kwarg=13)  # signature suggestion in shell
                               
```

with the UserNamespace there is also a signature hint also for
the properties / members fo the namespace

```python
BLISS [1]: from bliss.common.utils import UserNamespace
BLISS [2]: def b(self,kwarg=13):
      ...:     print("toto")
BLISS [4]: c=UserNamespace({"b":b})
BLISS [5]: c.b(
              b(self, kwarg=13)   # signature suggestion in shell
```
in analogy to the `namedtuple` there is also `UserNamedtuple`

```python
BLISS [1]: from bliss.common.utils import UserNamedtuple
BLISS [2]: Ntup  = UserNamedtuple("ntup","a,b")
BLISS [3]: def a(self,kwarg=13):
      ...:     print("toto")
BLISS [4]: nt=Ntup(a,1)
BLISS [5]: nt.a(
                 a(self, kwarg=13) # signature completion
```
