/* -*- mode: C; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * ESRF C208/P201 Kernel-Userland Device communication context              *
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

#if !defined CT2_DCC_H
#define CT2_DCC_H

#include <linux/poll.h>                 // poll_table, poll_wait()
#include <linux/sched.h>                // TASK_INTERRUPTIBLE (wake_up_interruptible())
#include <linux/slab.h>                 // kmalloc(), kfree()
#include <linux/time.h>                 // getrawmonotonic()
#include <linux/types.h>                // bool
#include <linux/wait.h>                 // wait_queue_head_t,
                                        // init_waitqueue_head(), wake_up_interruptible()

#include <hzdr/fwf/linux/dl_list.h>     // hfl_dl_(list_elem_type|list_elem_init)
#include <hzdr/fwf/linux/type_casts.h>  // hfl_const_cast()

#include "esrf/ct2.h"                   // struct ct2_in
#include "ct2-param.h"                  // ct2_in_fifo_(type|append_nf|fillpoint)


struct ct2;

/**
 * struct ct2_dcc - DCC object type
 *
 * A Device communication context aggregates all state information that we
 * associate with an open file description to a Device.
 */

#define CT2_DCC_INM_FLAGS_RCVS_INTR     (1 << 0)
#define CT2_DCC_INM_FLAGS_HAS_INQ       (1 << 1)
#define CT2_DCC_INM_FLAGS_IS_ASLEEP     (1 << 2)

struct ct2_dcc {

    hfl_dl_list_elem_type       list_elem;

    struct ct2 * const          dev;

    struct {

        wait_queue_head_t       evl;
        uint8_t                 flags;

        union {
            struct ct2_in       in;
            ct2_in_fifo_type    fifo;
        } u;

    } inm;
};


/*--------------------------------------------------------------------------*
 *                                 Methods                                  *
 *--------------------------------------------------------------------------*/


/**
 * ct2_dcc_new - allocate and initialise a new DCC
 */

static inline
struct ct2_dcc * ct2_dcc_new( gfp_t flags, struct ct2 * dev )
{
    struct ct2_dcc *    dcc;


    // [include/linux/sl(a|o|u)b_def.h:kmalloc()]
    if ( (dcc = (struct ct2_dcc * )kmalloc(sizeof(struct ct2_dcc), flags)) != NULL ) {

        hfl_dl_list_elem_init(&(dcc->list_elem));
        hfl_const_cast(struct ct2 *, dcc->dev) = dev;

        // [include/linux/wait.h:init_waitqueue_head()]
        init_waitqueue_head(&(dcc->inm.evl));
        dcc->inm.flags = 0;
        dcc->inm.u.in.ctrl_it = 0;
        // [kernel/time/timekeeping.c:getrawmonotonic()]
        getrawmonotonic(&(dcc->inm.u.in.stamp));
    }

    return dcc;
}

/**
 * ct2_dcc_rcvs_intr - ask whether we may receive interrupts from the associated Device
 */

static inline
bool ct2_dcc_rcvs_intr( const struct ct2_dcc * dcc )
{
    return ( (dcc->inm.flags & CT2_DCC_INM_FLAGS_RCVS_INTR) != 0 );
}

/**
 * ct2_dcc_has_inq - ask whether we have an INQ attached
 */

static inline
bool ct2_dcc_has_inq( const struct ct2_dcc * dcc )
{
    return ( (dcc->inm.flags & CT2_DCC_INM_FLAGS_HAS_INQ) != 0 );
}

/**
 * ct2_dcc_delete - release all resources of and associated with the DCC
 */

static inline
void ct2_dcc_delete( struct ct2_dcc * dcc )
{
    if ( ct2_dcc_has_inq(dcc) ) {
        /* ct2_in_fifo_reset(&(dcc->inm.u.fifo)); */;
    }

    // [mm/sl(a|o|u)b.c:kfree()]
    kfree(dcc);
}

/**
 * ct2_dcc_en_intr - affirm that we may receive interrupts from the associated Device
 */

static inline
void ct2_dcc_en_intr( struct ct2_dcc * dcc )
{
    dcc->inm.flags |= CT2_DCC_INM_FLAGS_RCVS_INTR;
}

/**
 * ct2_dcc_dis_intr - negative that we may receive interrupts from the associated Device
 */

static inline
void ct2_dcc_dis_intr( struct ct2_dcc * dcc )
{
    dcc->inm.flags &= ~CT2_DCC_INM_FLAGS_RCVS_INTR;

    // [include/linux/wait.h:wake_up_interruptible()]
    wake_up_interruptible(&(dcc->inm.evl));
}

/**
 * ct2_dcc_post_in - deliver an interrupt notification
 */

static inline
void ct2_dcc_post_in( struct ct2_dcc * dcc, const struct ct2_in * in )
{
    if ( ct2_dcc_has_inq(dcc) ) {

        ct2_in_fifo_append_nf(&(dcc->inm.u.fifo), in);

    } else {

        dcc->inm.u.in.ctrl_it |= in->ctrl_it;
        dcc->inm.u.in.stamp = in->stamp;
    }

    wake_up_interruptible(&(dcc->inm.evl));
}

/**
 * ct2_dcc_poll_wait - poll_wait helper
 */

static inline
void ct2_dcc_poll_wait( struct ct2_dcc * dcc, struct file * file, poll_table * pt )
{
    // [include/linux/poll.h:poll_wait()]
    poll_wait(file, &(dcc->inm.evl), pt);
}


/**
 * ct2_dcc_get_const_in_ref - obtain a read reference to the IN object of the DCC
 */

static inline
const struct ct2_in * ct2_dcc_get_const_in_ref( const struct ct2_dcc * dcc )
{
    return &(dcc->inm.u.in);
}

/**
 * ct2_dcc_mark_in_as_read - void the IN object of the DCC
 */

static inline
void ct2_dcc_mark_in_as_read( struct ct2_dcc * dcc )
{
    dcc->inm.u.in.ctrl_it = 0;
    getrawmonotonic(&(dcc->inm.u.in.stamp));
}

/**
 * ct2_dcc_inq_fillpoint - ask for the fillpoint of the INQ of the DCC
 */

static inline
ct2_size_type ct2_dcc_inq_fillpoint( const struct ct2_dcc * dcc )
{
    return ct2_in_fifo_fillpoint(&(dcc->inm.u.fifo));
}

/**
 * ct2_dcc_ins_available - ask whether there are any (new) INs available at the DCC
 */

static inline
bool ct2_dcc_ins_available( const struct ct2_dcc * dcc )
{
    if ( ct2_dcc_has_inq(dcc) )
        return ( ct2_dcc_inq_fillpoint(dcc) > 0 );
    else
        return ( dcc->inm.u.in.ctrl_it != 0 );
}


#endif  // CT2_DCC_H
