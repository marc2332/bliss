.. _bliss-getting-started:

Getting Started
===============

.. _bliss-installation:

Installation
------------

Bliss is easy to install::

    $ pip install blisslib

Setup
~~~~~

You can of course use bliss as a standalone library. If that is your case then
you can skip ahead to the :ref:`bliss-quick-start`.

One of the powers of bliss is it's centralized configuration system.

The setup of the bliss configuration consists of starting a beacon server that
serves bliss configuration system (which is just a tree of YAML_ files). The
server will serve several purposes:

* serve bliss configuration requests
* spawn a private redis_ server (so you will need to have redis-server installed
  on your machine)
* spawn a web server (optional)
* spawn a tango database server (optional).

The bliss configuration system consists of s tree of YAML_ files. You can find
examples in the bliss distribution in :file:`examples/configuration`.

You will need to pass the root of this configuration as a parameter to the server::

    $ beacon_server --db_path=~/local/beamline_configuration

On non development environments, were your subnet might have more than one
running beacon server, it is also a good idea to fix the bliss configuration
server port number (otherwiseby default, bliss server will just choose the first
free port it finds)::

    $ beacon_server --db_path=~/local/beamline_configuration --port=25000

Clients will then need to setup their BEACON_HOST to point to <machine>:<port>
(Example: `id31:25000`)

You might also want to activate the web configuration UI. Just choose a free
port::

    $ beacon_server --db_path=~/local/beamline_configuration --port=25000 --webapp_port=9030

(To access the web page just type <machine>:<port> on your browser. Example:
`http://id31:9030`)

Additionally, in case you use TANGO_ and you want to centralize the TANGO_
configuration, Bliss configuration server is also able to provide a full TANGO_
database server service that integrates nicely with the bliss YAML_
configuration. To start this service you just need to provide the TANGO_ port
that you want the TANGO_ database server to serve::

    $ beacon_server --db_path=~/local/beamline_configuration --port=25000 --webapp_port=9030 --tango_port=20000

... and update your TANGO_HOST environment variable accordingly.

On an ESRF beamline
~~~~~~~~~~~~~~~~~~~

.. todo:: write ESRF beamline installation


.. _bliss-quick-start:

Quick Start
-----------

To access bliss from a python console (example of using the bliss
:class:`~bliss.comm.tcp.Socket` class connecting to an :term:`IcePAP`)::

    >>> from bliss.comm.tcp import Socket
    >>> sock = Socket('icebcu2.esrf.fr', 5000)
    >>> sock.write_readline('?VELOCITY 1\n')
    '?VELOCITY 10000'

The next example will require a running bliss configuration server and
assumes the following YAML_ configuration is present:

.. literalinclude:: examples/config/motion.yml
   :language: yaml
   :caption: ./motion.yml
 
Accessing the configured elements from python is easy::

    >>> from bliss.config.static import get_config

    >>> # access the bliss configuration object
    >>> config = get_config()

    >>> # see all available object names
    >>> config.names_list
    ['mock1', 'slit1', 's1f', 's1b', 's1u', 's1d', 's1vg', 's1vo', 's1hg', 's1ho']

    >>> # get a hold of motor 's1vo'
    >>> s1vo = config.get('s1vo')

    >>> s1vo
    <bliss.common.axis.Axis at 0x7f94de365790>

    >>> s1b.position()
    0.0

    >>> s1b.move(90)

    >>> s1b.position()
    90.0

