/* -*- mode: C++; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * ESRF C208/P201 exclusive access demo                                     *
 *                                                                          *
 * Copyright © 2014 Helmholtz-Zentrum Dresden Rossendorf                    *
 * Christian Böhme <c.boehme@hzdr.de>                                       *
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
#include <unistd.h>           // ::close(2), ::dup(2)

#include <cstring>
#include <cerrno>

#include <iostream>

#include <esrf/ct2.h>


using namespace std;


static const char * const default_device_name = "/dev/p201";


/**
 * Invoke as "xaccess [〈device-name〉]".
 */

int main ( int argc, char ** argv )
{
  const char *  device_name;
  int           device_fd_1, device_fd_2, device_fd_3, device_fd_4;


  if ( argc > 1 )
    device_name = argv[1];
  else
    device_name = default_device_name;

  if ( (device_fd_1 = ::open(device_name, (O_RDWR /* | O_NONBLOCK */))) == -1 ) {
    cerr << "open(" << device_name << "): " << strerror(errno) << endl;
    return 1;
  }

  if ( (device_fd_2 = ::open(device_name, (O_RDWR /* | O_NONBLOCK */))) == -1 ) {
    cerr << "open(" << device_name << "): " << strerror(errno) << endl;
    return 2;
  }


  // both fd_1 and fd_2 (try to) relinquish exclusive access to the
  // Device, which neither of them had
  if ( ::ioctl(device_fd_1, CT2_IOC_LXA) != 0 )
    cerr << "ioctl(fd_1, CT2_IOC_LXA): " << strerror(errno) << endl;

  if ( ::ioctl(device_fd_2, CT2_IOC_LXA) != 0 )
    cerr << "ioctl(fd_2, CT2_IOC_LXA): " << strerror(errno) << endl;


  // fd_1 claims exclusive access to the Device, while fd_2 fails
  // on all accounts, until fd_1 returns the Device to the public
  if ( ::ioctl(device_fd_1, CT2_IOC_QXA) != 0 )
    cerr << "ioctl(fd_1, CT2_IOC_QXA): " << strerror(errno) << endl;

  if ( ::ioctl(device_fd_2, CT2_IOC_QXA) != 0 )
    cerr << "ioctl(fd_2, CT2_IOC_QXA): " << strerror(errno) << endl;

  if ( ::ioctl(device_fd_2, CT2_IOC_LXA) != 0 )
    cerr << "ioctl(fd_2, CT2_IOC_LXA): " << strerror(errno) << endl;

  if ( (device_fd_3 = ::dup(device_fd_1)) == -1 )
    cerr << "dup(fd_1): " << strerror(errno) << endl;

  if ( ::close(device_fd_1) != 0 )
    cerr << "close(fd_1): " << strerror(errno) << endl;

  if ( ::ioctl(device_fd_3, CT2_IOC_LXA) != 0 )
    cerr << "ioctl(fd_3, CT2_IOC_LXA): " << strerror(errno) << endl;


  // dito, but for fd_2 vs. fd_3
  if ( ::ioctl(device_fd_2, CT2_IOC_QXA) != 0 )
    cerr << "ioctl(fd_2, CT2_IOC_QXA): " << strerror(errno) << endl;

  if ( (device_fd_4 = ::dup(device_fd_2)) == -1 )
    cerr << "dup(fd_2): " << strerror(errno) << endl;

  if ( ::ioctl(device_fd_4, CT2_IOC_QXA) != 0 )
    cerr << "ioctl(fd_4, CT2_IOC_QXA): " << strerror(errno) << endl;

  if ( ::ioctl(device_fd_4, CT2_IOC_LXA) != 0 )
    cerr << "ioctl(fd_4, CT2_IOC_LXA): " << strerror(errno) << endl;

  if ( ::ioctl(device_fd_2, CT2_IOC_LXA) != 0 )
    cerr << "ioctl(fd_2, CT2_IOC_LXA): " << strerror(errno) << endl;


  // repeat the first two attempts
  if ( ::ioctl(device_fd_3, CT2_IOC_LXA) != 0 )
    cerr << "ioctl(fd_3, CT2_IOC_LXA): " << strerror(errno) << endl;

  if ( ::ioctl(device_fd_2, CT2_IOC_LXA) != 0 )
    cerr << "ioctl(fd_2, CT2_IOC_LXA): " << strerror(errno) << endl;


  return 0;
}
