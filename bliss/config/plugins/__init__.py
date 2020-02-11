"""
.. autosummary::
   :toctree:

   _ct2
   beamline
   bliss
   comm
   ct2
   default
   emotion
   keithley
   khoros
   regulation
   session
   temperature
   utils
"""
__all__ = []


def _init_module():
    import os

    for root, dirs, files in os.walk(__path__[0], followlinks=True):
        for file_name in files:
            if file_name.startswith("__"):
                continue
            base, ext = os.path.splitext(file_name)
            if ext == ".py":
                subdir = root[len(__path__[0]) + 1 :]
                if subdir:
                    base = "%s.%s" % (subdir, base)
                __all__.append(base)


_init_module()
