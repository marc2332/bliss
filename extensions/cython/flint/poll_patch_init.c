#define _GNU_SOURCE
#include <poll.h>
#include <dlfcn.h>
#include "poll_patch_init.h"

typedef int (*set_poll_func)(poll_func,int);

int poll_patch_init(poll_func new_func,int nb_before_call)
{
  set_poll_func set_poll = dlsym(RTLD_DEFAULT, "set_poll_func");
  if(set_poll) set_poll(new_func,nb_before_call);
  return !!set_poll;
}
