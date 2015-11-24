__all__ = ['get_interface']

from ._serial import Serial
from .gpib import Gpib
from .tcp import Tcp

__INTERFACES = dict(serial=Serial, gpib=Gpib, tcp=Tcp)

def get_interface(*args, **kwargs):
    """
    Create interface from args, kwargs.
    Useful to use in a __init__ to parse arguments and keyword arguments
    with interface connection.

    Returns Interface, args, kwargs. Returned args and kwargs are the non
    consumed arguments.

    Example of usage::

        from ... import BaseDevice
        from bliss.comm.util import get_interface

        class Lecroy(BaseDevice):

            def __init__(self, *args, **kwargs):
                interface, args, kwargs = get_interface(*args, **kwargs)
                self.interface = interface
                super(Lecroy, self).__init__(*args, **kwargs)
    """
    if 'interface' in kwargs:
        interface = kwargs.pop('interface')
    else:
        if args:
            interface, args = args[0], args[1:]
        else:
            for iname, iclass in __INTERFACES.items():
                if iname in kwargs:
                    ikwargs = kwargs.pop(iname)
                    if isinstance(ikwargs, dict):
                        interface = iclass(**ikwargs)
                    else:
                        interface = ikwargs
                    break
            else:
                raise RuntimeError("Cannot find proper interface")
    return interface, args, kwargs
