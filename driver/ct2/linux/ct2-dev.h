/* -*- mode: C; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * ESRF C208/P201 Kernel definition                                         *
 *                                                                          *
 * Copyright (c) 2004 by European Synchrotron Radiation Facility,           *
 *                       Grenoble, France                                   *
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

#if !defined CT2_DEV_H
#define CT2_DEV_H

#include <linux/cdev.h>             // struct cdev
#include <linux/device.h>           // struct device
#include <linux/interrupt.h>        // request_irq(), free_irq()
#include <linux/mutex.h>            // struct mutex, mutex_(init|(un)lock)
#include <linux/pci.h>              // struct pci_dev
#include <linux/types.h>            // bool, dev_t, size_t, uint8_t
#include <linux/workqueue.h>        // struct work_struct

#include "public/esrf/ct2.h"        // ct2_reg_t
#include "ct2-param.h"              // ct2_in_fifo_(type|...)
#include "ct2-dcc.h"                // struct ct2_dcc


/*--------------------------------------------------------------------------*
 *                       Device Directory Entry Names                       *
 *--------------------------------------------------------------------------*/

#define CT2_NAME                            "ct2"

// printf() format for device and interrupt handler names
#define CT2_DEVICE_NAME_FMT                 "%04u:%02u:%02u.%u"
#define CT2_CDEV_BASENAME_FMT               "%s-" CT2_DEVICE_NAME_FMT
#define CT2_CDEV_BASENAME_PREFIX_C208       "c208"
#define CT2_CDEV_BASENAME_PREFIX_P201       "p201"
// We could do much better here.
#define CT2_CDEV_NAME_BUF_SIZE              (128)


/*--------------------------------------------------------------------------*
 *                              PCI Interface                               *
 *--------------------------------------------------------------------------*/

// PCI_VENDOR_ID_AMCC
#define CT2_VID                             (0x10e8)

#define PCI_DEVICE_ID_ESRF_C208             (0xee10)
#define PCI_DEVICE_ID_ESRF_P201             (0xee12)

#define CT2_PCI_BAR_AMCC                    (0)
#define CT2_PCI_BAR_IO_R1                   (CT2_PCI_BAR_AMCC + 1)
#define CT2_PCI_BAR_IO_R2                   (CT2_PCI_BAR_IO_R1 + 1)
#define CT2_PCI_BAR_FIFO                    (CT2_PCI_BAR_IO_R2 + 1)
#define CT2_PCI_BAR_COUNT                   (CT2_PCI_BAR_FIFO + 1)

#define CT2_AMCC_REG_MAP_LEN                (AMCC_OP_REG_MCSR + 4)


/*--------------------------------------------------------------------------*
 *                        CT2 Object Type Definitions                       *
 *--------------------------------------------------------------------------*/

/**
 * enum ct2_init_status - Device status object type
 */

enum ct2_init_status {

    DEV_INIT_ALLOC_CT2_STRUCT,

    DEV_INIT_PCI_DEV_ENABLE,

    DEV_INIT_AMCC_REGS_REGION,
    DEV_INIT_CTRL_REGS_1_REGION,
    DEV_INIT_CTRL_REGS_2_REGION,
    DEV_INIT_FIFO_REGION,

    DEV_INIT_ALLOC_CHRDEV,
    DEV_INIT_CLASS_DEV,
    DEV_INIT_ADD_CDEV,

    DEV_INIT_DEV_LIST_ADD,

    DEV_INIT_REQ_INTR
};

/**
 * ct2_r1_lut_type, ct2_r2_lut_type - register file type lookup tables
 *
 * For each offset  r  in the two Device register files as eg. modeled by the
 * struct ct2_r1  and  struct ct2_r2  structure types, there is an entry in a
 * corresponding lookup table at index  r  which contains an  l  such that the
 * interval  [r, r+l)  identifies the maximum number of contiguously accessible
 * registers starting at  r.  If, for any  r,  l = 0, then no register is
 * defined at that  r.
 */

typedef ct2_reg_dist_t ct2_r1_lut_type[CT2_RW_R1_LEN];
typedef ct2_reg_dist_t ct2_r2_lut_type[CT2_RW_R2_LEN];


/*--------------------------------------------------------------------------*
 *                                CT2 Device                                *
 *--------------------------------------------------------------------------*/

/**
 * struct ct2 - Device object type
 */

struct ct2 {

    hfl_dl_list_elem_type               list_elem;

