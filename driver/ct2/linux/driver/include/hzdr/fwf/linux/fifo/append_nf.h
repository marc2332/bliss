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

//  HZDR_FWFI_LINUX_FIFO_APPEND_NF_H

#include <linux/stddef.h>               // true, false
#include <linux/types.h>                // bool

// assume
//  <hzdr/fwf/linux/fifo/fifo.h>
// is included


// references HFL_FIFO_IDENT(fifo_copy_entry)


/**
 * fifo_append_nf - possibly append an entry to the write end of the FIFO
 * @fifo:   FIFO to append the entry to
 * @datum:  pointer to the source object to copy the entry from
 *
 * Append a single entry to the write end of the FIFO unless the FIFO is full.
 *
 * returns: "true" if an entry was appended or "false" otherwise
 */

static inline
bool HFL_FIFO_IDENT(fifo_append_nf)( struct HFL_FIFO_IDENT(fifo) * fifo, const HFL_FIFO_ENTRY_TYPE * datum )
{
    struct HFL_FIFO_IDENT(fifo_ptr) *   w = &(fifo->w);
    HFL_FIFO_ENTRY_TYPE *               entry = w->ea_ptr + w->off;


    // Do nothing if we're full.
    if ( fifo->fillpoint >= fifo->capacity )
        return false;

    HFL_FIFO_IDENT(fifo_copy_entry)(datum, entry);

    fifo->fillpoint = fifo->fillpoint + 1;
    HFL_FIFO_IDENT(fifo_ptr_advance)(w);

    return true;
}

//  HZDR_FWFI_LINUX_FIFO_APPEND_NF_H
