from distutils.core import setup

setup(name="bliss", version="0.1",
      description="Bliss",
      author="M.Guijarro (ESRF)",
      package_dir={"bliss": "bliss"},
      packages=["khoros", 'khoros.core', 'khoros.interpreter', 'khoros.blcomponents'],
      package_data={'bliss':['shell/web/*.html', 'shell/web/css/*.css', "shell/web/js/*.js"]},
      scripts = ['bin/bliss_webserver'],) 