    enum ct2_init_status                init_status;

    struct pci_dev * const              pci_dev;
    const bool                          req_intrs;
    const ct2_reg_t                     ctrl_it_mask;
    const ct2_r1_lut_type * const       r1_rd_lut;
    const ct2_r1_lut_type * const       r1_wr_lut;
    const ct2_r2_lut_type * const       r2_rd_lut;
    const ct2_r2_lut_type * const       r2_wr_lut;

    struct {
        const ct2_r1_io_addr_type       r1;
        const ct2_r2_io_addr_type       r2;
        ct2_regs_mutex_type             mutex;
    } regs;

    ct2_reg_t __iomem * const           fifo;

    struct {
        const char                      basename[CT2_CDEV_NAME_BUF_SIZE];
        const dev_t                     num;
        struct cdev                     obj;
        struct device * const           class;
    } cdev;

    struct {
        ct2_in_fifo_type                fifo;
        ct2_inm_mutex_type              mutex;
        struct work_struct              task;
    } inm;

    struct {
        hfl_dl_list_type                list;
        const struct ct2_dcc *          blessed;
        size_t                          blessed_fmc;
        ct2_dccm_mutex_type             mutex;
    } dccs;
};


/*--------------------------------------------------------------------------*
 *                        CT2 Device Register Access                        *
 *--------------------------------------------------------------------------*/

/**
 * ct2_regs_init - initialise the  struct ct2::regs  member
 */

static inline
void ct2_regs_init( struct ct2 * dev )
{
    hfl_const_cast(ct2_r1_io_addr_type, dev->regs.r1) = CT2_REGS_NULL_ADDR;
    hfl_const_cast(ct2_r2_io_addr_type, dev->regs.r2) = CT2_REGS_NULL_ADDR;
    ct2_regs_mutex_init(&(dev->regs.mutex));

    // Not strictly a control register, but it's close.
    hfl_const_cast(ct2_reg_t __iomem *, dev->fifo) = NULL;
}

/**
 * ct2_regs_readv_sync - read from Device register array (serialised)
 */

static inline
void ct2_regs_readv_sync( struct ct2 *                  dev,
                          ct2_const_regs_io_addr_type   src,
                          ct2_reg_t *                   dst,
                          ct2_reg_dist_t                count )
{

#if !defined CT2_MAP_IOPORTS_TO_IOMEM

    ct2_const_regs_io_addr_type     i;
    ct2_reg_dist_t                  j;

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM


    ct2_regs_sr(&(dev->regs.mutex), {

#if defined CT2_MAP_IOPORTS_TO_IOMEM

        // [include/asm-generic/io.h:memcpy_fromio()]
        memcpy_fromio(dst, src, (((size_t )count) * sizeof(ct2_reg_t)));

#else   // CT2_MAP_IOPORTS_TO_IOMEM

        // [include/asm-generic/io.h:inl()]
        for ( i = src, j = 0; j < count; i = i + sizeof(ct2_reg_t), j = j + 1 )
            dst[j] = (ct2_reg_t )inl(i);

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM

    })
}

/**
 * ct2_regs_writev_sync - write to Device register array (serialised)
 */

static inline
void ct2_regs_writev_sync( struct ct2 *             dev,
                           const ct2_reg_t *        src,
                           ct2_regs_io_addr_type    dst,
                           ct2_reg_dist_t           count )
{

#if !defined CT2_MAP_IOPORTS_TO_IOMEM

    ct2_reg_dist_t                  i;
    ct2_regs_io_addr_type           j;

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM


    ct2_regs_sw(&(dev->regs.mutex), {

#if defined CT2_MAP_IOPORTS_TO_IOMEM

        // [include/asm-generic/io.h:memcpy_toio()]
        memcpy_toio(dst, src, (((size_t )count) * sizeof(ct2_reg_t)));

#else   // CT2_MAP_IOPORTS_TO_IOMEM

        // [include/asm-generic/io.h:outl()]
        for ( i = 0, j = dst; i < count; i = i + 1, j = j + sizeof(ct2_reg_t) )
            outl(src[i], j);

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM

    })
}

/**
 * ct2_regs_rrs - read from Device register (serialised)
 */

