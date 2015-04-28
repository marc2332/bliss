/* -*- mode: C; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * ESRF C208/P201 Kernel Module code parametrisation                        *
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

#if !defined CT2_PARAM_H
#define CT2_PARAM_H

#include <linux/mutex.h>                // struct mutex
#include <linux/spinlock.h>             // spinlock_t
#include <linux/string.h>               // mem(cpy|move)()
#include <linux/types.h>                // size_t, uintptr_t, resource_size_t

#include <hzdr/fwf/linux/serialise.h>   // hfl_serialise(_c)()

#include "public/esrf/ct2.h"            // ct2_reg_t, ct2_reg_dist_t, struct ct2_in


/*--------------------------------------------------------------------------*
 *                                 INQ FIFO                                 *
 *--------------------------------------------------------------------------*/

#define HFL_FIFO_PREFIX             ct2_in_
#define HFL_FIFO_ENTRY_TYPE         struct ct2_in

static inline
void ct2_in_fifo_copy_entries( const struct ct2_in * src, struct ct2_in * dst, size_t count )
{
    // [lib/string.c:memcpy()]
    memcpy(dst, src, (count * sizeof(struct ct2_in)));
}

static inline
void ct2_in_fifo_move_entries( const struct ct2_in * src, struct ct2_in * dst, size_t count )
{
    // [lib/string.c:memmove()]
    memmove(dst, src, (count * sizeof(struct ct2_in)));
}

#include <hzdr/fwf/linux/fifo/fifo.h>
#include <hzdr/fwf/linux/fifo/truncate.h>
#include <hzdr/fwf/linux/fifo/replace_reservoir.h>

static inline
void ct2_in_fifo_copy_entry( const struct ct2_in * src, struct ct2_in * dst )
{
    dst->ctrl_it = src->ctrl_it;
    dst->stamp = src->stamp;
}

#include <hzdr/fwf/linux/fifo/append_nf.h>
#include <hzdr/fwf/linux/fifo/consume_ne.h>

typedef struct ct2_in_fifo          ct2_in_fifo_type;


/*--------------------------------------------------------------------------*
 *                          PCI I/O Space Mappings                          *
 *--------------------------------------------------------------------------*/

#if defined CT2_MAP_IOPORTS_TO_IOMEM

typedef uintptr_t                   ct2_io_addr_uint_type;

// kernel I/O port mapped virtual address types

typedef struct ct2_r1 __iomem *     ct2_r1_io_addr_type;
typedef struct ct2_r2 __iomem *     ct2_r2_io_addr_type;

typedef ct2_reg_t __iomem *         ct2_regs_io_addr_type;
typedef const ct2_reg_t __iomem *   ct2_const_regs_io_addr_type;

#define CT2_REGS_NULL_ADDR          NULL

static inline
ct2_reg_t __iomem * ct2_io_addr_subscript( ct2_reg_t __iomem * base, ct2_reg_dist_t off )
{
    // pointer arithmetic
    return (base + off);
}

#else   // CT2_MAP_IOPORTS_TO_IOMEM

typedef resource_size_t             ct2_io_addr_uint_type;

// kernel I/O port address types

// [include/linux/types.h:resource_size_t, include/linux/ioport.h:struct resource]
typedef resource_size_t             ct2_r1_io_addr_type;
typedef resource_size_t             ct2_r2_io_addr_type;

typedef resource_size_t             ct2_regs_io_addr_type;
typedef resource_size_t             ct2_const_regs_io_addr_type;

#define CT2_REGS_NULL_ADDR          (0U)

static inline
resource_size_t ct2_io_addr_subscript( resource_size_t base, ct2_reg_dist_t off )
{
    // (unsigned) integer arithmetic
    return (base + (off * sizeof(ct2_reg_t)));
}

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM


/*--------------------------------------------------------------------------*
 *                          Device Register Access                          *
 *--------------------------------------------------------------------------*/

// Contending contexts are interrupt and user contexts and /must not/ sleep.

// Since the number of read-only, write-only, and read-write registers is
// fairly balanced, we anticipate that reads and writes will, too, be balanced,
// so using  rwlock_t instead of  spinlock_t  would not seem to have much of an
// advantage.  We'd also like to keep it simple with one giant register lock
// over both register files.
typedef spinlock_t                          ct2_regs_mutex_type;

// The rationale for disabling (local processor) interrupts while holding
// the lock even when we are executing in any other than interrupt context
// is the example in LDD3, p 118, last paragraph.

// [include/linux/spinlock.h:spin_lock_init()]
#define ct2_regs_mutex_init                 spin_lock_init

typedef struct {
    ct2_regs_mutex_type * const     lock;
    unsigned long                   flags;
} ct2_spinlock_t;

static inline
void ct2_spin_lock_irqsave( ct2_spinlock_t * sl )
{
    // [include/linux/spinlock.h:spin_lock_irqsave()]
    spin_lock_irqsave(sl->lock, sl->flags);
}

static inline
void ct2_spin_unlock_irqrestore( ct2_spinlock_t * sl )
{
    // [include/linux/spinlock.h:spin_unlock_irqrestore()]
    spin_unlock_irqrestore(sl->lock, sl->flags);
}

