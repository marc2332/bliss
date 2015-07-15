.. ct2 documentation master file, created by
   sphinx-quickstart on Wed Jul  8 09:58:50 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

P201/C208 documentation!
========================

Here is the link to the `P201 reference manual`_. 

Quickstart
----------

Eager to get started? This page gives a good introduction to ct2.
It assumes you already have ct2 installed. 
If you do not, head over to the Installation section.

A Minimal Application
#####################

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
   
   

