### -*- mode: Makefile; coding: utf-8 -*- ###

#############################################################################
#                                                                           #
# Copyright © 2013-2014 Helmholtz-Zentrum Dresden Rossendorf                #
# Christian Böhme <c.boehme@hzdr.de>                                        #
#                                                                           #
# This program is free software: you can redistribute it and/or modify      #
# it under the terms of the GNU General Public License as published by      #
# the Free Software Foundation, either version 3 of the License, or         #
# (at your option) any later version.                                       #
#                                                                           #
# This program is distributed in the hope that it will be useful,           #
# but WITHOUT ANY WARRANTY; without even the implied warranty of            #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
# GNU General Public License for more details.                              #
#                                                                           #
# You should have received a copy of the GNU General Public License         #
# along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                           #
#############################################################################

MAKE_CWD                    :=  $(shell pwd)

CT2_LIB_PATH                :=  lib
CT2_LIB_INC_PATH            :=  $(CT2_LIB_PATH)/include
CT2_LIB_SRC_PATH            :=  $(CT2_LIB_PATH)/src

CT2_TOOLS_PATH              :=  tools


all     :   bit2arr kmod examples


kmod    :
	make -C driver


clean   :
	make -C driver clean
	make -C examples clean
	rm -f $(CT2_TOOLS_PATH)/*.o $(CT2_DRIVER_SRC_PATH)/*_bit.c 
	rm -f $(CT2_TOOLS_PATH)/bit2arr

bit2arr :  $(CT2_TOOLS_PATH)/bit2arr.c
	$(CC) $(LDFLAGS) -o $(CT2_TOOLS_PATH)/$@ $^


examples:
	make -C examples