#define ct2_regs_s(mutex, pfx, cstmt)                                       \
{                                                                           \
    ct2_spinlock_t pfx ## cxt = { (mutex), 0 };                             \
    hfl_serialise(&(pfx ## cxt),                                            \
                  ct2_spin_lock_irqsave,                                    \
                  ct2_spin_unlock_irqrestore,                               \
                  cstmt                      )                              \
}

/**
 * ct2_regs_sr - serialise Device register read access(es) in user context
 * @mutex:  expression of type "pointer to ct2_regs_mutex_type"
 * @cstmt:  compound-statement
 *
 * Ensure consistency of the Device register read(s) expressed in @cstmt
 * by serialising their execution w.r.t. all concurrent Device register
 * write accesses.
 *
 * Inside @cstmt, the prefix  ct2_regs_sr_  shall not appear in any identifier.
 */

#define ct2_regs_sr(mutex, cstmt)           ct2_regs_s((mutex), ct2_regs_sr_, cstmt)

/**
 * ct2_regs_srhi - serialise Device register read access(es) in interrupt context
 * @mutex:  expression of type "pointer to ct2_regs_mutex_type"
 * @cstmt:  compound-statement
 *
 * (cf. ct2_regs_sr())
 *
 * Inside @cstmt, the prefix  ct2_regs_srhi_  shall not appear in any identifier.
 */

#define ct2_regs_srhi(mutex, cstmt)         ct2_regs_s((mutex), ct2_regs_srhi_, cstmt)

/**
 * ct2_regs_sw - serialise Device register write access(es) in user context
 * @mutex:  expression of type "pointer to ct2_regs_mutex_type"
 * @cstmt:  compound-statement
 *
 * Ensure consistency of the Device register write(s) expressed in @cstmt
 * by serialising their execution w.r.t. all other concurrent Device register
 * accesses.
 *
 * Inside @cstmt, the prefix  ct2_regs_sw_  shall not appear in any identifier.
 */

#define ct2_regs_sw(mutex, cstmt)           ct2_regs_s((mutex), ct2_regs_sw_, cstmt)


/*--------------------------------------------------------------------------*
 *                             IN(Q) Management                             *
 *--------------------------------------------------------------------------*/

// Contending contexts are interrupt and kthread contexts and /must not/ sleep.

typedef ct2_regs_mutex_type                 ct2_inm_mutex_type;

#define ct2_inm_mutex_init                  ct2_regs_mutex_init

#define ct2_inm_s(mutex, pfx, cstmt)        ct2_regs_s((mutex), pfx, cstmt)

/**
 * ct2_inm_sr - serialise IN(Q) management read access(es) in user context
 * @mutex:  expression of type "pointer to ct2_inm_mutex_type"
 * @cstmt:  compound-statement
 *
 * Ensure consistency of the IN(Q) management read(s) expressed in @cstmt
 * by serialising their execution w.r.t. all concurrent IN(Q) management
 * write accesses.
 *
 * Inside @cstmt, the prefix  ct2_inm_sr_  shall not appear in any identifier.
 */

#define ct2_inm_sr(mutex, cstmt)            ct2_inm_s((mutex), ct2_inm_sr_, cstmt)

/**
 * ct2_inm_sw - serialise IN(Q) management write access(es) in user context
 * @mutex:  expression of type "pointer to ct2_inm_mutex_type"
 * @cstmt:  compound-statement
 *
 * Ensure consistency of the IN(Q) management write(s) expressed in @cstmt
 * by serialising their execution w.r.t. all other concurrent IN(Q) management
 * accesses.
 *
 * Inside @cstmt, the prefix  ct2_inm_sw_  shall not appear in any identifier.
 */

#define ct2_inm_sw(mutex, cstmt)            ct2_inm_s((mutex), ct2_inm_sw_, cstmt)

/**
 * ct2_inm_swhi - serialise IN(Q) management write access(es) in interrupt context
 * @mutex:  expression of type "pointer to ct2_inm_mutex_type"
 * @rpfx:   prefix guaranteed to not appear in any identifier inside @cstmt
 * @cstmt:  compound-statement
 *
 * (cf. ct2_inm_sw())
 *
 * Inside @cstmt, the prefix  ct2_inm_swhi_  shall not appear in any identifier.
 */

#define ct2_inm_swhi(mutex, cstmt)          ct2_inm_s((mutex), ct2_inm_swhi_, cstmt)


/*--------------------------------------------------------------------------*
 *                              DCC Management                              *
 *--------------------------------------------------------------------------*/

// Contending contexts are kthread and user contexts and /may/ sleep.

// Our current exclusion scheme for all accesses DCC is based on the
// assumption of a low number of DCCs active at any one time and very light
// contention among contexts and therefore provides only one giant primitive.
// As in the Device register access case, we expect that reads and writes will
// be balanced and choose  struct mutex  over, eg. RCU.
typedef struct mutex                        ct2_dccm_mutex_type;

// [include/linux/mutex.h:mutex_init(mutex)]
#define ct2_dccm_mutex_init                 mutex_init

// [include/linux/mutex.h:mutex_lock()]
// [include/linux/mutex.h:mutex_lock_interruptible()]
// [include/linux/mutex.h:mutex_trylock()]
// [include/linux/mutex.h:mutex_unlock()]

/**
 * ct2_dccm_sr - serialise DCC management read access(es)
 * @mutex:  expression of type "pointer to ct2_dccm_mutex_type"
 * @cstmt:  compound-statement
 *
 * Ensure consistency of the DCC management read(s) expressed in @cstmt by
 * serialising their execution w.r.t. all concurrent DCC management write
 * accesses.
 */

#define ct2_dccm_sr(mutex, cstmt)                                           \
    hfl_serialise((mutex),                                                  \
                  mutex_lock,                                               \
                  mutex_unlock,                                             \
                  cstmt        )

/**
 * ct2_dccm_sri - serialise DCC management read access(es) (interruptible)
 * @mutex:  expression of type "pointer to ct2_dccm_mutex_type"
 * @rv:     expression denoting an object of type "int"
 * @csint:  compound-statement
 * @csacq:  compound-statement
 *
 * (cf. ct2_dccm_sr())
 *
 * If, in the contention case, the context was put to sleep and
 * subsequently interrupted before it could acquire @mutex, @rv holds the
 * value %-EINTR and @csint is executed instead of @rv holding the value
 * %0 and @csacq being executed.
 */

#define ct2_dccm_sri(mutex, rv, csint, csacq)                               \
    hfl_serialise_c((mutex),                                                \
                    mutex_lock_interruptible,                               \
                    mutex_unlock,                                           \
                    (rv), 0,                                                \
                    csacq, csint             )

/**
 * ct2_dccm_srt - serialise DCC management read access(es) (non-sleepable)
 * @mutex:  expression of type "pointer to ct2_dccm_mutex_type"
 * @rv:     expression denoting an object of type "int"
 * @csrfs:  compound-statement
 * @csacq:  compound-statement
 *
 * (cf. ct2_dccm_sr())
 *
 * In case of contention, the context being late to access @mutex is
 * denied ownership of @mutex and is notified of that fact via a value
 * of %-EAGAIN in @rv and @csrfs is executed.  Otherwise, @rv holds %0
 * and @csacq is executed.
 */

#define ct2_dccm_srt(mutex, rv, csrfs, csacq)                               \
    hfl_serialise_c((mutex),                                                \
                    mutex_trylock,                                          \
                    mutex_unlock,                                           \
                    (rv), 1,                                                \
                    {                                                       \
                        (rv) = 0;                                           \
                        csacq                                               \
                    },                                                      \
                    {                                                       \
                        (rv) = -EAGAIN;                                     \
                        csrfs                                               \
                    }                  )

/**
 * ct2_dccm_sw - serialise DCC management write access(es)
 * @mutex:  expression of type "pointer to ct2_dccm_mutex_type"
 * @cstmt:  compound-statement
 *
 * Ensure consistency of the DCC management write(s) expressed in @cstmt
 * by serialising their execution w.r.t. all other concurrent DCC management
 * accesses.
 */

#define ct2_dccm_sw(mutex, cstmt)                                           \
    ct2_dccm_sr((mutex), cstmt)

/**
 * ct2_dccm_swi - serialise DCC management write access(es) (interruptible)
 * @mutex:  expression of type "pointer to ct2_dccm_mutex_type"
 * @rv:     expression denoting an object of type "int"
 * @csint:  compound-statement
 * @csacq:  compound-statement
 *
 * Ensure consistency of the DCC management write(s) expressed in @csacq
 * by serialising their execution w.r.t. all other concurrent DCC management
 * accesses.
 *
 * If, in the contention case, the context was put to sleep and
 * subsequently interrupted before it could acquire @mutex, @rv holds the
 * value %-EINTR and @csint is executed instead of @rv holding the value
 * %0 and @csacq being executed.
 */

#define ct2_dccm_swi(mutex, rv, csint, csacq)                               \
    ct2_dccm_sri((mutex), (rv), csint, csacq)


/*--------------------------------------------------------------------------*
 *                         Module Parameter Defaults                        *
 *--------------------------------------------------------------------------*/

#if !defined CT2_KMOD_PARAM_BITSTREAM_PATH
#define CT2_KMOD_PARAM_BITSTREAM_PATH               ""
#endif

#if !defined CT2_KMOD_PARAM_ENABLE_P201_TEST_REG
#define CT2_KMOD_PARAM_ENABLE_P201_TEST_REG         false
#endif

#if !defined CT2_KMOD_PARAM_DEFAULT_INQ_LENGTH
#define CT2_KMOD_PARAM_DEFAULT_INQ_LENGTH           32
#endif

// CT2_VBC_ERROR + CT2_VBC_WARNING
#if !defined CT2_KMOD_PARAM_VERBOSITY
#define CT2_KMOD_PARAM_VERBOSITY                    10
#endif


#endif  // CT2_PARAM_H
