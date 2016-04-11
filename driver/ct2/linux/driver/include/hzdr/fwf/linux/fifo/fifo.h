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

//  HZDR_FWFI_LINUX_FIFO_FIFO_H

#include <linux/kernel.h>               // container_of(), max_t()
#include <linux/slab.h>                 // kmalloc(), kfree()
#include <linux/types.h>                // gfp_t, size_t

#include <hzdr/fwf/linux/arrays.h>
#include <hzdr/fwf/linux/type_casts.h>


#if !defined HFL_FIFO_ENTRY_TYPE
# error "HFL_FIFO_ENTRY_TYPE must be #define'd to a type-id that names an object type."
#endif

#if !defined HFL_FIFO_PREFIX
# define HFL_FIFO_PREFIX                hfl_
#endif

#define HFL_FIFO_IDENT0(pfx, ident)     pfx ## ident
#define HFL_FIFO_IDENT1(pfx, ident)     HFL_FIFO_IDENT0(pfx, ident)
#define HFL_FIFO_IDENT(ident)           HFL_FIFO_IDENT1(HFL_FIFO_PREFIX, ident)


/**
 * struct fifo_bhead - FIFO entry storage unit object type
 * @succ:       successor in the list of FESUs
 * @max_index:  @max_index = C - 1, where C stands for the actual number of elements in @ea
 * @ea:         (var)array with an element type of HFL_FIFO_ENTRY_TYPE
 */

struct HFL_FIFO_IDENT(fifo_bhead) {
    struct HFL_FIFO_IDENT(fifo_bhead) *     succ;
    const size_t                            max_index;
    HFL_FIFO_ENTRY_TYPE                     ea[2];
};

/**
 * fifo_bhead_new - try to allocate a FESU
 * @flags:  kmalloc() flags
 * @size:   capacity of the FESU measured in the number of FIFO entries it may hold
 *
 * returns: pointer to a FESU object with the requested capacity or "NULL" otherwise
 */

static inline
struct HFL_FIFO_IDENT(fifo_bhead) * HFL_FIFO_IDENT(fifo_bhead_new)( gfp_t flags, size_t size )
{
    struct HFL_FIFO_IDENT(fifo_bhead) *     fbh;
    size_t                                  min_ea_size, kmalloc_size;


    min_ea_size = max_t(size_t, size,
                        hfl_array_size(HFL_FIFO_ENTRY_TYPE,
                                       ((struct HFL_FIFO_IDENT(fifo_bhead) * )(NULL))->ea));
    kmalloc_size = hfl_sizeof_vamsl_struct(struct HFL_FIFO_IDENT(fifo_bhead), ea, min_ea_size);

    if ( (fbh = (struct HFL_FIFO_IDENT(fifo_bhead) * )kmalloc(kmalloc_size, flags)) != NULL ) {

        // A newly constructed FESU is its own successor.
        fbh->succ = fbh;
        hfl_const_cast(size_t, fbh->max_index) = min_ea_size - 1;
    }

    return fbh;
}

/**
 * fifo_bhead_delete - delete a FESU
 * @fbh:    pointer to the FESU object to delete
 */

static inline
void HFL_FIFO_IDENT(fifo_bhead_delete)( struct HFL_FIFO_IDENT(fifo_bhead) * fbh )
{
    kfree(fbh);
}

/**
 * struct fifo_ptr - FIFO pointer object type
 * @ea_ptr:     pointer to the  ea[]  member of a FESU
 * @off:        strictly positive offset into @ea_ptr
 */

struct HFL_FIFO_IDENT(fifo_ptr) {
    HFL_FIFO_ENTRY_TYPE *   ea_ptr;
    size_t                  off;
};

/**
 * fifo_ptr_advance - advance a FIFO pointer
 * @ptr:    FIFO pointer to advance
 */

static inline
void HFL_FIFO_IDENT(fifo_ptr_advance)( struct HFL_FIFO_IDENT(fifo_ptr) * ptr )
{
    struct HFL_FIFO_IDENT(fifo_bhead) * fbh = container_of(ptr->ea_ptr, struct HFL_FIFO_IDENT(fifo_bhead), ea[0]);


    if ( ptr->off < fbh->max_index ) {
        ptr->off = ptr->off + 1;
    } else {
        ptr->ea_ptr = &(fbh->succ->ea[0]);
        ptr->off = 0;
    }
}


/**
 * struct fifo - FIFO object type
 * @capacity:   maximum number of entries that may be held in the FIFO
 * @fillpoint:  number of entries currently held in the FIFO
 * @w:          pointer to the write end of the FIFO
 * @r:          pointer to the read end of the FIFO
 */

struct HFL_FIFO_IDENT(fifo) {
    size_t                              capacity;
    size_t                              fillpoint;
    struct HFL_FIFO_IDENT(fifo_ptr)     w, r;
};

/**
 * fifo_capacity - obtain the current capacity of a FIFO
 * @fifo:   FIFO whose capacity to obtain
 */

static inline
size_t HFL_FIFO_IDENT(fifo_capacity)( const struct HFL_FIFO_IDENT(fifo) * fifo )
{
    return fifo->capacity;
}

/**
 * fifo_fillpoint - obtain the current fillpoint of a FIFO
 * @fifo:   FIFO whose fillpoint to obtain
 */

static inline
size_t HFL_FIFO_IDENT(fifo_fillpoint)( const struct HFL_FIFO_IDENT(fifo) * fifo )
{
    return fifo->fillpoint;
}

//  HZDR_FWFI_LINUX_FIFO_FIFO_H
