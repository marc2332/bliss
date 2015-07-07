/* -*- mode: C++; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * ESRF C208/P201 register access demo                                      *
 *                                                                          *
 * Copyright © 2015 ESRF                                                    *
 *                                                                          *
 * This program is free software: you can redistribute it and/or modify     *
 * it under the terms of the GNU General Public License as published by     *
 * the Free Software Foundation, either version 3 of the License, or        *
 * (at your option) any later version.                                      *
 *                                                                          *
 * This program is distributed in the hope that it will be useful,          *
 * but WITHOUT ANY WARRANTY; without even the implied warranty of           *
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            *
 * GNU General Public License for more details.                             *
 *                                                                          *
 * You should have received a copy of the GNU General Public License        *
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.    *
 *                                                                          *
 ****************************************************************************/

#include <sys/types.h>        // ::open(2)
#include <sys/stat.h>         // ::open(2)
#include <sys/ioctl.h>        // ::ioctl(2)

#include <fcntl.h>            // ::open(2)
#include <unistd.h>           // ::pread(2), ::pwrite(2)

#include <cstring>
#include <cerrno>

#include <iostream>

#include <esrf/ct2>

#include "register_transfers"

using namespace std;
using namespace esrf::ct2;

static const char * const default_device_name = "/dev/p201";


/**
 * Invoke as "ct [〈device-name〉]".
 */

int main ( int argc, char ** argv )
{
  const char *  device_name;
  int           device_fd;


  if ( argc > 1 )
    device_name = argv[1];
  else
    device_name = default_device_name;

  // Access the Device, ...
  if ( (device_fd = ::open(device_name, (O_RDWR /* | O_NONBLOCK */))) == -1 ) {
    cerr << "open(" << device_name << "): " << strerror(errno) << endl;
    return 1;
  }

  // ... lay claim to it, ...
  if ( ::ioctl(device_fd, CT2_IOC_QXA) != 0 ) {
    cerr << "ioctl(device_fd, CT2_IOC_QXA): " << strerror(errno) << endl;
    return 2;
  }

  // ... and reset it.
  if ( ::ioctl(device_fd, CT2_IOC_DEVRST) != 0 ) {
    cerr << "ioctl(device_fd, CT2_IOC_DEVRST): " << strerror(errno) << endl;
    return 3;
  }

  ct2_reg_t reg;

  // initialize test_reg with value 1
  reg = 1;
  if ( !wr(device_fd, p201::test_reg, reg ) )
    return 1;
  
  // read back 5 times: 1, 2, 4, 8, 16
  for(int i = 0; i < 5; ++i) {
    if ( !rd(device_fd, p201::test_reg, reg) )
      return 2;  
    printf("%0u\n", reg);
  }    

  return 0;
}
