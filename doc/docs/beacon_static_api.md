# Static configuration API

## Cheatsheet

```py
>>> from bliss.config.static import get_config

>>> #load YAML tree from Beacon server and parse it
>>> #into a Python 'Config' object
>>> config = get_config() # returns Config singleton

>>> #get all existing names in config
>>> config.names_list
['object_1', 'object_2']

>>> #reload config from server
>>> config.reload()

>>> #get 'object_1' configuration
>>> object_1_config = config.get_config('object_1')
>>> object_1_config
filename:<directory_1/file_1.yml>,plugin:None,{'name': 'object_1', 'param': 42}
>>> type(object_1_config)
<class 'bliss.config.static.Node'>

>>> #access with dict interface
>>> object_1_config['param']
42
>>> object_1_config['param'] = 0
>>> #send config to server
>>> object_1_config.save()

>>> #instantiate 'object_1' object
>>> object_1 = config.get('object_1')

>>> #getting any file from the server
>>> from bliss.config.conductor.client import remote_open
>>> # file-like object
>>> with remote_open("directory_1/file_1.yml") as f:
>>>    print(f.read())
b'- !!omap\n  - name: object_1\n  - param: 0\n- !!omap\n  - name: object_2\n  - param: 43\n'
```


# To save parameters in a YAML configuration file


```yaml
name: titi
truc: much
bidule:
- titi: rouge
  toto: bleu
```

```python
from bliss.config import static
cc = static.get_config()
cc.reload()
n= cc.get("titi")
n['truc']='machin'

nn = n['bidule'][0]

type(nn)  #  <class 'bliss.config.static.Node'>

nn['titi'] = "jaune"

nn.save()  # saves "jaune" and "machin"
n.save()  # saves "jaune" and "machin"
```

resulting YAML file is:

```yaml
name: titi
truc: machin
bidule:
- titi: jaune
  toto: bleu
```


# Export temporary some objects.

Sometime you need to get some device during a certain time and doesn't
expose them as global in a session.
This is possible by using `session.temporary_config` as follow:

```
from bliss import current_session
BLISS [2]: def display_motor_position(*axis_names): 
      ...:     with current_session.temporary_config() as cfg: 
      ...:         axes = list() 
      ...:         for name in axis_names: 
      ...:             axes.append(cfg.get(name)) 
      ...:         wm(*axes)
BLISS [3]: display_motor_position('roby','robz')

             roby          robz[mm]
--------  -------  ----------------
User
 High         inf  1000000000.00000
 Current  2.00000           1.00000
 Low         -inf       -1000.00000
Offset    0.00000           0.00000

Dial
 High         inf  1000000000.00000
 Current  2.00000           1.00000
 Low         -inf       -1000.00000
BLISS [4]: wa()
Current Positions: user
                   dial


```