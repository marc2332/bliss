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

#if !defined HZDR_FWF_LINUX_RELATIONS_H
#define HZDR_FWF_LINUX_RELATIONS_H


/**
 * hfl_in_interval_ix - test whether a number is inside an interval
 * @type:   type-name specifying a real type
 * @x:      expression denoting a value of type @type
 * @l:      expression denoting a value of type @type
 * @u:      expression denoting a value of type @type
 *
 * returns: "true" if @l ≤ @x < @u or "false" otherwise
 */

#define hfl_in_interval_ix(type, x, l, u)                                   \
({                                                                          \
    type _x = (x);                                                          \
    type _l = (l);                                                          \
    type _u = (u);                                                          \
    ( ( _l <= _x ) && ( _x < _u ) );                                        \
})


#endif  // HZDR_FWF_LINUX_RELATIONS_H
