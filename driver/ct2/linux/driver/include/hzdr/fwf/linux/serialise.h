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

#if !defined HZDR_FWF_LINUX_SERIALISE_H
#define HZDR_FWF_LINUX_SERIALISE_H


/**
 * hfl_serialise - provide for the controlled execution of a code section
 * @sp:     expression denoting a synchronisation primitive
 * @acq:    expression denoting a function or function-like macro
 * @rel:    expression denoting a function or function-like macro
 * @cstmt:  compound-statement
 *
 * Construct a code fragment to be used as a compound-statement wherein
 * first @acq is called with @sp as the argument-expression-list, then @cstmt
 * is executed, and then @rel is called, again with @sp as the
 * argument-expression-list, where @cstmt is the critical
 * section of code.
 */

#define hfl_serialise(sp, acq, rel, cstmt)                                  \
{                                                                           \
    acq(sp);                                                                \
        cstmt                                                               \
    rel(sp);                                                                \
}

/**
 * hfl_serialise_c - provide for the controlled execution of a code section (on condition)
 * @sp:     expression denoting a synchronisation primitive
 * @acq:    expression denoting a function or function-like macro whose return type is a non-array complete object type
 * @rel:    expression denoting a function or function-like macro
 * @rv:     expression denoting an object of the return type of @acq
 * @rvref:  expression denoting a value of the return type of @acq
 * @cseq:   compound-statement
 * @csneq:  compound-statement
 *
 * Construct a code fragment to be used as a compound-statement wherein
 * first @acq is called with @sp as the argument-expression-list and the
 * value so produced is stored in @rv and compared against @rvref.  Then,
 * if the value of @rv equals @rvref, @cseq is executed, and then @rel is
 * called with @sp as the argument-expression-list, where @cseq is the
 * critical section of code.  Otherwise, only @csneq is executed.
 */

#define hfl_serialise_c(sp, acq, rel, rv, rvref, cseq, csneq)               \
{                                                                           \
    if ( (rv = acq(sp)) != (rvref) ) {                                      \
        csneq                                                               \
    } else {                                                                \
        cseq                                                                \
        rel(sp);                                                            \
    }                                                                       \
}


#endif  // HZDR_FWF_LINUX_SERIALISE_H
