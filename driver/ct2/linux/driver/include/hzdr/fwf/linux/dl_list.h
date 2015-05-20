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

#if !defined HZDR_FWF_LINUX_DL_LIST_H
#define HZDR_FWF_LINUX_DL_LIST_H

#include <linux/list.h>                 // struct list_head, INIT_LIST_HEAD(), list_+()
#include <linux/stddef.h>               // offsetof()
#include <linux/types.h>                // bool, size_t, uintptr_t

#include <hzdr/fwf/linux/type_casts.h>


typedef struct list_head                hfl_dl_list_type;
typedef struct list_head                hfl_dl_list_elem_type;


/**
 * hfl_dl_list_init - initialise a doubly-linked list
 * @l:  expression of type "pointer to hfl_dl_list_type"
 */

static inline
void hfl_dl_list_init( hfl_dl_list_type * l )
{
    // [include/linux/list.h:INIT_LIST_HEAD()]
    INIT_LIST_HEAD(l);
}

/**
 * hfl_dl_list_elem_init - initialise @e for inclusion into a doubly-linked list
 * @e:  expression of type "pointer to hfl_dl_list_elem_type"
 */

static inline
void hfl_dl_list_elem_init( hfl_dl_list_elem_type * e )
{
    INIT_LIST_HEAD(e);
}

/**
 * hfl_dl_list_elem_is_initialised - test whether @e is properly initialised for inclusion into a doubly-linked list
 * @e:  expression of type "pointer to const hfl_dl_list_elem_type"
 *
 * returns: "true" if @e is properly initialised or "false" otherwise
 */

static inline
bool hfl_dl_list_elem_is_initialised( const hfl_dl_list_elem_type * e )
{
    // [include/linux/list.h:list_empty_careful()]
    return list_empty_careful(e);
}

/**
 * hfl_dl_list_is_empty - test whether a doubly-linked list is empty
 * @l:  expression of type "pointer to const hfl_dl_list_type"
 *
 * returns: "true" if @l is empty or "false" otherwise
 */

static inline
bool hfl_dl_list_is_empty( const hfl_dl_list_type * l )
{
    // [include/linux/list.h:list_empty_careful()]
    return list_empty_careful(l);
}

/**
 * hfl_dl_list_length - determine the number of elements in in a doubly-linked list
 * @l:  expression of type "pointer to const hfl_dl_list_type"
 *
 * returns: the number of elements in @l as a &size_t
 */

static inline
size_t hfl_dl_list_length( const hfl_dl_list_type * l )
{
    hfl_dl_list_elem_type *     x;
    size_t                      count = 0;


    // [include/linux/list.h:list_for_each()]
    list_for_each(x, l) { count = count + 1; }

    return count;
}

/**
 * hfl_dl_list_append_elem - append @e to the doubly-linked list @l
 * @l:  expression of type "pointer to hfl_dl_list_type"
 * @e:  expression of type "pointer to hfl_dl_list_elem_type"
 */

static inline
void hfl_dl_list_append_elem( hfl_dl_list_type * l, hfl_dl_list_elem_type * e )
{
    // [include/linux/list.h:list_add_tail()]
    list_add_tail(e, l);
}

/**
 * hfl_dl_list_append_elem_check - append @e to the doubly-linked list @l if @e is properly initialised
 * @l:  expression of type "pointer to hfl_dl_list_type"
 * @e:  expression of type "pointer to hfl_dl_list_elem_type"
 *
 * returns: copy of @l if @e was properly initialised or "NULL" otherwise
 */

static inline
hfl_dl_list_type * hfl_dl_list_append_elem_check( hfl_dl_list_type * l, hfl_dl_list_elem_type * e )
{
    if ( !hfl_dl_list_elem_is_initialised(e) )
        return NULL;

    hfl_dl_list_append_elem(l, e);

    return l;
}

/**
 * hfl_dl_list_prepend_elem - prepend @e to the doubly-linked list @l
 * @l:  expression of type "pointer to hfl_dl_list_type"
 * @e:  expression of type "pointer to hfl_dl_list_elem_type"
 */