static inline
ct2_reg_t ct2_regs_rrs( struct ct2 * dev, ct2_regs_io_addr_type addr )
{
    ct2_reg_t   reg;


    ct2_regs_sr(&(dev->regs.mutex), {

#if defined CT2_MAP_IOPORTS_TO_IOMEM

        // [include/asm-generic/iomap.h:ioread32()]
        reg = ioread32(addr);

#else   // CT2_MAP_IOPORTS_TO_IOMEM

        reg = (ct2_reg_t )inl(addr);

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM

    })

    return reg;
}

/**
 * ct2_regs_rrshi - read from Device register (serialised, in interrupt handler context)
 */

static inline
ct2_reg_t ct2_regs_rrshi( struct ct2 * dev, ct2_regs_io_addr_type addr )
{
    ct2_reg_t   reg;


    ct2_regs_srhi(&(dev->regs.mutex), {

#if defined CT2_MAP_IOPORTS_TO_IOMEM

        reg = ioread32(addr);

#else   // CT2_MAP_IOPORTS_TO_IOMEM

        reg = (ct2_reg_t )inl(addr);

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM

    })

    return reg;
}

/**
 * ct2_regs_wrs - write to Device register (serialised)
 */

static inline
void ct2_regs_wrs( struct ct2 * dev, ct2_regs_io_addr_type addr, ct2_reg_t reg )
{
    ct2_regs_sw(&(dev->regs.mutex), {

#if defined CT2_MAP_IOPORTS_TO_IOMEM

        // [include/asm-generic/iomap.h:iowrite32()]
        iowrite32(reg, addr);

#else   // CT2_MAP_IOPORTS_TO_IOMEM

        outl(reg, addr);

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM

    })
}

/**
 * register access helpers
 * @dev:    struct ct2 *
 * @spc:    { 1, 2 }
 * @reg:    set of register names in @spc
 * @regv:   set of register vector names in @spc
 * @buf:    ct2_reg_t[ct2_reg_size(@spc, @regv)]
 */

#if defined CT2_MAP_IOPORTS_TO_IOMEM

#define ct2_ctrl_reg_to_ioaddr(dev, spc, reg)       ((ct2_regs_io_addr_type )&((dev)->regs.r ## spc->reg))

#define ct2_regs_read(dev, spc, reg)                ioread32(ct2_ctrl_reg_to_ioaddr(dev, spc, reg))
#define ct2_regs_read_sync_hi(dev, spc, reg)        ct2_regs_rrshi((dev), ct2_ctrl_reg_to_ioaddr(dev, spc, reg))

#define ct2_regs_write(dev, spc, reg, val)          iowrite32((val), ct2_ctrl_reg_to_ioaddr(dev, spc, reg))
#define ct2_regs_clear(dev, spc, reg)               iowrite32(0x00000000, ct2_ctrl_reg_to_ioaddr(dev, spc, reg))

#define ct2_regs_writev(dev, spc, regv, buf)                                                        \
    memcpy_toio(ct2_ctrl_reg_to_ioaddr(dev, spc, regv[0]), buf, ct2_sizeof_reg(spc, regv))

#define ct2_regs_vtile(dev, spc, regv, buf, val)                                                    \
    do {                                                                                            \
        size_t i;                                                                                   \
        for ( i = 0; i < ct2_reg_size(spc, regv); i = i + 1 )                                       \
            buf[i] = (val);                                                                         \
        memcpy_toio(ct2_ctrl_reg_to_ioaddr(dev, spc, regv[0]), buf, ct2_sizeof_reg(spc, regv));     \
    } while ( 0 )

// [include/asm-generic/io.h:memset_io()]
#define ct2_regs_clearv(dev, spc, regv)                                                             \
    memset_io(ct2_ctrl_reg_to_ioaddr(dev, spc, regv[0]), 0x00, ct2_sizeof_reg(spc, regv))

#else   // CT2_MAP_IOPORTS_TO_IOMEM

#define ct2_ctrl_reg_to_ioport(dev, spc, reg)       (((dev)->regs.r ## spc) + ((resource_size_t )ct2_offsetof_reg(spc, reg)))

#define ct2_regs_read(dev, spc, reg)                inl(ct2_ctrl_reg_to_ioport(dev, spc, reg))
#define ct2_regs_read_sync_hi(dev, spc, reg)        ct2_regs_rrshi((dev), ct2_ctrl_reg_to_ioport(dev, spc, reg))

#define ct2_regs_write(dev, spc, reg, val)          outl((val), ct2_ctrl_reg_to_ioport(dev, spc, reg))
#define ct2_regs_clear(dev, spc, reg)               outl(0x00000000, ct2_ctrl_reg_to_ioport(dev, spc, reg))

