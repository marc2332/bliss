"""Repository of controllers

Here you will find the complete catalog of available Bliss controllers.

Three main controller subsystems have been implemented so far:

* :mod:`~bliss.controllers.motors`
* :mod:`~bliss.controllers.temperature`
* :mod:`~bliss.controllers.regulation`

All other controllers have too much specific functionality to be categorized.
This may change in the future when more controllers patterns are discovered
and their common API and functionality can be determined

.. autosummary::
    :toctree:

    actuator
    counter
    correlator
    ct2
    ebv
    emh
    expression_based_calc
    flex
    gasrig
    keithley
    keithley428
    keithley_scpi_mapping
    keller
    id31
    lima
    matt
    mca
    mcce
    motor
    motors
    multiplepositions
    multiplexer
    multiplexerswitch
    musst
    mx
    nano_bpm
    opiom
    pepu
    regulator
    regulation
    rontec
    simulation_actuator
    simulation_calc_counter
    simulation_counter
    simulation_diode
    speedgoat
    tango_attr_as_counter
    tango_shutter
    tango_tfg
    temp
    temperature
    tflens
    transfocator
    transmission
    wago
    white_beam_attenuator
"""
