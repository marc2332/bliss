from distutils.core import setup
import sys

setup(name="bliss", version="0.1",
      description="ESRF Motion library",
      author="M. Guijarro, M. Perez (ESRF)",
      package_dir={"bliss": "bliss"},
      packages=["bliss"])  # , "cool.control_objects"])
