### -*- mode: Makefile; coding: utf-8 -*- ###

#############################################################################
#                                                                           #
# Copyright © 2014 Helmholtz-Zentrum Dresden Rossendorf                     #
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

TARGET_KERN     :=  $(shell uname -r)
LINUX_SRC       ?=  /lib/modules/$(TARGET_KERN)/source
KMOD_ROOT       ?=  ..


EXAMPLES        =   continuous_scan \
                    rmap \
                    xaccess \
                    ct \
                    test_reg

CXX             =   g++ -g
LD              =   $(CXX)

INC_DIRS        =   -I $(LINUX_SRC)/include \
                    -I $(KMOD_ROOT) \
                    -I $(KMOD_ROOT)/lib/include \
                    -I .

LIB_DIRS        =

CPPFLAGS        +=  $(INC_DIRS)

CXXFLAGS        +=  -D_REENTRANT -std=c++0x \
                    -Wall

LDFLAGS         +=  $(LIB_DIRS) -lrt



all : $(EXAMPLES)

clean :
	rm -f *.o $(EXAMPLES)


% : %.o
	$(LD) $^ -o $@ $(LDFLAGS)

%.o : %.c++
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) -c $<
