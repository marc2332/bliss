// This file is part of the bliss project
//
// Copyright (c) 2015-2020 Beamline Control Unit, ESRF
// Distributed under the GNU LGPLv3. See LICENSE for more info.
#define _GNU_SOURCE
#include <poll.h>
#include <dlfcn.h>
#include <pthread.h>

typedef int (*poll_func)(struct pollfd *fds, nfds_t nfds, int timeout);
static poll_func real_poll;
static pthread_t main_thread;
static int nb_before_call_patched_poll;
static poll_func replaced_poll;

__attribute__((constructor))
static void
poll_patch_init()
{
  real_poll = dlsym(RTLD_NEXT, "poll");
  replaced_poll = NULL;
}

int poll(struct pollfd *fds, nfds_t nfds, int timeout)
{
  if(replaced_poll && pthread_self() == main_thread)
    if(nb_before_call_patched_poll <= 0)
      return replaced_poll(fds,nfds,timeout);
    else
      {
	--nb_before_call_patched_poll;
	return real_poll(fds,nfds,timeout);
      }
  else
    return real_poll(fds,nfds,timeout);
}

void set_poll_func(poll_func new_poll_func,int nb_before_call)
{
  main_thread = pthread_self();
  nb_before_call_patched_poll = nb_before_call;
  replaced_poll = new_poll_func;
}
