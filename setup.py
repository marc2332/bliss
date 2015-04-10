from distutils.core import setup

setup(name="bliss", version="0.1",
      description="Bliss",
      author="M.Guijarro (ESRF)",
      package_dir={"bliss": "bliss"},
      packages=["bliss", "bliss.common", "bliss.shell", "bliss.shell.interpreter", "bliss.controllers", "bliss.shell.web",
                'bliss.comm', 'bliss.comm.gpib'],
      package_data={'bliss':['shell/web/*.html', 'shell/web/css/*.css', "shell/web/js/*.js"]},
      scripts = ['bin/bliss_webserver'],) 
