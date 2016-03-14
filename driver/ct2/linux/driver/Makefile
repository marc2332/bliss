### -*- mode: Makefile; coding: utf-8 -*- ###

#############################################################################
#                                                                           #
# Copyright © 2015 ESRF                                                     #
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

CT2_DRIVER_SRC_PATH         :=  src

CT2_TOOLS_PATH              :=  ../tools

ifndef KERNEL_SOURCES
ifndef TARGET_KERN
TARGET_KERN                 :=  $(shell uname -r)
endif
KERNEL_SOURCES              =   /lib/modules/$(TARGET_KERN)/build
endif

MAKE_CMD                    =   $(MAKE) -C $(KERNEL_SOURCES) M=$(MAKE_CWD)

CT2_MOD                     =   ct2.ko

OS                          =   $(shell /csadmin/common/scripts/get_os.share)
ARCH                        =   $(shell uname -m)
DRV_BASE                    =   /segfs/bliss/source/driver
DRV_MOD                     =   $(DRV_BASE)/modules
DRV_DEPOT                   =   $(DRV_MOD)/$(OS)/$(ARCH)/$(TARGET_KERN)

all     :   kmod

kmod    :   c208_bit.c p201_bit.c
	$(MAKE_CMD) modules

%_bit.c :   $(CT2_TOOLS_PATH)/%.bit
	$(CT2_TOOLS_PATH)/bit2arr $< $(CT2_DRIVER_SRC_PATH)/$@ > /dev/null

clean   :
	$(MAKE_CMD) clean

copy2depot	:
	cp $(CT2_MOD) $(DRV_DEPOT)
