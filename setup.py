from distutils.core import setup

setup(name="bliss", version="0.1",
      description="ESRF Motion library",
      author="M. Guijarro, M. Perez (ESRF)",
      package_dir={"bliss": "bliss"},
      packages=["bliss", 'bliss.controllers.motors', 'bliss.config.motors', 'bliss.comm'])  # , "cool.control_objects"])
