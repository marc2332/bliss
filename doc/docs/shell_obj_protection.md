# Object protection in BLISS command line

To protect the BLISS shell against unintentional corruption by users and to avoid the loss of object (axes, counters, controllers etc.), that are available in the session environment, a system to protect a subset of these objects is put in place.

By default all objects that are imported from the configuration during the session startup (entries in `config-objects` and `aliases` of the session’s _yaml_ configuration) are protected. However it is possible to modify the behavior during run-time.

When trying the modify an protected object (axis _roby_ in example below) one will see the following message:

```python
TEST_SESSION [1]: roby
         Out [1]: AXIS:
                       name (R): roby
                       unit (R): None
                       offset (R): 0.00000
                       backlash (R): 2.00000
                       sign (R): 1
                       steps_per_unit (R): 10000.00
                       ...                  

TEST_SESSION [2]: roby = 1
!!! === RuntimeError: roby is protected and can not be modified! === !!! ( for more details type cmd 'last_error' )

TEST_SESSION [3]: roby
         Out [3]: AXIS:
                       name (R): roby
                       unit (R): None
                       offset (R): 0.00000
                       backlash (R): 2.00000
                       sign (R): 1
                       steps_per_unit (R): 10000.00
                       ...
                  
```


### Protection on runtime
To protect or to remove the protection on the fly the two commands `protect` and `unprotect` are available from the command line.

```python
TEST_SESSION [4]: my_important_variable = 3.141
TEST_SESSION [5]: protect('my_important_variable')
TEST_SESSION [6]: my_important_variable
         Out [6]: 3.141

TEST_SESSION [7]: my_important_variable=1
!!! === RuntimeError: my_important_variable is protected and can not be modified! === !!! ( for more details type cmd 'last_error' )

TEST_SESSION [8]: unprotect('my_important_variable')
TEST_SESSION [9]: my_important_variable=1
TEST_SESSION [10]: my_important_variable
         Out [10]: 1
```

### Customization of protection in session setup _.py_ file
To add additional names to the set of protected keys from the setup file `protect` method can be used. Note: config objects are protected after setup.


```python
from bliss import is_bliss_shell

my_important_variable = 12

if is_bliss_shell():
    protect('my_important_variable')
    protect(['obj1','obj2'])
```

### Further implementation details
- `config.get` overrides the protection
```python
TEST_SESSION [15]: roby
         Out [15]: AXIS:
                        name (R): roby
                        unit (R): None
                        offset (R): 0.00000
                        ...

TEST_SESSION [16]: unprotect('roby')
TEST_SESSION [17]: roby=1
TEST_SESSION [18]: protect('roby')
TEST_SESSION [19]: roby
         Out [19]: 1

TEST_SESSION [20]: config.get('roby')
         Out [20]: AXIS:
                        name (R): roby
                        unit (R): None
                        offset (R): 0.00000
                        ...

TEST_SESSION [21]: roby
         Out [21]: AXIS:
                        name (R): roby
                        unit (R): None
                        offset (R): 0.00000
                        ...
```
- only keys that are present in the `env_dict` can be protected.
- the use of bliss in _library-mode_ is not concerned, the protection only affects the command line. However, once the command line client is initialized  `protect` and `unprotect` are available in the session _env_dict_.
