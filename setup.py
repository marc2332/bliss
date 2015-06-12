from distutils.core import setup

setup(name="bliss", version="1.8",
      description="ESRF Motion library",
      author="M.Guijarro, C.Guilloud, M.Perez (ESRF) 2014-2015",
      package_dir={"bliss": "bliss"},
      packages=["bliss", 'bliss.controllers', 'bliss.controllers.motors', 'bliss.controllers.motors.libicepap',
                'bliss.controllers.motors.libicepap.deep', 'bliss.config', 'bliss.config.motors',
                'bliss.comm', 'bliss.comm.embl', 'bliss.common'])
