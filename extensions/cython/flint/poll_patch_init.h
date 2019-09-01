typedef int (*poll_func)(struct pollfd *fds, nfds_t nfds, int timeout);

int poll_patch_init(poll_func,int);
