:orphan:

Welcome to Bliss
================

.. image:: _static/logo.png
    :alt: Bliss: beamline control and data acquisition
    :scale: 80 %
    :align: right

Welcome to Bliss |release| documentation.

Bliss is a python_ library focused on beamline control and data acquisition.

It is an acronym for BeamLine Instrumentation Support Software. It is also
the old name of the ESRF_ Beamline Control Unit (BCU).

Spolier alert: Bliss is as "easy" as::

    >>> from bliss.config.static import get_config

    >>> cfg = get_config()
    >>> energy = cfg.get('energy')
    >>> energy.move(120)
    >>> print(energy.position)
    120.0

This document is divided into different parts. Check out the
:ref:`bliss-getting-started` to learn how to
:ref:`Install Bliss <bliss-installation>` and then the head over to the
:ref:`bliss-quick-start`.

We provide also more detailed :ref:`bliss-tutorials` and a
:ref:`bliss-how-tos` that can help you with the most common tasks in
bliss.

If you want to dive into the internals of bliss, we recommend
the :ref:`bliss-api` documentation.

.. toctree::
    :maxdepth: 2

    getting_started
    tutorials
    howtos
    api
    developers_guide
    project_design
    todo
    glossary


