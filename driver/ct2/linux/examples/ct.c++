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

  // 0. board init

  // internal clock 40 Mhz
  reg = CT2_COM_GENE_CLOCK_AT_40_MHz;
  
  if ( !wrb(device_fd, ct2::com_gene, reg) )
    return 4;  

  // 1. Configure channel 10 as master: output, counter 10 gate out, TTL

  // output 10 TTL enable
  reg = 1 << 9;

  if ( !wrb(device_fd, ct2::niveau_out, reg) )
    return 4;  
  
  // no 50 ohm adapter
  reg = 0x3FF; 
  if ( !wrb(device_fd, ct2::adapt_50, reg) )
    return 4;  

  // channel 9 and 10: no filter, no polarity
  reg = 0;
  if ( !wrb(device_fd, p201::sel_filtre_output, reg) )
    return 4;  

  // channel 10 output: counter 10 gate envelop
  reg = 0x70 << 8;
  if ( !wrb(device_fd, p201::sel_source_output, reg) )
    return 4;  

  

  // Internal clock to 1 Mhz [1us]
  
  

  return 0;
}
