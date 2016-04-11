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

#if !defined HZDR_FWF_LINUX_TYPE_CASTS_H
#define HZDR_FWF_LINUX_TYPE_CASTS_H


/**
 * hfl_const_cast - cast away constness from an object
 * @type:   type-name specifying a non-const-qualified object type
 * @object: expression denoting an object of type "const @type"
 *
 * returns: @object, whose type has been adjusted to "@type"
 */

#define hfl_const_cast(type, object)                (*((type * )&(object)))

/**
 * hfl_pobj_cast - change the referenced object type of a pointer object to another object type
 * @type:   type-name specifying an object type
 * @ptr:    expression denoting an object of type "pointer to T"
 *          where T specifies an object type
 *
 * returns: @ptr, whose type has been adjusted to "pointer to @type"
 */

#define hfl_pobj_cast(type, ptr)                    (*((type ** )&(ptr)))


#endif  // HZDR_FWF_LINUX_TYPE_CASTS_H
