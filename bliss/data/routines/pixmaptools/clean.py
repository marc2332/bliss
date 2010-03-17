#!/usr/bine/env python

import os
import os.path

dont_rm_files = ['pixmaptools.sip','pixmaptools_io.cpp','pixmaptools_io.h',
                 'pixmaptools_lut.cpp','pixmaptools_stat.h','pixmaptools_stat.cpp',
		 'pixmaptools_lut_sse.c','pixmaptools_lut_sse.h','pixmaptools_lut.h',
                 'pixmaptoolsconfig.py.in','configure.py','clean.py','.gitignore']

for root,dirs,files in os.walk('.') :
    for file_name in files :
        if file_name not in dont_rm_files :
            os.remove(os.path.join(root,file_name))
    break
