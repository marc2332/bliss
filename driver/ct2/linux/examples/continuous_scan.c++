/* -*- mode: C++; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * ESRF C208/P201 continuous scan demo                                      *
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

#define _BSD_SOURCE
#include <sys/types.h>        // ::open(2), ::(f)stat(2), major(3), minor(3)
#include <sys/stat.h>         // ::open(2), ::(f)stat(2), S_ISCHR()
#include <sys/ioctl.h>        // ::ioctl(2)
#include <sys/mman.h>         // ::mmap(2), ::munmap(2)
#include <sys/epoll.h>        // ::epoll_(create|ctl|wait)(2)
#include <sys/signalfd.h>     // ::signalfd(2)
#include <sys/param.h>        // MAXPATHLEN

#include <fcntl.h>            // ::open(2)
#include <signal.h>           // ::sigprocmask(2), ::sigemptyset(3), ::sigaddset(3)
#include <time.h>             // ::clock_gettime(2)
#include <unistd.h>           // ::read(2), ::(f)stat(2)

// CLOCK_MONOTONIC_RAW is in /usr/include/linux/time.h
// but not in /usr/include/bits/time.h, where userland
// code searches for it, so we define it ourselves.
#if !defined CLOCK_MONOTONIC_RAW
# define CLOCK_MONOTONIC_RAW  4
#endif

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cerrno>

#include <iostream>

#include <esrf/ct2>

#include "register_transfers"


using namespace std;
using namespace esrf::ct2;


// s_si  ... scan initiation signal
// s_en  ... encoder signal
// s_t_1 ... detector 1 signal
// s_t_2 ... detector 2 signal
// c_so  ... scan origin/ramp-up/start counter
// c_i   ... displacement interval counter
// c_d   ... displacement interval size counter
// c_t_1 ... detector 1 pulse counter
// c_t_2 ... detector 2 pulse counter

// 1 kHz on s_en with d = 2000 makes for 2 seconds long displacement
// intervals.  With an f_0 of 20 MHz, and 20 MHz ÷ 10000, we obtain
// 2 kHz s_t_1 impulse rate which results in (roughly) 4000 counts
// for c_t_1 per interval.  A 20 MHz ÷ 80000 makes for 250 Hz s_t_2
// impulse rate which results in (roughly) 500 counts for c_t_2 per
// interval.

static const ct2_reg_t      en_ctrs = (1 <<  0) | // ccl 1
                                      (1 << 10) | // ccl 11
                                      (1 << 11) | // ccl 12
                                      (1 <<  1) | // ccl 2
                                      (1 <<  2);  // ccl 3
static const ct2_reg_t      dis_ctrs = (en_ctrs << 16);

static const uint8_t        f_0 = CT2_COM_GENE_CLOCK_AT_40_MHz;
static const uint8_t        wt_s_si = 0x02;     // ic 2/pulse_m
static const uint8_t        cs_s_en = 0x06;     // ic 1/pulse_m
static const uint8_t        cs_s_t_1 = 0x01;    // f_0 ÷ 10000
static const uint8_t        cs_s_t_2 = 0x00;    // f_0 ÷ 80000

static const unsigned int   n_so = 4000;        // scan origin count
static const unsigned int   n_e = 44000;        // end count
static const unsigned int   i = 20;             // displacement interval count
static const unsigned int   d = 2000;           // displacement interval size

static const char * const default_device_name = "/dev/p201";


static volatile ct2_reg_t * mmap_fifo( );
typedef int (fd_handler_type )( uint32_t );
static int device_fd_handler( uint32_t );
static int signal_fd_handler( uint32_t );


int device_fd = -1;
int signal_fd = -1;
#define MMAP_FAILURE        static_cast<ct2_reg_t *>(MAP_FAILED)
volatile ct2_reg_t * fifo = MMAP_FAILURE;
::off_t fifo_len = 0;


/**
 * Invoke as "continuous_scan [〈device-name〉]",
 * wait until the counters are enabled, and then
 * provide a rising edge on input cell 2 to start
 * the "scan".
 */

