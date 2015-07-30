from distutils.core import setup

setup(name="bliss", version="0.1",
      description="ESRF Continuous Scan library",
      author="M. Guijarro, S. Petitdemange and BCU team (ESRF)",
      package_dir={"bliss":"bliss"},
      packages=["bliss", "bliss.acquisition", "bliss.common", "bliss.data", "bliss.data.writer", ])
