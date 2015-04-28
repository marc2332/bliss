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


##############################################################################
#                            BUILD OPTIONS BEGIN                             #
##############################################################################


CT2_MAKE_DEBUG_VERSION      ?=  yes
CT2_MAP_IOPORTS_TO_IOMEM    ?=  no

CT2_HZDR_INC_PATH           ?=  $(MAKE_CWD)
CT2_BLISS_ROOT              ?=  $(MAKE_CWD)
CT2_BLISS_INC_PATH          ?=  $(CT2_BLISS_ROOT)/source/driver/linux-2.6/ct2/include
CT2_BLISS_SRC_PATH          ?=  $(CT2_BLISS_ROOT)/source/driver/linux-2.6/ct2/src


##############################################################################
#                             BUILD OPTIONS END                              #
##############################################################################


NAME                        :=  ct2
obj-m                       :=  $(NAME).o


# [scripts/Makefile.build]
EXTRA_CFLAGS                +=  -I$(CT2_BLISS_INC_PATH)
EXTRA_CFLAGS                +=  -I$(CT2_HZDR_INC_PATH)

ifeq ($(CT2_MAKE_DEBUG_VERSION), yes)
EXTRA_CFLAGS                +=  -D CT2_DEBUG
else ifneq ($(CT2_MAKE_DEBUG_VERSION), no)
    $(error CT2_MAKE_DEBUG_VERSION can hold either "yes" or "no")
endif

ifeq ($(CT2_MAP_IOPORTS_TO_IOMEM), yes)
EXTRA_CFLAGS                +=  -D CT2_MAP_IOPORTS_TO_IOMEM
else ifneq ($(CT2_MAP_IOPORTS_TO_IOMEM), no)
    $(error CT2_MAP_IOPORTS_TO_IOMEM can hold either "yes" or "no")
endif


ifndef KERNEL_SOURCES
ifndef TARGET_KERN
TARGET_KERN                 :=  $(shell uname -r)
endif
KERNEL_SOURCES              =   /lib/modules/$(TARGET_KERN)/build
endif

MAKE_CMD                    =   $(MAKE) -C $(KERNEL_SOURCES) M=$(MAKE_CWD)


all     :   kmod


kmod    :   c208_bit.c p201_bit.c
	$(MAKE_CMD) modules


clean   :
	$(MAKE_CMD) clean
	rm -f *.o *_bit.c bit2arr


%_bit.c :   $(CT2_BLISS_SRC_PATH)/%.bit bit2arr
	bit2arr $< $@ > /dev/null


%       ::  $(CT2_BLISS_SRC_PATH)/%.c
	$(CC) $(LDFLAGS) -o $@ $^