int main ( int argc, char ** argv )
{
  const char *  device_name;

  // XXX
  if ( ( i <= 0 ) || ( d <= 0 ) )
    return 1;

  // XXX
  if ( n_e != (i * d + n_so) )
    return 2;


  if ( argc > 1 )
    device_name = argv[1];
  else
    device_name = default_device_name;

  int         rv;
  ct2_reg_t   reg, source_it_b = 0;

  // Access the Device, ...
  if ( (device_fd = ::open(device_name, (O_RDWR /* | O_NONBLOCK */))) == -1 ) {
    cerr << "open(" << device_name << "): " << strerror(errno) << endl;
    return 3;
  }

  // ... lay claim to it, ...
  if ( ::ioctl(device_fd, CT2_IOC_QXA) != 0 ) {
    cerr << "ioctl(device_fd, CT2_IOC_QXA): " << strerror(errno) << endl;
    return 4;
  }

  // ... and reset it.
  if ( ::ioctl(device_fd, CT2_IOC_DEVRST) != 0 ) {
    cerr << "ioctl(device_fd, CT2_IOC_DEVRST): " << strerror(errno) << endl;
    return 5;
  }


  // Enable the device clock.
  reg = f_0;
  if ( !wrb(device_fd, ct2::com_gene, reg) )
    return 6;

  // Make sure the counters are disabled (soft_enable_disable).
  reg = dis_ctrs;
  if ( !edc(device_fd, reg) )
    return 7;

  // Configure ccl 1 aka c_so:
  // (1) clock source is s_en
  // (2) gate wide open
  // (3) started by s_si
  // (4) halted by ccl 1/egal ...
  // (5) ... while keeping its value ...
  reg = (cs_s_en << CT2_CONF_CMPT_CLK_OFF)    | // (1)
        (   0x00 << CT2_CONF_CMPT_GATE_OFF)   | // (2)
        (wt_s_si << CT2_CONF_CMPT_HSTART_OFF) | // (3)
        (   0x49 << CT2_CONF_CMPT_HSTOP_OFF)  | // (4)
        (      0 << 30)                       | // (5)
        (      1 << 31);                        // (4)
  if ( !wrb(device_fd, ct2::conf_cmpt_1, reg) )
    return 8;

  reg = n_so;
  if ( !wrb(device_fd, ct2::compare_cmpt_1, reg) )
    return 9;

  // ... and signaling its end to the outside world.
  source_it_b |= (1 << 0);

  // Configure ccl 11 aka c_i:
  // (1) clock source is ccl 12/end aka c_d/end
  // (2) gate wide open
  // (3) started by ccl 1/end aka c_so/end
  // (4) halted by ccl 11/egal ...
  // (5) ... while keeping its value ...
  reg = (0x41 << CT2_CONF_CMPT_CLK_OFF)     | // (1)
        (0x00 << CT2_CONF_CMPT_GATE_OFF)    | // (2)
        (0x31 << CT2_CONF_CMPT_HSTART_OFF)  | // (3)
        (0x53 << CT2_CONF_CMPT_HSTOP_OFF)   | // (4)
        (   0 << 30)                        | // (5)
        (   1 << 31);                         // (4)
  if ( !wrb(device_fd, ct2::conf_cmpt_11, reg) )
    return 10;

  reg = i;
  if ( !wrb(device_fd, ct2::compare_cmpt_11, reg) )
    return 11;

  // ... and signaling this to the outside world.
  source_it_b |= (1 << 10);

  // Configure ccl 12 aka c_d:
  // (1) clock source is s_en
  // (2) gate wide open
  // (3) started by ccl 1/end aka c_so/end
  // (4) reset by ccl 12/egal ...
  // (5) ... while running continuously ...
  reg = (cs_s_en << CT2_CONF_CMPT_CLK_OFF)    | // (1)
        (   0x00 << CT2_CONF_CMPT_GATE_OFF)   | // (2)
        (   0x31 << CT2_CONF_CMPT_HSTART_OFF) | // (3)
        (   0x54 << CT2_CONF_CMPT_HSTOP_OFF)  | // (4)
        (      1 << 30)                       | // (4)
        (      0 << 31);                        // (5)
  if ( !wrb(device_fd, ct2::conf_cmpt_12, reg) )
    return 12;

  reg = d;
  if ( !wrb(device_fd, ct2::compare_cmpt_12, reg) )
    return 13;

  // ... and having us tell when it wraps.
  source_it_b |= (1 << 11);

  // Configure ccl 2 aka c_t_1:
  // (1) clock source is s_t_1
  // (2) gate wide open
  // (3) started by ccl 1/end aka c_so/end
  // (4) reset by ccl 12/egal aka c_d/egal
  // (5) ... while running continuously
  reg = (cs_s_t_1 << CT2_CONF_CMPT_CLK_OFF)    | // (1)
        (    0x00 << CT2_CONF_CMPT_GATE_OFF)   | // (2)
        (    0x31 << CT2_CONF_CMPT_HSTART_OFF) | // (3)
        (    0x54 << CT2_CONF_CMPT_HSTOP_OFF)  | // (4)
        (       1 << 30)                       | // (4)
        (       0 << 31);                        // (5)
  if ( !wrb(device_fd, ct2::conf_cmpt_2, reg) )
    return 14;

  // The latch signal shall be generated from ccl 12/stop + disable
  // aka c_d/stop + disable, so that we're latching all from the same
  // source and before actually clearing the counter.
  reg = ((1 << 11) << 16);
  if ( !wrb(device_fd, ct2::sel_latch_a, reg) )
    return 15;

  // Configure ccl 3 aka c_t_2:
  // (1) clock source is s_t_2
  // (2) gate wide open
  // (3) started by ccl 1/end aka c_so/end
  // (4) reset by ccl 12/egal aka c_d/egal
  // (5) ... while running continuously
  reg = (cs_s_t_2 << CT2_CONF_CMPT_CLK_OFF)    | // (1)
        (    0x00 << CT2_CONF_CMPT_GATE_OFF)   | // (2)
        (    0x31 << CT2_CONF_CMPT_HSTART_OFF) | // (3)
        (    0x54 << CT2_CONF_CMPT_HSTOP_OFF)  | // (4)
        (       1 << 30)                       | // (4)
        (       0 << 31);                        // (5)
  if ( !wrb(device_fd, ct2::conf_cmpt_3, reg) )
    return 16;

  reg = ((1 << 11) << 0);
  if ( !wrb(device_fd, ct2::sel_latch_b, reg) )
    return 17;

  // We store the latched counter values of ccls 2 and 3 (2)
  // while it should suffice that the transfer is triggered by
  // c_t_1's latch (1).  But first and foremost, we enable the
  // transfer (3).
  reg =           ((1 << 1)  <<  0) | // (1)
        (((1 << 2)|(1 << 1)) << 16) | // (2)
                          (1 << 31);  // (3)
  if ( !wrb(device_fd, ct2::cmd_dma, reg) )
    return 18;


  // Set output cell 1's signal source to ic 1 (1) and
  // output cell 2's signal source to ic 2(2).
  reg = 0x07 << 0 |   // (1)
        0x08 << 8;    // (2)
  if ( !wrb(device_fd, p201::sel_source_output, reg) )
    return 19;

  // Set the filter configuration for both outputs.  Neither cell's signal
  // shall be inverted nor filters used.
  reg = (((0 << 4) | (0 << 3) | 0x0) << 0) |
        (((0 << 4) | (0 << 3) | 0x0) << 8);
  if ( !wrb(device_fd, p201::sel_filtre_output, reg) )
    return 20;

  // Set both output cells' levels to TTL.
  reg = (1 << 8) | (1 << 9);
  if ( !wrb(device_fd, ct2::niveau_out, reg) )
    return 21;


  // Enable input termination on all inputs except ic 9 and ic10.
  reg = (1 << 8) | (1 << 9);
  if ( !wrb(device_fd, ct2::adapt_50, reg) )
    return 22;

  // Set input cells 1's (1) and 2's (2) filter configuration
  // to short pulse capture.
  reg = (((0x0 << 3) | (0x0 << 0)) << 0) |  // (1)
        (((0x0 << 3) | (0x0 << 0)) << 5);   // (2)
  if ( !wrb(device_fd, ct2::sel_filtre_input_a, reg) )
    return 23;

  // Set input cell 1's and 2's level to TTL.
  reg = (1 << 0) | (1 << 1);
  if ( !wrb(device_fd, p201::niveau_in, reg) )
    return 24;

  // Now map the FIFO over its full length into our address space, ...
  if ( (fifo = mmap_fifo()) == MMAP_FAILURE )
    return 25;

  // ... prepare the poll infrastructure, ...
  int poll_fd;
  if ( (poll_fd = ::epoll_create1(0)) == -1 ) {
    cerr << "epoll_create1(0): " << strerror(errno) << endl;
    return 26;
  }

  struct epoll_event pev;
  pev.events = EPOLLIN | EPOLLHUP | EPOLLERR;
  pev.data.ptr = reinterpret_cast<void *>(device_fd_handler);
  if ( ::epoll_ctl(poll_fd, EPOLL_CTL_ADD, device_fd, &pev) != 0 ) {
    cerr << "epoll_ctl(poll_fd, device_fd): " << strerror(errno) << endl;
    return 27;
  }

  // ... along with signal handling, ...
  sigset_t sigmask;
  ::sigemptyset(&sigmask);
  ::sigaddset(&sigmask, SIGINT);
  ::sigaddset(&sigmask, SIGQUIT);
  ::sigaddset(&sigmask, SIGTERM);

  if ( ::sigprocmask(SIG_BLOCK, &sigmask, NULL) != 0 ) {
    cerr << "sigprocmask(SIG_BLOCK, sigmask, NULL): " << strerror(errno) << endl;
    return 28;
  }

  if ( (signal_fd = ::signalfd(-1, &sigmask, 0)) == -1 ) {
    cerr << "signalfd(-1, sigmask, 0): " << strerror(errno) << endl;
    return 29;
  }

  pev.events = EPOLLIN | EPOLLHUP | EPOLLERR;
  pev.data.ptr = reinterpret_cast<void *>(signal_fd_handler);
  if ( ::epoll_ctl(poll_fd, EPOLL_CTL_ADD, signal_fd, &pev) != 0 ) {
    cerr << "epoll_ctl(poll_fd, signal_fd): " << strerror(errno) << endl;
    return 30;
  }

  // ... and enable device interrupts with a FIFO 100 entries deep.
  if ( ::ioctl(device_fd, CT2_IOC_EDINT, 100) != 0 ) {
    cerr << "ioctl(device_fd, CT2_IOC_EDINT): " << strerror(errno) << endl;
    return 31;
  }

  // Have us generate FIFO transfer interrupts for
  // finished latch-FIFO transfers (1), associated errors (2)
  // and a fillpoint of half a FIFO (2).
  source_it_b |= (1 << 12)  | // (1)
                 (1 << 13)  | // (2)
                 (1 << 14);   // (3)
  if ( !wrb(device_fd, ct2::source_it_b, source_it_b) )
    return 32;

  // Now enable the counters.
  reg = en_ctrs;
  if ( !edc(device_fd, reg) )
    return 33;

  for ( ; ; ) {

    int poll_wait_rv;
    if ( (poll_wait_rv = ::epoll_wait(poll_fd, &pev, 1, -1)) == -1 ) {
      cerr << "epoll_wait(poll_fd): " << strerror(errno) << endl;
      return 34;
    }

    if ( poll_wait_rv == 0 ) {
      cout << "ignoring spurious epoll event" << endl;
      continue;
    }

    fd_handler_type * fdh = reinterpret_cast<fd_handler_type *>(pev.data.ptr);
    switch ( fdh(pev.events) ) {
      case 0: break;
      case 1: rv = 0; goto clean_up;
      case 2: rv = 35; goto clean_up;
      default: rv = 36; goto clean_up;
    }

  } // for ( ; ; )

clean_up:

  // Clear all interrupts we asked the Device to generate previoulsy.
  source_it_b = 0;
  if ( !wrb(device_fd, ct2::source_it_b, source_it_b) )
      return 37;

  // Disable device interrupts ...
  if ( ::ioctl(device_fd, CT2_IOC_DDINT) != 0 ) {
    cerr << "ioctl(device_fd, CT2_IOC_DDINT): " << strerror(errno) << endl;
    return 38;
  }

  // ... and disable the counters.
  reg = dis_ctrs;
  if ( !edc(device_fd, reg) )
    return 39;

  // Finally, unmap the FIFO.
  if ( ::munmap(const_cast<ct2_reg_t *>(fifo), fifo_len) != 0 ) {
    cerr << "munmap(fifo, " << fifo_len << "): " << strerror(errno) << endl;
    rv = 40;
  }

  return rv;
}


