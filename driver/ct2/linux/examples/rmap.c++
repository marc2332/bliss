/* -*- mode: C++; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * ESRF C208/P201 register access demo                                      *
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
#include <unistd.h>           // ::pread(2), ::pwrite(2)

#include <cstring>
#include <cerrno>

#include <iostream>

#include <esrf/ct2.h>

#ifndef CT2_REG_SIZE
#define CT2_REG_SIZE sizeof(ct2_reg_t)
#endif

using namespace std;

ssize_t rread(int fd, void *buf, size_t count, off_t offset) 
{
  ssize_t result = ::pread(fd, buf, count * CT2_REG_SIZE, offset * CT2_REG_SIZE);
  if (result > 0)
    result /= CT2_REG_SIZE;
  return result;
}

ssize_t rwrite(int fd, const void *buf, size_t count, off_t offset)
{
  ssize_t result = ::pwrite(fd, buf, count * CT2_REG_SIZE, offset * CT2_REG_SIZE);
  if (result > 0)
    result /= CT2_REG_SIZE;
  return result;  
}

static const char * const default_device_name = "/dev/p201";


/**
 * Invoke as "rmap [〈device-name〉]".
 */

int main ( int argc, char ** argv )
{
  const char *  device_name;
  int           device_fd;


  if ( argc > 1 )
    device_name = argv[1];
  else
    device_name = default_device_name;

  if ( (device_fd = ::open(device_name, (O_RDWR /* | O_NONBLOCK */))) == -1 ) {
    cerr << "open(" << device_name << "): " << strerror(errno) << endl;
    return 1;
  }

  
  ct2_reg_t   reg;
  size_t      offset;
  ssize_t     xfer_len;


  // read beyond the limits of the map itself
  reg = 0;
  offset = -1;
  if ( rread(device_fd, &reg, 1, offset) != 1 ) {
    cerr << "pread(-1): " << strerror(errno) << endl;
  }

  reg = 0;
  offset = CT2_RW_R2_OFF + CT2_RW_R2_LEN;
  if ( rread(device_fd, &reg, 1, offset) != 1 ) {
    cerr << "pread(CT2_RW_R2_OFF + CT2_RW_R2_LEN): " << strerror(errno) << endl;
  }


  // write to a read-only register
  reg = 0;
  offset = CT2_RW_R1_OFF + ct2_reg_offset(1, ctrl_fifo_dma);
  if ( rwrite(device_fd, &reg, 1, offset) != 1 ) {
    cerr << "pwrite(ctrl_fifo_dma): " << strerror(errno) << endl;
  }

  // write into a hole
  reg = 0;
  offset = CT2_RW_R1_OFF + ct2_reg_offset(1, rd_latch_cmpt[11]) + 1;
  if ( rwrite(device_fd, &reg, 1, offset) != 1 ) {
    cerr << "pwrite(rd_latch_cmpt[11] + 1): " << strerror(errno) << endl;
  }

  // write across a write hole
  ct2_reg_t rv1[] = { 0x0, 0x0, 0x0, 0x0 };
  offset = CT2_RW_R1_OFF + ct2_reg_offset(1, soft_out);
  if ( (xfer_len = rwrite(device_fd, &rv1[0], 4, offset)) != 4 ) {
    if ( xfer_len != -1 )
      cout << "pwrite(soft_out, 4) = " << xfer_len << endl;
    else
      cerr << "pwrite(soft_out, 4): " << strerror(errno) << endl;
  }


  // read from a write-only register
  reg = 0;
  offset = CT2_RW_R2_OFF + ct2_reg_offset(2, soft_latch);
  if ( rread(device_fd, &reg, 1, offset) != 1 ) {
    cerr << "pread(soft_latch): " << strerror(errno) << endl;
  }

  // read from a P201 hole
  reg = 0;
  offset = CT2_RW_R2_OFF + ct2_reg_offset(2, p201_sel_source_output) - 1;
  if ( rread(device_fd, &reg, 1, offset) != 1 ) {
    cerr << "pread(p201_sel_source_output - 1): " << strerror(errno) << endl;
  }

  // read from p201_test_reg
  reg = 0;
  offset = CT2_RW_R1_OFF + ct2_reg_offset(1, p201_test_reg);
  if ( rread(device_fd, &reg, 1, offset) != 1 ) {
    cerr << "pread(p201_test_reg): " << strerror(errno) << endl;
  }

  // read across a hole
  ct2_reg_t rv2[] = { 0x0, 0x0, 0x0, 0x0 };
  offset = CT2_RW_R1_OFF + ct2_reg_offset(1, p201_niveau_in);
  if ( (xfer_len = rread(device_fd, &rv2[0], 4, offset)) != 4 ) {
    if ( xfer_len != -1 )
      cout << "pread(p201_niveau_in, 4) = " << xfer_len << endl;
    else
      cerr << "pread(p201_niveau_in, 4): " << strerror(errno) << endl;
  }

  // read across a read hole
  ct2_reg_t rv3[] = { 0x0, 0x0, 0x0, 0x0, 0x0 };
  offset = CT2_RW_R2_OFF + ct2_reg_offset(2, conf_cmpt[11]);
  if ( (xfer_len = rread(device_fd, &rv3[0], 5, offset)) != 5 ) {
    if ( xfer_len != -1 )
      cout << "pread(conf_cmpt[11], 5) = " << xfer_len << endl;
    else
      cerr << "pread(conf_cmpt[11], 5): " << strerror(errno) << endl;
  }

  int device_fd_1;
  if ( (device_fd_1 = ::open(device_name, (O_RDWR /* | O_NONBLOCK */))) == -1 ) {
    cerr << "open(" << device_name << "): " << strerror(errno) << endl;
    return 2;
  }

  if ( ::ioctl(device_fd_1, CT2_IOC_QXA) != 0 ) {
    cerr << "ioctl(fd_1, CT2_IOC_QXA): " << strerror(errno) << endl;
    return 3;
  }

  // unprivileged read across a register with side effects
  ct2_reg_t rv4[] = { 0x0, 0x0, 0x0 };
  offset = CT2_RW_R1_OFF + ct2_reg_offset(1, cmd_dma);
  if ( (xfer_len = rread(device_fd, &rv4[0], 3, offset)) != 3 ) {
    if ( xfer_len != -1 )
      cout << "pread(cmd_dma, 3) = " << xfer_len << endl;
    else
      cerr << "pread(cmd_dma, 3): " << strerror(errno) << endl;
  }


  return 0;
}
