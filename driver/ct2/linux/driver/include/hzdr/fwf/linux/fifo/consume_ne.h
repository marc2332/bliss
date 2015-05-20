/* -*- mode: C; coding: utf-8 -*- */

/****************************************************************************
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

//  HZDR_FWFI_LINUX_FIFO_CONSUME_NE_H

#include <linux/stddef.h>               // true, false
#include <linux/types.h>                // bool

// assume
//  <hzdr/fwf/linux/fifo/fifo.h>
// is included


// references HFL_FIFO_IDENT(fifo_copy_entry)


/**
 * fifo_consume_ne - possibly remove an entry from the read end of the FIFO
 * @fifo:   FIFO to remove the entry from
 * @datum:  pointer to the target object to copy the entry into
 *
 * Read the value of and remove the entry on the read end of the FIFO unless the FIFO is empty.
 *
 * returns: "true" if the entry was read from and removed or "false" otherwise
 */

static inline
bool HFL_FIFO_IDENT(fifo_consume_ne)( struct HFL_FIFO_IDENT(fifo) * fifo, HFL_FIFO_ENTRY_TYPE * datum )
{
    struct HFL_FIFO_IDENT(fifo_ptr) *   r = &(fifo->r);
    const HFL_FIFO_ENTRY_TYPE *         entry = r->ea_ptr + r->off;


    // Do nothing if we're empty.
    if ( fifo->fillpoint <= 0 )
        return false;

    HFL_FIFO_IDENT(fifo_copy_entry)(entry, datum);

    fifo->fillpoint = fifo->fillpoint - 1;
    HFL_FIFO_IDENT(fifo_ptr_advance)(r);

    return true;
}

//  HZDR_FWFI_LINUX_FIFO_CONSUME_NE_H