static
volatile ct2_reg_t * mmap_fifo( )
{
  struct stat stat;
  if ( ::fstat(device_fd, &stat) != 0 ) {
    cerr << "fstat(device_fd): " << strerror(errno) << endl;
    return MMAP_FAILURE;
  }

  if ( S_ISCHR(stat.st_mode) == 0 ) {
    cerr << "device_fd does not point to a character special file" << endl;
    return MMAP_FAILURE;
  }

  char sysfs_bar3_dn[MAXPATHLEN];
  size_t sysfs_bar3_dn_len = sizeof(sysfs_bar3_dn);
  int wlen = snprintf(sysfs_bar3_dn,
                      sysfs_bar3_dn_len,
                      "/sys/dev/char/%d:%d/device/resource3",
                      major(stat.st_rdev), minor(stat.st_rdev));
  if ( static_cast<size_t>(wlen) >= sysfs_bar3_dn_len ) {
    cerr << "sysfs device name " << sysfs_bar3_dn << " is apparently too long" << endl;
    return MMAP_FAILURE;
  }

  if ( ::stat(sysfs_bar3_dn, &stat) != 0 ) {
    cerr << "stat(" << sysfs_bar3_dn << "): " << strerror(errno) << endl;
    return MMAP_FAILURE;
  }

  void * addr;
  if ( (addr = ::mmap(NULL, stat.st_size,
                      PROT_READ, MAP_PRIVATE,
                      device_fd, CT2_MM_FIFO_OFF)) == MAP_FAILED ) {
    cerr << "mmap(" << stat.st_size
                    << ", device_fd, "
                    << CT2_MM_FIFO_OFF
                    << "): " << strerror(errno) << endl;
    return MMAP_FAILURE;
  }

  fifo_len = stat.st_size;

  cout << "FIFO mapped: [" << CT2_MM_FIFO_OFF
                           << ", "
                           << fifo_len << ")" << endl;

  return static_cast<volatile ct2_reg_t *>(addr);
}

