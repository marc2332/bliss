from distutils.core import setup

# dependencies:
#  - gevent
#  - redis
#  - yaml
#  - netifaces
#  - louie (or old pydispatch)
#  - nanomsg
# optional dependencies:
#  - ruamel (yaml preserving comments, style, key order)
#  - posix_ipc (use posix queues)

setup(name="beacon", version="0.1",
      description="BEAmline CONfiguration library",
      author="S. Petitdemange, M. Guijarro (ESRF)",
      package_dir={"bliss": "bliss"},
      packages=["beacon", "beacon.conductor",
                "bliss.config.plugins","bliss.config.redis"],
      package_data={'beacon.redis': ['redis.conf'],
                    'beacon.conductor': ['*.html', 'css/*.css', "js/*.js"]},
      scripts=["bin/beacon-server"])