#define ct2_regs_writev(dev, spc, regv, buf)                                                \
    do {                                                                                    \
        size_t i = 0;                                                                       \
        resource_size_t j = ct2_ctrl_reg_to_ioport(dev, spc, regv);                         \
        for ( ; i < ct2_reg_size(spc, regv); i = i + 1, j = j + sizeof(ct2_reg_t) )         \
            outl(buf[i], j);                                                                \
    } while ( 0 )

#define ct2_regs_vtile(dev, spc, regv, buf, val)                                            \
    do {                                                                                    \
        resource_size_t j = ct2_ctrl_reg_to_ioport(dev, spc, regv);                         \
        const resource_size_t l = j + ct2_sizeof_reg(spc, regv);                            \
        for ( ; j < l; j = j + sizeof(ct2_reg_t) )                                          \
            outl((val), j);                                                                 \
    } while ( 0 )

#define ct2_regs_clearv(dev, spc, regv)             ct2_regs_vtile(dev, spc, regv, 0, 0x00000000)

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM


/*--------------------------------------------------------------------------*
 *                       Device Interrupt Management                        *
 *--------------------------------------------------------------------------*/

/**
 * ct2_enable_interrupts - enable Device interrupts with the Kernel
 */

static inline
int ct2_enable_interrupts( struct ct2 * dev, irqreturn_t (* ih)( int, struct ct2 * ) )
{
    typedef irqreturn_t (linux_interrupt_handler)( int, void * );


    if ( !dev->req_intrs )
        return -ENXIO;

    // [include/linux/interrupt.h:request_irq()]
    return request_irq(dev->pci_dev->irq,
                       ((linux_interrupt_handler * )ih),
                       IRQF_SHARED,
                       dev->cdev.basename, dev          );
}

/**
 * ct2_disable_interrupts - disable Device interrupts with the Kernel
 */

static inline
void ct2_disable_interrupts( struct ct2 * dev )
{
    // XXX: Is this a no-op if interrupts aren't enabled ???
    // [kernel/irq/manage.c:free_irq()]
    free_irq(dev->pci_dev->irq, dev);
}


/*--------------------------------------------------------------------------*
 *                              INQ Management                              *
 *--------------------------------------------------------------------------*/

/**
 * ct2_inm_init - initialise the  struct ct2::inm  member
 */

static inline
void ct2_inm_init( struct ct2 * dev, void (* proc) ( struct work_struct * ) )
{
    ct2_in_fifo_truncate(&(dev->inm.fifo));
    ct2_inm_mutex_init(&(dev->inm.mutex));
    // [include/linux/workqueue.h:INIT_WORK()]
    INIT_WORK(&(dev->inm.task), proc);
}

/**
 * ct2_inm_fifo_init - setup the Device interrupt notification FIFO
 */

static inline
void ct2_inm_fifo_init( struct ct2 * dev, struct ct2_in_fifo_bhead * fbh )
{
    ct2_in_fifo_replace_reservoir(&(dev->inm.fifo), fbh);
}

/**
 * ct2_inm_fifo_reset - teardown the Device interrupt notification FIFO
 */

static inline
void ct2_inm_fifo_reset( struct ct2 * dev )
{
    struct ct2_in_fifo_bhead *  fbh;


    if ( (fbh = ct2_in_fifo_truncate(&(dev->inm.fifo))) != NULL )
        ct2_in_fifo_bhead_delete(fbh);
}

/**
 * ct2_inm_fifo_capacity - ask for the current capacity of the Device interrupt notification FIFO
 */

static inline
ct2_size_type ct2_inm_fifo_capacity( const struct ct2 * dev )
{
    return ct2_in_fifo_capacity(&(dev->inm.fifo));
}

/**
 * ct2_inm_fifo_fillpoint - ask for the current fillpoint of the Device interrupt notification FIFO
 */

static inline
ct2_size_type ct2_inm_fifo_fillpoint( struct ct2 * dev )
{
    ct2_size_type   fp;


    ct2_inm_sr(&(dev->inm.mutex), {
        fp = ct2_in_fifo_fillpoint(&(dev->inm.fifo));
    })

    return fp;
}

/**
 * ct2_post_in - post an interrupt notification
 */

static inline
void ct2_post_in( struct ct2 * dev, const struct ct2_in * in )
{
    ct2_inm_swhi(&(dev->inm.mutex), {
        ct2_in_fifo_append_nf(&(dev->inm.fifo), in);
    })

    // [kernel/workqueue.c:schedule_work()]
    schedule_work(&(dev->inm.task));
}

