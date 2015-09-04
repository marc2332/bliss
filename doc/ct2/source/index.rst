.. ct2 documentation master file, created by
   sphinx-quickstart on Wed Jul  8 09:58:50 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

P201/C208 documentation!
========================

Here are the links to the:

    * `P201 reference manual`_
    * `P201 user's manual`_
    * `C208 user's manual`_


Quickstart
----------

Eager to get started? This page gives a good introduction to ct2.
It assumes you already have ct2 installed. 
If you do not, head over to the Installation section.

A Minimal Application
~~~~~~~~~~~~~~~~~~~~~

A minimal ct2 usage looks something like this::

    import ct2

    p201 = ct2.P201()

    p201.request_exclusive_access()
    p201.reset_software()

    for i in range(10):
        print(p201.get_test_reg())


API Reference
-------------
If you are looking for information on a specific function, class or method, this part of the documentation is for you.

Contents:

.. toctree::
   :maxdepth: 2
   
   API <api.rst>
   
   
.. _ct2-benchmarks:

Benchmarks
----------

Simple measurements/benchmarks

Hardware
    Used an IPC 4 CPU 3GHz Intel; 4Gb RAM.

Linux
    Linux version 2.6.32-5-amd64 (Debian 2.6.32-45) (dannf@debian.org) (gcc version 4.3.5 (Debian 4.3.5-4) ) #1 SMP Sun May 6 04:00:17 UTC 2012

Python
    2.6.6 (r266:84292, Dec 26 2010, 22:31:48)


ct2.py benchmark
~~~~~~~~~~~~~~~~

Measures where done in ipython 1.2.1 with *timeit* utility

time to read register (`preadn(fileno, offset, n=4)`):
    **4.27 µs** (100000 loops, best of 3: 4.27 µs per loop)

time to read register integer (`card.get_counter_value(1)`):
    **5.86 µs** (100000 loops, best of 3: 5.86 µs per loop)

time to read 12 continuous registers (`preadn(fileno, offset, n=4*12)`):
    **14.1 µs (1.18 µs / register)** (100000 loops, best of 3: 14.1 µs per loop)

time to read 12 continuous registers integer (numpy array) (`card.get_counters_values(1)`):
    **18.6 µs (1.46 µs / register)** (100000 loops, best of 3: 18.6 µs per loop)