static
int64_t timespec_to_ns( const struct timespec & ts )
{
  // [include/linux/time.h:timespec_to_ns()]
  return static_cast<int64_t>((ts.tv_sec * 1000L * 1000L * 1000L) + ts.tv_nsec);
}

static
int device_fd_handler( uint32_t poll_events )
{
  if ( (poll_events & (EPOLLHUP | EPOLLERR)) ) {
      cout << "epoll event other than EPOLLIN seen, bailing out" << endl;
      return 2;
  }

  struct timespec stamp;
  if ( ::clock_gettime(CLOCK_MONOTONIC_RAW, &stamp) != 0 ) {
    cerr << "clock_gettime(CLOCK_MONOTONIC_RAW): " << strerror(errno) << endl;
    return -1;
  }

  struct ct2_in in;
  if ( ::ioctl(device_fd, CT2_IOC_ACKINT, &in) != 0 ) {
    cerr << "ioctl(device_fd, CT2_IOC_ACKINT): " << strerror(errno) << endl;
    return -2;
  }

  int64_t intr_hdlr = timespec_to_ns(in.stamp);
  int64_t intr_rcpt = timespec_to_ns(stamp);

  cout << "interrupt delivery delay: " << intr_rcpt - intr_hdlr << " nanoseconds" << endl;

  if ( (in.ctrl_it & ((1 <<  0) << 12)) != 0 )
    cout << "c_so/end asserted, we have begun" << endl;

  if ( (in.ctrl_it & ((1 << 11) << 12)) != 0 )
    cout << "c_d/end asserted" << endl;

  if ( (in.ctrl_it & (1 << 25)) != 0 )
    cout << "received latch-FIFO transfer success notice" << endl;

  if ( (in.ctrl_it & (1 << 26)) != 0 )
    cout << "received FIFO half full notice" << endl;

  if ( (in.ctrl_it & (1 << 27)) != 0 )
    cout << "received latch-FIFO transfer error notice" << endl;

  ct2_reg_t reg;
  if ( !rd(device_fd, ct2::ctrl_fifo_dma, reg) )
    return -3;

  size_t fifo_fillpoint = reg & ((1 << 13) - 1);
  for ( size_t n = 0; n < fifo_fillpoint; n++ )
    printf("FIFO[%zu] = %08x\n", n, fifo[n]);

  if ( !rd(device_fd, ct2::ctrl_fifo_dma, reg) )
    return -4;

  if ( (in.ctrl_it & ((1 << 10) << 12)) == 0 )
    return 0;

  cout << "c_i/end asserted, we're done here" << endl;

  return 1;
}

static
int signal_fd_handler( uint32_t poll_events )
{
  if ( (poll_events & (EPOLLHUP | EPOLLERR)) ) {
    cout << "epoll event other than EPOLLIN seen, bailing out" << endl;
    return 2;
  }

  struct signalfd_siginfo sfd_info;
  if ( ::read(signal_fd, &sfd_info, sizeof(sfd_info)) != sizeof(sfd_info) ) {
    cerr << "read(signal_fd): " << strerror(errno) << endl;
    return -1;
  }

  const char *  signal_name = "〈signal〉";
  switch ( sfd_info.ssi_signo ) {
    case SIGINT: signal_name = "SIGINT"; break;
    case SIGQUIT: signal_name = "SIGQUIT"; break;
    case SIGTERM: signal_name = "SIGTERM"; break;
    default:
        cout << "spurious signal caught and ignored" << endl;
        return 0;
  }

  cout << signal_name << " caught, bailing out" << endl;

  return 1;
}
