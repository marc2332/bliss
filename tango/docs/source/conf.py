# -*- coding: utf-8 -*-

# Imports
import sys
import os
# To find device doc extension
sys.path.insert(0, os.path.abspath('..'))
# To find CT2 module
sys.path.insert(0, os.path.abspath('../..'))

# Configuration
extensions = ['sphinx.ext.autodoc', 'devicedoc']
master_doc = 'index'

# Data
project = u'CT2'
copyright = u'2015, Tango Controls'
