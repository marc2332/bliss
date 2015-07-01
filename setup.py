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
      packages=["bliss", "bliss.config", "bliss.config.conductor", "bliss.config.conductor.web",
                "bliss.config.plugins","bliss.config.redis"],
      package_data={'beacon.redis': ['redis.conf'],
                    'beacon.plugins': ['*.html'],
                    'beacon.conductor.web': ['*.html', 'css/*.css', "js/*.js", 'css/jquery-ui/*.css', 'css/jstree/*.css']},
      scripts=["bin/beacon-server"])