/**
 * ct2_receive_in - receive an interrupt notification previously posted by the interrupt handler
 */

static inline
void ct2_receive_in( struct ct2 * dev, struct ct2_in * in )
{
    // Since a FIFO read modifies the FIFO's state,
    // we actually require write serialisation here.
    ct2_inm_sw(&(dev->inm.mutex), {
        ct2_in_fifo_consume_ne(&(dev->inm.fifo), in);
    })
}


/*--------------------------------------------------------------------------*
 *                              DCC Management                              *
 *--------------------------------------------------------------------------*/

/**
 * ct2_dccs_init - initialise the  struct ct2::dccs  member
 */

static inline void ct2_dccs_init( struct ct2 * dev )
{
    hfl_dl_list_init(&(dev->dccs.list));
    dev->dccs.blessed = NULL;
    dev->dccs.blessed_fmc = 0;
    ct2_dccm_mutex_init(&(dev->dccs.mutex));
}

/**
 * ct2_dccs_sr - serialise Device DCC management read access(es)
 */

#define ct2_dccs_sr(dev, cstmt)                                             \
    ct2_dccm_sr(&((dev)->dccs.mutex), cstmt)

/**
 * ct2_dccs_sri - serialise Device DCC management read access(es) (interruptible)
 *
 * A local label  ct2_dccs_sri_end  is available in the scope of @csacq
 * that can be used from inside @csacq to transfer control to the statement
 * that is to follow the last statement in @csacq.
 */

#define ct2_dccs_sri(dev, rv, csint, csacq)                                 \
    ct2_dccm_sri(&((dev)->dccs.mutex),                                      \
                 (rv), csint,                                               \
                 {                                                          \
                    __label__ ct2_dccs_sri_end;                             \
                    csacq                                                   \
                    ct2_dccs_sri_end:;                                      \
                 }                             )

/**
 * ct2_dccs_srt - serialise Device DCC management read access(es) (non-sleepable)
 *
 * A local label  ct2_dccs_srt_end  is available in the scope of @csacq
 * that can be used from inside @csacq to transfer control to the statement
 * that is to follow the last statement in @csacq.
 */

#define ct2_dccs_srt(dev, rv, csrfs, csacq)                                 \
    ct2_dccm_srt(&((dev)->dccs.mutex),                                      \
                 (rv), csrfs,                                               \
                 {                                                          \
                    __label__ ct2_dccs_srt_end;                             \
                    csacq                                                   \
                    ct2_dccs_srt_end:;                                      \
                 }                             )

/**
 * ct2_dccs_sw - serialise Device DCC management write access(es)
 */

#define ct2_dccs_sw(dev, cstmt)                                             \
    ct2_dccm_sw(&((dev)->dccs.mutex), cstmt)

/**
 * ct2_dccs_swi - serialise Device DCC management write access(es) (interruptible)
 *
 * A local label  ct2_dccs_swi_end  is available in the scope of @csacq
 * that can be used from inside @csacq to transfer control to the statement
 * that is to follow the last statement in @csacq.
 */

#define ct2_dccs_swi(dev, rv, csint, csacq)                                 \
    ct2_dccm_swi(&((dev)->dccs.mutex),                                      \
                (rv), csint,                                                \
                {                                                           \
                    __label__ ct2_dccs_swi_end;                             \
                    csacq                                                   \
                    ct2_dccs_swi_end:;                                      \
                }                              )

/**
 * ct2_dccs_swi_nl - serialise Device DCC management write access(es) (interruptible, no label)
 */

#define ct2_dccs_swi_nl(dev, rv, csint, csacq)                              \
    ct2_dccm_swi(&((dev)->dccs.mutex), (rv), csint, csacq)

/**
 * ct2_dccs_add_dcc - add a DCC to the Device object DCC list
 */

static inline
void ct2_dccs_add_dcc( struct ct2 * dev, struct ct2_dcc * dcc )
{
    hfl_dl_list_append_elem(&(dev->dccs.list), &(dcc->list_elem));
}

/**
 * ct2_dccs_remove_dcc - remove a DCC from the Device object DCC list
 */

static inline
struct ct2_dcc * ct2_dccs_remove_dcc( struct ct2 * dev, struct ct2_dcc * dcc )
{
    return hfl_dl_list_remove_elem(&(dev->dccs.list), dcc, struct ct2_dcc, list_elem);
}

