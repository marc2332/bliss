import os
from distutils.core import setup

def get_packages_path():
    packages_path = ['bliss']
    for sub_package in [x for x in os.listdir('bliss') if os.path.isdir(os.path.join('bliss',x))]:
        full_package_path = os.path.join('bliss',sub_package)
        packages_path.extend((x[0] for x in os.walk(full_package_path)))
    return packages_path

setup(name="bliss", version="0.1",
      description="BeamLine Instrumentation Support Software",
      author="BCU (ESRF)",
      package_dir={"bliss": "bliss"},
      packages=get_packages_path(),
      package_data={"bliss.config.redis": ["redis.conf"],
                    "bliss.config.plugins": ["*.html"],
                    "bliss.config.conductor.web": ["*.html",
                                             "css/*.*",
                                             "css/jstree/*.*",
                                             "js/*.*",
                                             "res/*.*"],
                    'bliss.shell.web':['*.html', 'css/*.css', "js/*.js"]},
      scripts=["bin/beacon-server", "bin/bliss", 'bin/bliss_webserver'])
