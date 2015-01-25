from distutils.core import setup

setup(name="bliss", version="0.1",
      description="Bliss",
      author="M.Guijarro (ESRF)",
      package_dir={"bliss": "bliss"},
      packages=["khoros", 'khoros.core', 'khoros.blcomponents'],
      package_data={'khoros':['*.html', '*.css', "js/*"]},
      scripts = ['bin/bliss_webserver'],) 