/**
 * ct2_dccs_count - ask for the number of DCCs in the Device object DCC list
 */

static inline
size_t ct2_dccs_count( const struct ct2 * dev )
{
    return hfl_dl_list_length(&(dev->dccs.list));
}

/**
 * ct2_dccs_for_each - execute code for each DCC in the Device object DCC list
 */

#define ct2_dccs_for_each(dev, iter, cstmt)                                 \
    hfl_dl_list_enumerate(&((dev)->dccs.list), struct ct2_dcc, list_elem, iter, cstmt)

/**
 * ct2_grant_xaccess - grant a DCC exclusive Device access
 */

static inline
void ct2_grant_xaccess( struct ct2 * dev, const struct ct2_dcc * dcc )
{
    dev->dccs.blessed = dcc;
}

/**
 * ct2_revoke_xaccess - remove exclusive Device access
 */

static inline
void ct2_revoke_xaccess( struct ct2 * dev )
{
    dev->dccs.blessed = NULL;
}

/**
 * ct2_observes_xaccess - ask whether there is currently exclusive Device access granted
 */

static inline
bool ct2_observes_xaccess( const struct ct2 * dev )
{
    return ( dev->dccs.blessed != NULL );
}

/**
 * ct2_add_mmap - increment the Device Scaler Values FIFO mmap count
 */

static inline
void ct2_add_mmap( struct ct2 * dev )
{
    dev->dccs.blessed_fmc += 1;
}

/**
 * ct2_remove_mmap - decrement the Device Scaler Values FIFO mmap count
 */

static inline
void ct2_remove_mmap( struct ct2 * dev )
{
    dev->dccs.blessed_fmc -= 1;
}

/**
 * ct2_is_mmapped - ask whether the Device Scaler Values FIFO is currently mmapped
 */

static inline
bool ct2_is_mmapped( const struct ct2 * dev )
{
    return ( dev->dccs.blessed_fmc > 0 );
}

/**
 * ct2_dcc_has_xaccess - ask whether a DCC allows for exclusive Device access
 */

static inline
bool ct2_dcc_has_xaccess( const struct ct2 * dev, const struct ct2_dcc * dcc )
{
    return ( dev->dccs.blessed == dcc );
}

/**
 * ct2_dcc_may_change_dev_state - ask whether a DCC allows to change the Device state
 */

static inline
bool ct2_dcc_may_change_dev_state( const struct ct2 * dev, const struct ct2_dcc * dcc )
{
    return ( ( dev->dccs.blessed == NULL ) || ct2_dcc_has_xaccess(dev, dcc) );
}


/*--------------------------------------------------------------------------*
 *                            Device Management                             *
 *--------------------------------------------------------------------------*/

/**
 * struct ct2_list - list of Device objects object type
 */

struct ct2_list {
    hfl_dl_list_type    list;
    struct mutex        mutex;
};

/**
 * ct2_list_init - initialise the list of Device objects
 */

static inline
void ct2_list_init( struct ct2_list * l )
{
    hfl_dl_list_init(&(l->list));
    mutex_init(&(l->mutex));
}

/**
 * ct2_list_length - ask for the number of Device objects in the list of Device objects
 */

static inline
size_t ct2_list_length( struct ct2_list * l )
{
    size_t  length;


    mutex_lock(&(l->mutex));
    length = hfl_dl_list_length(&(l->list));
    mutex_unlock(&(l->mutex));

    return length;
}

/**
 * ct2_list_append - append a Device object to the list of Device objects
 */

static inline
struct ct2_list * ct2_list_append( struct ct2_list * l, struct ct2 * d )
{
    hfl_dl_list_type *  x;


    mutex_lock(&(l->mutex));
    x = hfl_dl_list_append_elem_check(&(l->list), &(d->list_elem));
    mutex_unlock(&(l->mutex));

    if ( x == NULL )
        return NULL;
    else
        return container_of(x, struct ct2_list, list);
}

/**
 * ct2_list_remove - remove a Device object from the list of Device objects
 */

static inline
struct ct2 * ct2_list_remove( struct ct2_list * l, struct ct2 * d )
{
    struct ct2 *    x;


    mutex_lock(&(l->mutex));
    x = hfl_dl_list_remove_elem(&(l->list), d, struct ct2, list_elem);
    mutex_unlock(&(l->mutex));

    return x;
}


#endif  // CT2_DEV_H
