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
  reg = CT2_COM_GENE_CLOCK_AT_100_MHz;
  
  if ( !wrb(device_fd, ct2::com_gene, reg) )
    return 4;  

  // 1. Configure channel 10 as GATE-OUT: output, counter 10 gate out, TTL

  // output 10 TTL enable
  reg = 1 << 9;

  if ( !wrb(device_fd, ct2::niveau_out, reg) )
    return 5;  
  
  // no 50 ohm adapter
  reg = 0x3FF; 
  if ( !wrb(device_fd, ct2::adapt_50, reg) )
    return 6;  

  // channel 9 and 10: no filter, no polarity
  reg = 0;
  if ( !wrb(device_fd, p201::sel_filtre_output, reg) )
    return 7;  

  // channel 10 output: counter 10 gate envelop
  reg = 0x70 << 8;
  if ( !wrb(device_fd, p201::sel_source_output, reg) )
    return 8;  

  // 2. Counter 10 as master

  // Internal clock to 1 Mhz [1us], Gate=1, Soft Start, HardStop on CMP, 
  // Reset on Hard/SoftStop, Stop on HardStop
  reg = 0x03 | (0 << 7) | (0 << 13) | (0x52 << 20) | (1 << 30) | (1 << 31);
  if ( !wrb(device_fd, p201::conf_cmpt_10, reg) )
    return 9;  

  // Latch on Counter 10 HardStop 
  reg = (0x200 << 16);
  if ( !wrb(device_fd, p201::sel_latch_e, reg) )
    return 10;  

  // Counter 10 will count 1 sec
  reg = 1000 * 1000;
  if ( !wrb(device_fd, p201::compare_cmpt_10, reg) )
    return 11;  

  ct2_reg_t count, latch, status;
  unsigned retries;

  retries = 0;
  do {
    // SoftStart on Counter 10
    reg = 0x200;
    if ( !wr(device_fd, p201::soft_start_stop, reg) )
      return 12;  

    if ( !rd(device_fd, p201::rd_ctrl_cmpt, status) )
      return 12;  

    // Verify on Counter 10
    retries++;
  } while ((status & (0x200 << 16)) == 0);

  printf("Started after %d start(s)\n", retries);

  while (1) {
    if ( ::pread(device_fd, &count, 1, r_reg_off(p201::rd_cmpt_10)) != 1 )
      return 13;  

    if ( ::pread(device_fd, &latch, 1, r_reg_off(p201::rd_latch_cmpt_10)) != 1 )
      return 14;  

    if ( ::pread(device_fd, &status, 1, r_reg_off(p201::rd_ctrl_cmpt)) != 1 )
      return 15;  

    bool end = ((status & (0x200 << 16)) == 0);
    if (end)
      break;
    printf("%010u   %010u    0x%08x\r", count, latch, status);

  }

  printf("\n%010u   %010u    0x%08x\n", count, latch, status);

  // SoftDisable on Counter 10
  reg = (0x200 << 16);
  if ( !wr(device_fd, p201::soft_enable_disable, reg) )
    return 16;  

  if ( !rd(device_fd, p201::rd_ctrl_cmpt, status) )
    return 17;  

  return 0;
}
