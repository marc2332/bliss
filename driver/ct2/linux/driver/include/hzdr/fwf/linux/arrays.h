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

#if !defined HZDR_FWF_LINUX_ARRAYS_H
#define HZDR_FWF_LINUX_ARRAYS_H

#include <linux/stddef.h>                           // offsetof()
#include <linux/types.h>                            // size_t


/**
 * hfl_array_size - determine the number of elements in an array
 * @type:   type-name specifying the element type in @array
 * @array:  expression of array type
 *
 * returns: the number of elements in @array as a &size_t
 */

#define hfl_array_size(type, array)                 ((size_t )(sizeof(array)/sizeof(type)))

/**
 * hfl_array_elem_offset - determine the offset between two elements in an array
 * @array:  expression denoting an object of array type with at least two elements
 *
 * returns: the number of bytes between two elements in @array as a &size_t
 */

#define hfl_array_elem_offset(array)                ((size_t )(((char * )&((array)[1])) - ((char * )&((array)[0]))))

/**
 * hfl_sizeof_vamsl_struct - sizeof a structure with a vararray as its last member
 * @type:   type-name specifying a structure type
 * @name:   identifier naming an array with at least two elements as the last member in @type
 * @n:      expression denoting the number of elements in the vararray @name, where @n > 1
 *
 * Determine the size, in bytes, of objects of type "@type" as if they contained a
 * vararray named @name of @n elements as the last entry in their struct-declaration-list
 * instead of only the array member @name.  The vararray will have the same element type
 * as @name in @type.
 *
 * NOTE: This assumes that the alignment for arrays of any given element type
 *       is invariant with respect to the number of elements in such arrays.
 */

#define hfl_sizeof_vamsl_struct(type, name, n)      (offsetof(type, name) + (n) * hfl_array_elem_offset(((type * )(0))->name))


#endif  // HZDR_FWF_LINUX_ARRAYS_H
