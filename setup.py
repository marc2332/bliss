from distutils.core import setup

setup(name="bliss", version="0.1",
      description="ESRF Motion library",
      author="M.Guijarro, C.Guilloud, M.Perez (ESRF)",
      package_dir={"bliss": "bliss"},
      packages=["bliss", 'bliss.controllers', 'bliss.controllers.motors', 'bliss.controllers.motors.libicepap',
                'bliss.controllers.motors.libicepap.deep', 'bliss.config', 'bliss.config.motors',
                'bliss.comm', 'bliss.comm.embl', 'bliss.common'])