static inline
void hfl_dl_list_prepend_elem( hfl_dl_list_type * l, hfl_dl_list_elem_type * e )
{
    // [include/linux/list.h:list_add()]
    list_add(e, l);
}

/**
 * hfl_dl_list_prepend_elem_check - prepend @e to the doubly-linked list @l if @e is properly initialised
 * @l:  expression of type "pointer to hfl_dl_list_type"
 * @e:  expression of type "pointer to hfl_dl_list_elem_type"
 *
 * returns: copy of @l if @e was properly initialised or "NULL" otherwise
 */

static inline
hfl_dl_list_type * hfl_dl_list_prepend_elem_check( hfl_dl_list_type * l, hfl_dl_list_elem_type * e )
{
    if ( !hfl_dl_list_elem_is_initialised(e) )
        return NULL;

    hfl_dl_list_prepend_elem(l, e);

    return l;
}

/**
 * hfl_dl_list_remove_elem - remove an element from a doubly-linked list
 * @dllist: expression of type "pointer to hfl_dl_list_type"
 * @object: expression of type "pointer to @type"
 * @type:   type-name specifying a structure type
 * @member: identifier naming a member of type "hfl_dl_list_elem_type" in @type
 *
 * returns: copy of @object if it was found in @dllist or "NULL" otherwise
 */

#define hfl_dl_list_remove_elem(dllist, object, type, member)   ((type * )hfl__dl_list_re((dllist), (object), offsetof(type, member)))

static inline
void * hfl__dl_list_re( hfl_dl_list_type * dllist, void * container, size_t offset )
{
    hfl_dl_list_elem_type *     x;


    list_for_each(x, dllist) {
        // cf. [include/linux/stddef.h:offsetof()]
        if ( x == ((hfl_dl_list_elem_type * )(((uintptr_t )container) + offset)) ) {
            // [include/linux/list.h:list_del()]
            list_del(x);
            return container;
        }
    }

    return NULL;
}

/**
 * hfl_dl_list_find_elem - locate an element in a doubly-linked list
 * @dllist: expression of type "pointer to const hfl_dl_list_type"
 * @object: expression of type "pointer to @type"
 * @type:   type-name specifying a structure type
 * @member: identifier naming a member of type "hfl_dl_list_elem_type" in @type
 *
 * returns: copy of @object if it was found in @dllist or "NULL" otherwise
 */

#define hfl_dl_list_find_elem(dllist, object, type, member)     ((type * )hfl__dl_list_fe((dllist), (object), offsetof(type, member)))

static inline
void * hfl__dl_list_fe( const hfl_dl_list_type * dllist, void * container, size_t offset )
{
    hfl_dl_list_elem_type *     x;


    list_for_each(x, dllist) {
        if ( x == ((hfl_dl_list_elem_type * )(((uintptr_t )container) + offset)) )
            return container;
    }

    return NULL;
}

/**
 * hfl_dl_list_enumerate - execute code for each element in a doubly-linked list
 * @dllist: expression of type "pointer to const hfl_dl_list_type"
 * @type:   type-name specifying a structure type
 * @member: identifier naming a member of type "hfl_dl_list_elem_type" in @type
 * @elem:   identifier reserved for naming an object of type "pointer to @type" in @cstmt
 * @cstmt:  compound-statement to be executed for each element in @dllist
 *
 * Execute @cstmt for each element found in @dllist by enumerating @dllist in
 * forward order.  The element can be accessed from within @cstmt by referencing
 * an object of type "pointer to @type" named @elem in each invocation of @cstmt.
 */

#define hfl_dl_list_enumerate(dllist, type, member, elem, cstmt)                                \
    do {                                                                                        \
        type * elem;                                                                            \
        list_for_each(hfl_pobj_cast(hfl_dl_list_elem_type, elem), (dllist)) {                   \
            elem = container_of(hfl_pobj_cast(hfl_dl_list_elem_type, elem), type, member);      \
            cstmt                                                                               \
            hfl_pobj_cast(hfl_dl_list_elem_type, elem) = &(elem->member);                       \
        }                                                                                       \
    } while ( 0 )


#endif  // HZDR_FWF_LINUX_DL_LIST_H
