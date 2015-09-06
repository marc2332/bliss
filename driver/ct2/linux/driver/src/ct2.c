/* -*- mode: C; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * Copyright (c) 2004 by European Synchrotron Radiation Facility,           *
 *                       Grenoble, France                                   *
 * Copyright © 2013-2014 Helmholtz-Zentrum Dresden Rossendorf               *
 * Christian Böhme <c.boehme@hzdr.de>                                       *
 *                                                                          *
 ****************************************************************************/


/*--------------------------------------------------------------------------*
 *                               Linux Headers                              *
 *--------------------------------------------------------------------------*/

#include <linux/cdev.h>             // cdev_+()
#include <linux/device.h>           // DRIVER_ATTR(), DEVICE_ATTR()
#include <linux/errno.h>            // error codes
#include <linux/fs.h>               // struct file, ..., SEEK_(SET|CUR|END), alloc_chrdev_region()
#include <linux/init.h>             // __devexit_p(), __init, __exit
#include <linux/ioctl.h>            // _IO*()
#include <linux/ioport.h>           // request_region(), request_mem_region()
#include <linux/kernel.h>           // container_of(), printk(), INT_MAX, snprintf(), min_t()
#include <linux/module.h>           // MODULE_+()
#include <linux/pci.h>              // pci_+(), PCI_+
#include <linux/poll.h>             // poll_table
#include <linux/slab.h>             // kmalloc(), kfree()
#include <linux/stddef.h>           // offsetof(), true, false
#include <linux/string.h>           // mem(cpy|set)()
#include <linux/stringify.h>        // __stringify()
#include <linux/time.h>             // getrawmonotonic()
#include <linux/types.h>            // bool, gfp_t, loff_t, size_t, ssize_t, uint(8|16|32|ptr)_t

#include <asm/io.h>                 // pci_iomap(), pci_iounmap()
#include <asm/page.h>               // PAGE_SHIFT

#include <hzdr/fwf/linux/dl_list.h>
#include <hzdr/fwf/linux/relations.h>
#include <hzdr/fwf/linux/type_casts.h>


/*--------------------------------------------------------------------------*
 *                              Private Headers                             *
 *--------------------------------------------------------------------------*/

#include "ct2-param.h"
#include "ct2-dcc.h"
#include "ct2-dev.h"

#include "amcc.h"                   // definitions for AMCC S5933 chip



/*==========================================================================*
 *                 Function forward declaration (prototypes)                *
 *==========================================================================*/

/*--------------------------------------------------------------------------*
 *                      Module and Device Entry Points                      *
 *--------------------------------------------------------------------------*/

static int  __init  ct2_init    ( void );
static void         ct2_exit    ( void );

static int          ct2_probe   ( struct pci_dev *, const struct pci_device_id * );
static void         ct2_remove  ( struct pci_dev * );

static int          ct2_open    ( struct inode *, struct file * );
static int          ct2_close   ( struct inode *, struct file * );

static ssize_t      ct2_read    ( struct file *, char __user *, size_t, loff_t * );
static ssize_t      ct2_read_fifo(struct file *, char __user *, size_t, loff_t * );
static ssize_t      ct2_write   ( struct file *, const char __user *, size_t, loff_t * );
static loff_t       ct2_llseek  ( struct file *, loff_t, int );

static int          ct2_ioctl   ( struct inode *, struct file *, unsigned int, u_long );

static int          ct2_mmap    ( struct file *, struct vm_area_struct * );
static unsigned int ct2_poll    ( struct file *, poll_table * );


/*--------------------------------------------------------------------------*
 *                           Interrupt Processing                           *
 *--------------------------------------------------------------------------*/

static irqreturn_t process_device_interrupts( int, struct ct2 * );
static void distribute_interrupt_notifications( struct work_struct * );


/*--------------------------------------------------------------------------*
 *                               Local Helpers                              *
 *--------------------------------------------------------------------------*/

// ct2_init()
static void init_ct2_register_range_luts( void );

// ct2_probe()
static bool check_pci_io_region( const struct ct2 *, unsigned int, unsigned int, size_t );
static int load_fpga_bitstream( const struct ct2 * );
static int check_cub( const struct ct2 * );
static void reset_device( struct ct2 * );

// ct2_ioctl()
static int enable_device_interrupts( const struct ct2_dcc *, const struct file *, ct2_size_type );
static int disable_device_interrupts( const struct ct2_dcc * );
static int acknowledge_interrupt( struct ct2_dcc *, struct ct2_in __user * );
static int attach_inq( struct ct2_dcc *, ct2_size_type );
static void detach_inq( struct ct2_dcc * );
static int drain_inq( struct ct2_dcc *, const struct file *, struct ct2_inv __user * );
static int flush_inq( struct ct2_dcc *, struct timespec __user * );
static int grant_exclusive_access( struct ct2_dcc * );
static int revoke_exclusive_access( struct ct2_dcc * );



/*==========================================================================*
 *                            Object Definitions                            *
 *==========================================================================*/

/*--------------------------------------------------------------------------*
 * Driver version and RCS Id                                                *
 *--------------------------------------------------------------------------*/

char drv_revision[] = "XXX";


/*--------------------------------------------------------------------------*
 *                           PCI Device Interface                           *
 *--------------------------------------------------------------------------*/

// [include/linux/pci.h:DEFINE_PCI_DEVICE_TABLE()]
static DEFINE_PCI_DEVICE_TABLE(ct2_device_id_table) = {

    { PCI_DEVICE(CT2_VID, PCI_DEVICE_ID_ESRF_C208) },
    { PCI_DEVICE(CT2_VID, PCI_DEVICE_ID_ESRF_P201) },
    { }
};

// May not be qualified const due to pci_register_driver() apparently modifying it.
// [include/linux/pci.h]
static struct pci_driver ct2_driver = {

    .name       = CT2_NAME,

    .id_table   = ct2_device_id_table,

    .probe      = ct2_probe,
    .remove     = __devexit_p(ct2_remove),
};


/*--------------------------------------------------------------------------*
 *                               VFS Interface                              *
 *--------------------------------------------------------------------------*/

// [include/linux/fs.h, Documentation/filesystems/vfs.txt]
static const struct file_operations ct2_file_ops = {

    .owner      = THIS_MODULE,

    .open       = ct2_open,
    .release    = ct2_close,

    .read       = ct2_read,
    .write      = ct2_write,
    .llseek     = ct2_llseek,

    .ioctl      = ct2_ioctl,

    .mmap       = ct2_mmap,
    .poll       = ct2_poll,
};


/*--------------------------------------------------------------------------*
 *                          Kernel Driver Interface                         *
 *--------------------------------------------------------------------------*/

static ssize_t ct2_drv_revision_show( struct device_driver *, char * );
static ssize_t ct2_drv_status_show( struct device_driver *, char * );

static DRIVER_ATTR(revision, S_IRUGO, ct2_drv_revision_show, NULL);
static DRIVER_ATTR(status, S_IRUGO, ct2_drv_status_show, NULL);


/*--------------------------------------------------------------------------*
 *                          Kernel Module Interface                         *
 *--------------------------------------------------------------------------*/

MODULE_DESCRIPTION("Unified/Common C208+P201 Linux driver");
MODULE_AUTHOR("Franc Sever (sever@esrf.fr) and Christian Böhme (c.boehme@hzdr.de)");
MODULE_LICENSE("Dual BSD/GPL");

MODULE_DEVICE_TABLE(pci, ct2_device_id_table);

module_init(ct2_init);
module_exit(ct2_exit);


/*--------------------------------------------------------------------------*
 *                             Module Parameters                            *
 *--------------------------------------------------------------------------*/

static bool enable_p201_test_reg = CT2_KMOD_PARAM_ENABLE_P201_TEST_REG;
module_param(enable_p201_test_reg, bool, S_IRUGO);
MODULE_PARM_DESC(enable_p201_test_reg,
                 "enable R/W access to TEST_REG in the IO space 1 register map of P201 devices "
                 "(default: " __stringify(CT2_KMOD_PARAM_ENABLE_P201_TEST_REG) ")"              );

#if ( CT2_KMOD_PARAM_DEFAULT_INQ_LENGTH <= 0 )
# error "CT2_KMOD_PARAM_DEFAULT_INQ_LENGTH must be define'd to a Natural Number greater than 0."
#endif

static unsigned int inq_length = CT2_KMOD_PARAM_DEFAULT_INQ_LENGTH;
module_param(inq_length, uint, S_IRUGO);
MODULE_PARM_DESC(inq_length,
                 "default interrupt notification queue length "
                 "(default: " __stringify(CT2_KMOD_PARAM_DEFAULT_INQ_LENGTH) ")");


#define CT2_VBC_INTERNAL            0
#define CT2_VBC_ERROR               1
#define CT2_VBC_API_FAILURE         2
#define CT2_VBC_WARNING             3
#define CT2_VBC_NOTICE              4
#define CT2_VBC_KAPI_TRACE          5
#define CT2_VBC_MFUNC_TRACE         6

static const char * const verb_cat[] = {
    "x", "e", "f", "w", "n", "k", "m"
};

#if ( CT2_KMOD_PARAM_VERBOSITY >= (1 << (CT2_VBC_MFUNC_TRACE + 1)) )
# error "CT2_KMOD_PARAM_VERBOSITY must be define'd to a Natural Number less than 128."
#endif

static unsigned int verbosity = CT2_KMOD_PARAM_VERBOSITY;
// Use S_IRUGO | S_IWUGO to be able to change verbosity from the shell.
// For ex. the following line typed in shell:
//  echo 10 > /sys/module/ct2/parameters/verbosity
// sets the verbosity level to CT2_VBC_ERROR + CT2_VBC_WARNING.
// This would not be possible if would use only S_IRUGO.
// However, the kernel people decided that a world writable entry would
// be too liberal and prevent any S_IWOTH or S_IXOTH from getting through.
// [include/linux/moduleparam.h:__module_param_call()]
module_param(verbosity, uint, ( S_IWUSR | S_IWGRP | S_IRUGO ));
MODULE_PARM_DESC(verbosity,
                 "verbosity flags: 1 - internal/logic error, "
                                  "2 - type error, "
                                  "4 - API failure, "
                                  "8 - warning, "
                                 "16 - notice, "
                                 "32 - kernel API trace, "
                                 "64 - module function trace "
                 "(default: " __stringify(CT2_KMOD_PARAM_VERBOSITY) ")");


/*--------------------------------------------------------------------------*
 *                        Module Private Definitions                        *
 *--------------------------------------------------------------------------*/

/**
 * enum ct2_mod_init_status - module status object type
 */

enum ct2_mod_init_status {

    MOD_INIT_UNDEFINED,
    MOD_INIT_CLASS_REGISTER,
    MOD_INIT_PCI_REGISTER_DRIVER,
    MOD_INIT_CREATE_DRV_ATTR_FILE

}                               mod_init_status = MOD_INIT_UNDEFINED;
// serialised access list of managed CT2 devices
static struct ct2_list          mod_device_list;
static struct class *           ct2_class = NULL;

/**
 * ct2_reg_lut_ident - LUT name constructor
 * @ct2:    { c208, p201 }
 * @spc:    { 1, 2 }
 * @rw:     { rd, wr }
 */

#define ct2_reg_lut_ident(ct2, spc, rw)     ct2 ## _r ## spc ## _ ## rw ## _lut

static const ct2_r1_lut_type    ct2_reg_lut_ident(c208, 1, rd);
static const ct2_r1_lut_type    ct2_reg_lut_ident(c208, 1, wr);
static const ct2_r2_lut_type    ct2_reg_lut_ident(c208, 2, rd);
static const ct2_r2_lut_type    ct2_reg_lut_ident(c208, 2, wr);

static const ct2_r1_lut_type    ct2_reg_lut_ident(p201, 1, rd);
static const ct2_r1_lut_type    ct2_reg_lut_ident(p201, 1, wr);
static const ct2_r2_lut_type    ct2_reg_lut_ident(p201, 2, rd);
static const ct2_r2_lut_type    ct2_reg_lut_ident(p201, 2, wr);


// [include/linux/kernel.h:printk()]
#define ct2_printk(fmt, args...)            printk(CT2_NAME " " fmt "\n", ## args)
#define ct2_printk_cf(cat, fmt, args...)                                            \
{                                                                                   \
    if ( (verbosity & (1 << (cat))) != 0 )                                          \
        ct2_printk("%s %s " fmt, verb_cat[(cat)], __FUNCTION__, ## args);           \
}
#define ct2_printk_dcf(dev, cat, fmt, args...)                                      \
    ct2_printk_cf((cat), "[%s] " fmt, (dev)->cdev.basename, ## args)

#define ct2_internal(dev, fmt, args...)     ct2_printk_dcf((dev), CT2_VBC_INTERNAL, fmt, ## args)

#define ct2_error0(fmt, args...)            ct2_printk_cf(CT2_VBC_ERROR, fmt, ## args)
#define ct2_error(dev, fmt, args...)        ct2_printk_dcf((dev), CT2_VBC_ERROR, fmt, ## args)

#define ct2_fail0(fmt, args...)             ct2_printk_cf(CT2_VBC_API_FAILURE, fmt, ## args)
#define ct2_fail(dev, fmt, args...)         ct2_printk_dcf((dev), CT2_VBC_API_FAILURE, fmt, ## args)

#define ct2_warn0(fmt, args...)             ct2_printk_cf(CT2_VBC_WARNING, fmt, ## args)
#define ct2_warn(dev, fmt, args...)         ct2_printk_dcf((dev), CT2_VBC_WARNING, fmt, ## args)

#define ct2_notice0(fmt, args...)           ct2_printk_cf(CT2_VBC_NOTICE, fmt, ## args)
#define ct2_notice(dev, fmt, args...)       ct2_printk_dcf((dev), CT2_VBC_NOTICE, fmt, ## args)

#if defined CT2_DEBUG

#define ct2_ktrace0(fmt, args...)           ct2_printk_cf(CT2_VBC_KAPI_TRACE, fmt, ## args)
#define ct2_ktrace(dev, fmt, args...)       ct2_printk_dcf((dev), CT2_VBC_KAPI_TRACE, fmt, ## args)

#define ct2_mtrace0_enter                   ct2_printk_cf(CT2_VBC_MFUNC_TRACE, "->")
#define ct2_mtrace0_exit                    ct2_printk_cf(CT2_VBC_MFUNC_TRACE, "<-")
#define ct2_mtrace_enter(dev)               ct2_printk_dcf((dev), CT2_VBC_MFUNC_TRACE, "->")
#define ct2_mtrace_exit(dev)                ct2_printk_dcf((dev), CT2_VBC_MFUNC_TRACE, "<-")

#else   // CT2_DEBUG

#define ct2_ktrace0(fmt, args...)
#define ct2_ktrace(dev, fmt, args...)

#define ct2_mtrace0_enter
#define ct2_mtrace0_exit
#define ct2_mtrace_enter(dev)
#define ct2_mtrace_exit(dev)

#endif  // !CT2_DEBUG

#define CT2_REG_SIZE                        sizeof(ct2_reg_t)

/*==========================================================================*
 *                           Function definitions                           *
 *==========================================================================*/

/**
 * ct2_init - module initialisation
 */

static
int __init ct2_init( void )
{
    size_t      num_devs_so_far;
    int         rv = 0;


    ct2_mtrace0_enter;

    ct2_printk("ESRF C208/P201 Counter/Timer Driver, %s", drv_revision);

    // XXX: Type-check module parameters here ???

    ct2_list_init(&mod_device_list);
    init_ct2_register_range_luts();


    // ===== MOD_INIT_CLASS_REGISTER =====

    // [include/linux/device.h:class_create()]
    if ( (ct2_class = class_create(THIS_MODULE, CT2_NAME)) == NULL ) {
        ct2_fail0("class_create() = NULL");
        // That's utter speculation.
        return -ENOMEM;
    }

    mod_init_status = MOD_INIT_CLASS_REGISTER;
    ct2_ktrace0("class_create()");


    // ===== MOD_INIT_PCI_REGISTER_DRIVER =====

    // Note that a call to pci_register_driver() will cause ct2_probe()
    // to be called for each device found in the system that matches the
    // ones in the table ct2_device_id_table[].
    // [include/linux/pci.h:pci_register_driver()]
    if ( (rv = pci_register_driver(&ct2_driver)) != 0 ) {
        ct2_fail0("pci_register_driver() = %d", rv);
        goto err;
    }

    mod_init_status = MOD_INIT_PCI_REGISTER_DRIVER;
    ct2_ktrace0("pci_register_driver()");

    num_devs_so_far = ct2_list_length(&mod_device_list);
    if ( num_devs_so_far > 0 ) {
        ct2_notice0("found %zu C208/P201 device%s so far",
                    num_devs_so_far, ( num_devs_so_far == 1 ? "" : "s" ));
    } else {
        ct2_notice0("no C208/P201 device found so far");
    }


    // ===== MOD_INIT_CREATE_DRV_ATTR_FILE =====

    // [drivers/base/driver.c:driver_create_file()]
    if ( (rv = driver_create_file(&ct2_driver.driver, &driver_attr_revision)) != 0 )
        ct2_warn0("driver_create_file(driver_attr_revision) = %d", rv);

    if ( (rv = driver_create_file(&ct2_driver.driver, &driver_attr_status)) != 0 )
        ct2_warn0("driver_create_file(driver_attr_status) = %d", rv);

    mod_init_status = MOD_INIT_CREATE_DRV_ATTR_FILE;
    ct2_ktrace0("driver_create_file()");

    goto done;

err:

    ct2_exit();

done:

    ct2_mtrace0_exit;

    return rv;

}   // ct2_init()

/**
 * ct2_exit - module exit
 */

static
void ct2_exit( void )
{
    ct2_mtrace0_enter;

    switch ( mod_init_status ) {

        case MOD_INIT_CREATE_DRV_ATTR_FILE:

            // [drivers/base/driver.c:driver_remove_file()]
            driver_remove_file(&ct2_driver.driver, &driver_attr_revision);
            driver_remove_file(&ct2_driver.driver, &driver_attr_status);
            ct2_ktrace0("driver_remove_file()");

            // fall through

        case MOD_INIT_PCI_REGISTER_DRIVER:

            // Note that a call to pci_unregister_driver() will cause ct2_remove()
            // to be called for each device previously found (and registered) in the
            // system that match the ones in the table ct2_device_id_table[].
            // [drivers/pci/pci-driver.c:pci_unregister_driver()]
            pci_unregister_driver(&ct2_driver);
            ct2_ktrace0("pci_unregister_driver()");

            // fall through

        case MOD_INIT_CLASS_REGISTER:

            // [drivers/base/class.c:class_destroy()]
            class_destroy(ct2_class);
            ct2_ktrace0("class_destroy()");

            ct2_class = NULL;

            // fall through

        // This keeps the compiler happy.
        case MOD_INIT_UNDEFINED:;
    }

    // ct2_list_clear(&mod_device_list);

    ct2_mtrace0_exit;

}   // ct2_exit()


/*--------------------------------------------------------------------------*
 *                       Device Discovery and Removal                       *
 *--------------------------------------------------------------------------*/

/**
 * ct2_probe - integrate a Device into the system
 */

static
int ct2_probe( struct pci_dev * pci_dev, const struct pci_device_id * id_table )
{
    struct ct2 *        dev;
    struct device *     class_dev;
    struct pci_bus *    pci_bus = pci_dev->bus;
    uint8_t             pci_slot = PCI_SLOT(pci_dev->devfn);
    uint8_t             pci_func = PCI_FUNC(pci_dev->devfn);
    unsigned short      pci_device_id = pci_dev->device;
    const char *        cdev_basename_prefix;
    char                device_name[sizeof(((struct ct2 * )NULL)->cdev.basename)];
    void __iomem *      iomap_ptr;
    unsigned long       buffer_addr;
    uint8_t             intr_pin;
    size_t              kmalloc_size = sizeof(struct ct2);
    gfp_t               kmalloc_flags = GFP_KERNEL | __GFP_NOWARN;
    int                 rv;


    ct2_mtrace0_enter;

    ct2_notice0("found PCI device " CT2_DEVICE_NAME_FMT "; "
                "Vendor = 0x%04x/Device = 0x%04x; "
                "Interrupt Line = %u",
                pci_domain_nr(pci_bus), pci_bus->number, pci_slot, pci_func,
                // XXX: This one contradicts the comment to pci_enable_device() below.
                pci_dev->vendor, pci_device_id, pci_dev->irq);

    // Initialise the driver private data to a known value so that we can
    // safely bail via a call to  ct2_remove()  and evaluate the driver
    // private data field there.
    // [include/linux/pci.h:pci_set_drvdata()]
    pci_set_drvdata(pci_dev, NULL);

    switch ( pci_device_id ) {
        case PCI_DEVICE_ID_ESRF_C208:
            cdev_basename_prefix = CT2_CDEV_BASENAME_PREFIX_C208; break;
        case PCI_DEVICE_ID_ESRF_P201:
            cdev_basename_prefix = CT2_CDEV_BASENAME_PREFIX_P201; break;
        default:
            ct2_error0("can't handle device with PCI Device ID 0x%04x", pci_device_id);
            rv = -EINVAL;
            goto err;
    }

    snprintf(device_name,
             sizeof(device_name),
             CT2_CDEV_BASENAME_FMT,
             cdev_basename_prefix,
             pci_domain_nr(pci_bus),
             pci_bus->number, pci_slot, pci_func);

    // [include/linux/pci.h:pci_read_config_byte()]
    if ( (rv = pci_read_config_byte(pci_dev, PCI_INTERRUPT_PIN, &intr_pin)) != 0 ) {

        ct2_fail0("pci_read_config_byte() = %d for %s", rv, device_name);

        ct2_warn0("treating %s as if it did not generate interrupts", device_name);
        intr_pin = 0;

    } else {

        if ( intr_pin == 0 )
            ct2_warn0("%s claims to not generate interrupts", device_name);
    }



    // ===== DEV_INIT_ALLOC_CT2_STRUCT =====

    // [include/linux/slab_def.h:kmalloc()]
    // [include/linux/slob_def.h:kmalloc()]
    // [include/linux/slub_def.h:kmalloc()]
    if ( (dev = (struct ct2 * )kmalloc(kmalloc_size, kmalloc_flags)) == NULL ) {
        ct2_fail0("kmalloc(%zu, 0x%x) for %s", kmalloc_size, kmalloc_flags, device_name);
        rv = -ENOMEM;
        goto err;
    }

    dev->init_status = DEV_INIT_ALLOC_CT2_STRUCT;
    ct2_ktrace0("kmalloc(%zu) for %s", kmalloc_size, device_name);

    // XXX: ct2_init() anyone ???

    hfl_dl_list_elem_init(&(dev->list_elem));

    // If this was C++ we would not be having this const casting nightmare.
    hfl_const_cast(struct pci_dev *, dev->pci_dev) = pci_dev;
    hfl_const_cast(bool, dev->req_intrs) = ( intr_pin == 0 ? false : true );

    if ( pci_device_id == PCI_DEVICE_ID_ESRF_C208 ) {

        hfl_const_cast(ct2_reg_t, dev->ctrl_it_mask) = C208_CTRL_IT_UMSK;
        hfl_const_cast(const ct2_r1_lut_type *, dev->r1_rd_lut) = &ct2_reg_lut_ident(c208, 1, rd);
        hfl_const_cast(const ct2_r1_lut_type *, dev->r1_wr_lut) = &ct2_reg_lut_ident(c208, 1, wr);
        hfl_const_cast(const ct2_r2_lut_type *, dev->r2_rd_lut) = &ct2_reg_lut_ident(c208, 2, rd);
        hfl_const_cast(const ct2_r2_lut_type *, dev->r2_wr_lut) = &ct2_reg_lut_ident(c208, 2, wr);

    } else {    // PCI_DEVICE_ID_ESRF_P201

        hfl_const_cast(ct2_reg_t, dev->ctrl_it_mask) = P201_CTRL_IT_UMSK;
        hfl_const_cast(const ct2_r1_lut_type *, dev->r1_rd_lut) = &ct2_reg_lut_ident(p201, 1, rd);
        hfl_const_cast(const ct2_r1_lut_type *, dev->r1_wr_lut) = &ct2_reg_lut_ident(p201, 1, wr);
        hfl_const_cast(const ct2_r2_lut_type *, dev->r2_rd_lut) = &ct2_reg_lut_ident(p201, 2, rd);
        hfl_const_cast(const ct2_r2_lut_type *, dev->r2_wr_lut) = &ct2_reg_lut_ident(p201, 2, wr);
    }

    ct2_regs_init(dev);

    snprintf(((char * )dev->cdev.basename),
             sizeof(dev->cdev.basename), device_name);

    ct2_inm_init(dev, distribute_interrupt_notifications);
    ct2_dccs_init(dev);

    // Now that we properly initialised all fields of our Device object,
    // it's time to attach it to the PCI device object so that upon further
    // failures in our init sequence we can clean up by simply invoking
    // ct2_remove()  when we bail.
    pci_set_drvdata(pci_dev, dev);
    ct2_ktrace(dev, "pci_set_drvdata()");



    // ===== DEV_INIT_PCI_DEV_ENABLE =====

    // This call must be made BEFORE trying to get
    // device resources like pci_dev->irq, device->resource[i], etc.
    // [drivers/pci/pci.c:pci_enable_device()]
    if ( (rv = pci_enable_device(pci_dev)) != 0 ) {
        ct2_fail(dev, "pci_enable_device() = %d", rv);
        goto err;
    }

    dev->init_status = DEV_INIT_PCI_DEV_ENABLE;
    ct2_ktrace(dev, "pci_enable_device()");



    // ===== DEV_INIT_AMCC_REGS_REGION =====

    // Before FPGA is loaded we make request region only for AMCC registers
    // space. Other regions are accessible/valid only after FPGA load.
    if ( !check_pci_io_region(dev, CT2_PCI_BAR_AMCC,
                              IORESOURCE_IO, CT2_AMCC_REG_MAP_LEN) ) {
        // Quite.
        rv = -ENXIO;
        goto err;
    }

	/*
     * If there were no FPGA/Virtex to be loaded, then would call here
     * - request_region()      for ALL valid I/O spaces/regions
     * - request_mem_regions() for ALL valid MEMORY spaces/regions
     * [or pci_request_regions() to do this in one go].
     *
     * But in all CUB/PUB-based cards there is FPGA/Virtex to be loaded
     * on the CUB/PUB mother-board before regions other than I/O region
     * pointed to by BADR[CT2_PCI_BAR_AMCC] can be requested
     * and used/accessed.
     * So here call request_region() ONLY for I/O region pointed to by
     * BADR[CT2_PCI_BAR_AMCC], since for loading FPGA/Virtex must access
     * some AMCC operation registers and the access can be made only after
     * requesting this region.
     */
    // [drivers/pci/pci.c:pci_request_region()]
    if ( (rv = pci_request_region(pci_dev, CT2_PCI_BAR_AMCC, CT2_NAME)) != 0 ) {
        ct2_fail(dev, "pci_request_region(CT2_PCI_BAR_AMCC) = %d", rv);
        goto err;
    }

    dev->init_status = DEV_INIT_AMCC_REGS_REGION;
    ct2_ktrace(dev, "pci_request_region(CT2_PCI_BAR_AMCC)");

    // Load the FPGA bitstream in order for the card to become usable.
    if ( (rv = load_fpga_bitstream(dev)) != 0 ) {
        goto err;
    }

    ct2_notice(dev, "successfully loaded bitstream into FPGA");



    // Now that the FPGA is configured, proceed with the BARs
    // of the actually usable device.


    // ===== DEV_INIT_CTRL_REGS_1_REGION =====

    if ( !check_pci_io_region(dev, CT2_PCI_BAR_IO_R1,
                              IORESOURCE_IO, ct2_sizeof_spc(1)) ) {
        rv = -ENXIO;
        goto err;
    }

    if ( (rv = pci_request_region(pci_dev, CT2_PCI_BAR_IO_R1, CT2_NAME)) != 0 ) {
        ct2_fail(dev, "pci_request_region(CT2_PCI_BAR_IO_R1) = %d", rv);
        goto err;
    }

    dev->init_status = DEV_INIT_CTRL_REGS_1_REGION;
    ct2_ktrace(dev, "pci_request_region(CT2_PCI_BAR_IO_R1)");

#if defined CT2_MAP_IOPORTS_TO_IOMEM

    // [lib/iomap.c:pci_iomap()]
    iomap_ptr = pci_iomap(pci_dev, CT2_PCI_BAR_IO_R1, ct2_sizeof_spc(1));
    if ( iomap_ptr == NULL ) {
        ct2_fail(dev, "pci_iomap(CT2_PCI_BAR_IO_R1) = NULL");
        rv = -ENOMEM;
        goto err;
    }

    hfl_const_cast(ct2_r1_io_addr_type, dev->regs.r1) = (ct2_r1_io_addr_type )iomap_ptr;
    ct2_ktrace(dev, "pci_iomap(CT2_PCI_BAR_IO_R1)");

#else   // CT2_MAP_IOPORTS_TO_IOMEM

    // [include/linux/pci.h:pci_resource_start()]
    hfl_const_cast(ct2_r1_io_addr_type, dev->regs.r1) = pci_resource_start(pci_dev, CT2_PCI_BAR_IO_R1);

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM


    // ===== DEV_INIT_CTRL_REGS_2_REGION =====

    if ( !check_pci_io_region(dev, CT2_PCI_BAR_IO_R2,
                              IORESOURCE_IO, ct2_sizeof_spc(2)) ) {
        rv = -ENXIO;
        goto err;
    }

    if ( (rv = pci_request_region(pci_dev, CT2_PCI_BAR_IO_R2, CT2_NAME)) != 0 ) {
        ct2_fail(dev, "pci_request_region(CT2_PCI_BAR_IO_R2) = %d", rv);
        goto err;
    }

    dev->init_status = DEV_INIT_CTRL_REGS_2_REGION;
    ct2_ktrace(dev, "pci_request_region(CT2_PCI_BAR_IO_R2)");

#if defined CT2_MAP_IOPORTS_TO_IOMEM

    iomap_ptr = pci_iomap(pci_dev, CT2_PCI_BAR_IO_R2, ct2_sizeof_spc(2));
    if ( iomap_ptr == NULL ) {
        ct2_fail(dev, "pci_iomap(CT2_PCI_BAR_IO_R2) = NULL");
        rv = -ENOMEM;
        goto err;
    }

    hfl_const_cast(ct2_r2_io_addr_type, dev->regs.r2) = (ct2_r2_io_addr_type )iomap_ptr;
    ct2_ktrace(dev, "pci_iomap(CT2_PCI_BAR_IO_R2)");

#else   // CT2_MAP_IOPORTS_TO_IOMEM

    hfl_const_cast(ct2_r2_io_addr_type, dev->regs.r2) = pci_resource_start(pci_dev, CT2_PCI_BAR_IO_R2);

#endif  // !CT2_MAP_IOPORTS_TO_IOMEM


    // ===== DEV_INIT_FIFO_REGION =====

    // We take any size that fits we get - the larger, the better.
    if ( !check_pci_io_region(dev, CT2_PCI_BAR_FIFO, IORESOURCE_MEM, 0) ) {
        rv = -ENXIO;
        goto err;
    }

    if ( (rv = pci_request_region(pci_dev, CT2_PCI_BAR_FIFO, CT2_NAME)) != 0 ) {
        ct2_fail(dev, "pci_request_region(CT2_PCI_BAR_FIFO) = %d", rv);
        goto err;
    }

    dev->init_status = DEV_INIT_FIFO_REGION;
    ct2_ktrace(dev, "pci_request_region(CT2_PCI_BAR_FIFO)");

    iomap_ptr = pci_iomap(pci_dev, CT2_PCI_BAR_FIFO,
                          pci_resource_len(pci_dev, CT2_PCI_BAR_FIFO));
    if ( iomap_ptr == NULL ) {
        ct2_fail(dev, "pci_iomap(CT2_PCI_BAR_FIFO) = NULL");
        rv = -ENOMEM;
        goto err;
    }

    hfl_const_cast(ct2_reg_t __iomem *, dev->fifo) = (ct2_reg_t __iomem * )iomap_ptr;
    ct2_ktrace(dev, "pci_iomap(CT2_PCI_BAR_FIFO)");

    // [mm/page_alloc.c:__get_free_pages()]
    buffer_addr = __get_free_pages(GFP_KERNEL, CT2_FIFO_GFP_ORDER);
    if ( buffer_addr == 0 ) {
        ct2_fail(dev, "__get_free_pages(CT2_FIFO_GFP_ORDER) = NULL");
        rv = -ENOMEM;
        goto err;
    }

    hfl_const_cast(ct2_reg_t *, dev->fifo_buffer) = (ct2_reg_t * )buffer_addr;
    ct2_ktrace(dev, "__get_free_pages(CT2_FIFO_GFP_ORDER)");

    // Check Low Voltages and Temperatures on the board.  If anything
    // appears to be wrong with the board, we can bail right here and
    // not bother dealing with the kobject infrastructure.  This is so
    // userland really only gets to see a fully functioning and properly
    // initialised device.
    // If any problem, do not load module, but quit, since
    // should not use board when there are serious hardware
    // problems with it. This can be done only for C208, since
    // in P201 registers there is no information on LVs and Temps.
    if ( (rv = check_cub(dev)) != 0 ) {
        // propagate error
        goto err;
    }

    ct2_notice(dev, "CUB seems to be alright");

    // Since our hardware test was successful we are now safe to talk
    // with the device.
    reset_device(dev);


    // ===== DEV_INIT_ALLOC_CHRDEV =====

    // Yeah, that's right, we take the easy way out and
    // completely ignore the major/minor silliness.
    // [fs/char_dev.c:alloc_chrdev_region()]
    if ( (rv = alloc_chrdev_region(((dev_t * )&(dev->cdev.num)), 0, 1,
                                   dev->cdev.basename                 )) != 0 ) {
        ct2_fail(dev, "alloc_chrdev_region() = %d", rv);
        goto err;
    }

    dev->init_status = DEV_INIT_ALLOC_CHRDEV;
    ct2_ktrace(dev, "alloc_chrdev_region()");


    // ===== DEV_INIT_CLASS_DEV =====

    // [drivers/base/core.c:device_create()]
    if ( (class_dev = device_create(ct2_class,
                                    &(pci_dev->dev),
                                    dev->cdev.num,
                                    dev, dev->cdev.basename)) == NULL ) {
        ct2_fail(dev, "device_create() = NULL");
        // Really?
        rv = -ENOMEM;
        goto err;
    }

    hfl_const_cast(struct device *, dev->cdev.class) = class_dev;

    dev->init_status = DEV_INIT_CLASS_DEV;
    ct2_ktrace(dev, "device_create()");


    // ===== DEV_INIT_ADD_CDEV =====

    // [fs/char_dev.c:cdev_init()]
    cdev_init(&(dev->cdev.obj), &ct2_file_ops);
    // Although owner = THIS_MODULE is already in ct2_file_ops,
    // initialize owner field of dev->cdev explicitely as
    // mentioned on upper part of the p.56 in LDD3.
    dev->cdev.obj.owner = THIS_MODULE;
    ct2_ktrace(dev, "cdev_init()");

    // [fs/char_dev.c:cdev_add()]
    if ( (rv = cdev_add(&(dev->cdev.obj), dev->cdev.num, 1)) != 0 ) {
        ct2_fail(dev, "cdev_add() = %d", rv);
        goto err;
    }

    dev->init_status = DEV_INIT_ADD_CDEV;
    ct2_ktrace(dev, "cdev_add()");


    // ===== DEV_INIT_DEV_LIST_ADD =====

    if ( ct2_list_append(&mod_device_list, dev) == NULL ) {
        ct2_fail(dev, "ct2_list_append() = NULL");
        goto err;
    }

    dev->init_status = DEV_INIT_DEV_LIST_ADD;

    goto done;

err:

    ct2_remove(pci_dev);

done:

    ct2_mtrace0_exit;

    return rv;

}   // ct2_probe()

/**
 * ct2_remove - remove a Device from the system
 */

static
void ct2_remove( struct pci_dev * pci_dev )
{
    struct ct2 *    dev;


    ct2_mtrace0_enter;

    // We treat anything but a  NULL  here as a pointer to our Device object.
    // [include/linux/pci.h:pci_get_drvdata()]
    if ( (dev = (struct ct2 * )pci_get_drvdata(pci_dev)) == NULL ) {
        // This is a pre DEV_INIT_ALLOC_CT2_STRUCT call so we can just bail.
        goto done;
    }

    // That'd be a bug in the kernel PCI infrastructure, which is
    // totally out of our league so the only thing we can do is bail.
    if ( pci_dev != dev->pci_dev ) {
        ct2_error0("can't remove two different PCI devices at once");
        goto done;
    }

    ct2_notice(dev, "cleaning up");

    pci_set_drvdata(dev->pci_dev, NULL);

    // XXX: Do we check that all Device mutexes are released ???

    switch ( dev->init_status ) {

        case DEV_INIT_REQ_INTR:

            ct2_disable_interrupts(dev);
            ct2_ktrace(dev, "ct2_disable_interrupts()");

            ct2_inm_fifo_reset(dev);

            // fall through

        case DEV_INIT_DEV_LIST_ADD:

            // XXX: Check return value ???
            ct2_list_remove(&mod_device_list, dev);

            // fall through

        case DEV_INIT_ADD_CDEV:

            // [fs/char_dev.c:cdev_del()]
            cdev_del(&(dev->cdev.obj));
            ct2_ktrace(dev, "cdev_del()");

            // fall through

        case DEV_INIT_CLASS_DEV:

            // [drivers/base/core.c:device_del()]
            device_del(dev->cdev.class);
            ct2_ktrace(dev, "device_del()");

            dev_set_drvdata(dev->cdev.class, NULL);

            // [drivers/base/core.c:put_device()]
            put_device(dev->cdev.class);
            ct2_ktrace(dev, "put_device()");

            // fall through

        case DEV_INIT_ALLOC_CHRDEV:

            // [fs/char_dev.c:unregister_chrdev_region()]
            unregister_chrdev_region(dev->cdev.num, 1);
            ct2_ktrace(dev, "unregister_chrdev_region()");

            // fall through

        case DEV_INIT_FIFO_REGION:

            if ( dev->fifo_buffer != NULL ) {
		unsigned long buffer_addr = (unsigned long) dev->fifo_buffer;
		// [mm/page_alloc.c:free_pages()]
		free_pages(buffer_addr, CT2_FIFO_GFP_ORDER);
                ct2_ktrace(dev, "free_pages(CT2_FIFO_GFP_ORDER)");
            }

            if ( dev->fifo != NULL ) {
                // [lib/iomap.c:pci_iounmap()]
                pci_iounmap(dev->pci_dev, ((void __iomem * )dev->fifo));
                ct2_ktrace(dev, "pci_iounmap()");
            }

            // [drivers/pci/pci.c:pci_release_region()]
            pci_release_region(dev->pci_dev, CT2_PCI_BAR_FIFO);
            ct2_ktrace(dev, "pci_release_region(CT2_PCI_BAR_FIFO)");

            // fall through

        case DEV_INIT_CTRL_REGS_2_REGION:

#if defined CT2_MAP_IOPORTS_TO_IOMEM

            if ( dev->regs.r2 != CT2_REGS_NULL_ADDR ) {
                pci_iounmap(dev->pci_dev, ((void __iomem * )dev->regs.r2));
                ct2_ktrace(dev, "pci_iounmap()");
            }

#endif  // CT2_MAP_IOPORTS_TO_IOMEM

            pci_release_region(dev->pci_dev, CT2_PCI_BAR_IO_R2);
            ct2_ktrace(dev, "pci_release_region(CT2_PCI_BAR_IO_R2)");

            // fall through

        case DEV_INIT_CTRL_REGS_1_REGION:

#if defined CT2_MAP_IOPORTS_TO_IOMEM

            if ( dev->regs.r1 != CT2_REGS_NULL_ADDR ) {
                pci_iounmap(dev->pci_dev, ((void __iomem * )dev->regs.r1));
                ct2_ktrace(dev, "pci_iounmap()");
            }

#endif  // CT2_MAP_IOPORTS_TO_IOMEM

            pci_release_region(dev->pci_dev, CT2_PCI_BAR_IO_R1);
            ct2_ktrace(dev, "pci_release_region(CT2_PCI_BAR_IO_R1)");

            // fall through

        case DEV_INIT_AMCC_REGS_REGION:

            pci_release_region(dev->pci_dev, CT2_PCI_BAR_AMCC);
            ct2_ktrace(dev, "pci_release_region(CT2_PCI_BAR_AMCC)");

            // fall through

        case DEV_INIT_PCI_DEV_ENABLE:

            // pci_disable_device() must be called AFTER releasing regions
            // [drivers/pci/pci.c:pci_disable_device()]
            pci_disable_device(dev->pci_dev);
            ct2_ktrace(dev, "pci_disable_device()");

            // fall through

        case DEV_INIT_ALLOC_CT2_STRUCT:

            // Was moved from here to the beginning of the function
            // as was done in c216 driver:
            // pci_set_drvdata(dev->pci_dev, NULL);
            kfree(dev);
            ct2_ktrace0("kfree()");

    }   // dev->init_status

done:

    ct2_mtrace0_exit;

}   // ct2_remove()


/*--------------------------------------------------------------------------*
 *                        Device open(2) and close(2)                       *
 *--------------------------------------------------------------------------*/

/**
 * ct2_open - Device implementation of open(2)
 */

static
int ct2_open( struct inode * inode, struct file * file )
{
    struct ct2 *        dev = container_of(inode->i_cdev, struct ct2, cdev.obj);
    struct ct2_dcc *    dcc;
    gfp_t               kmalloc_flags = GFP_KERNEL | __GFP_NOWARN;
    size_t              dcc_count;
    int                 rv = 0;


    ct2_mtrace_enter(dev);

    // If we are not to block, make sure we do so everywhere.
    if ( file->f_flags & O_NONBLOCK )
        kmalloc_flags |= __GFP_NORETRY;

    dcc = ct2_dcc_new(kmalloc_flags, dev);
    file->private_data = dcc;

    if ( dcc == NULL ) {

        ct2_fail(dev, "ct2_dcc_new(flags=0x%x) = NULL", kmalloc_flags);

        if ( file->f_flags & O_NONBLOCK )
            // XXX: Really ???
            rv = -EAGAIN;
        else
            rv = -ENOMEM;

        goto done;
    }

    ct2_dccs_swi_nl(dev, rv, { goto delete_then_done; }, {

        // Don't forget to tell the DCC that we already
        // have arranged for interrupts to be delivered.
        if ( dev->init_status == DEV_INIT_REQ_INTR )
            ct2_dcc_en_intr(dcc);

        ct2_dccs_add_dcc(dev, dcc);
        dcc_count = ct2_dccs_count(dev);
    })

    ct2_notice(dev, "DCC count: %zu", dcc_count);

    goto done;

delete_then_done:

    ct2_dcc_delete(dcc);
    file->private_data = NULL;

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // ct2_open()

/**
 * ct2_close - Device implementation of close(2)
 */

static
int ct2_close( struct inode * inode, struct file * file )
{
    struct ct2_dcc *    dcc = (struct ct2_dcc * )file->private_data;
    struct ct2 *        dev = dcc->dev;
    int                 rv = 0;


    ct2_mtrace_enter(dev);

    ct2_dccs_swi(dev, rv, { goto done; }, {

        // We allow a given DCC resp. open file description to be
        // released if either it has not been granted exclusive Device
        // access or it has exclusive Device access but the FIFO is not
        // mmap(2)'ed during the release attempt.

        if ( ct2_dcc_has_xaccess(dev, dcc) ) {

            if ( ct2_is_mmapped(dev) ) {
                rv = -EBUSY;
                goto ct2_dccs_swi_end;
            }

            // If the DCC has been granted exclusive Device access while
            // it is being released, exclusivity is given up right here
            // on the spot.
            ct2_revoke_xaccess(dev);
        }

        dcc = ct2_dccs_remove_dcc(dev, dcc);
    })

    // Intercept an  EBUSY  here before we take it any further.
    if ( rv != 0 )
        goto done;

    // This is not supposed to happen.
    if ( dcc == NULL ) {
        ct2_internal(dev, "ct2_dccs_remove_dcc() = NULL");
        goto done;
    }

    ct2_dcc_delete(dcc);
    file->private_data = NULL;

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // ct2_close()


/*--------------------------------------------------------------------------*
 *                  Device read(2), write(2), and llseek(2)                 *
 *--------------------------------------------------------------------------*/

// Make sure that our premisses assumed true below actually hold.

#if ( ( CT2_RW_R1_OFF != 0 )                                || \
      ( CT2_RW_R2_OFF != (1 << 6) )                         || \
      ( CT2_RW_R1_LEN != (CT2_RW_R2_OFF - CT2_RW_R1_OFF) )  || \
      ( CT2_RW_R2_LEN != 64 )                                  )
# error "At least one of CT2_RW_R1_OFF, CT2_RW_R2_OFF, \
CT2_RW_R1_LEN, or CT2_RW_R2_LEN are inconsistent with our RW map implementation."
#endif

#define CT2_RW_RMAP_LEN             (CT2_RW_R2_OFF + CT2_RW_R2_LEN)
#define CT2_LONGEST_RREAD_RANGE     (ct2_reg_interval_size(2, sel_filtre_input[0], conf_cmpt[11]))
#define CT2_LONGEST_RWRITE_RANGE    (ct2_reg_interval_size(2, sel_filtre_input[0], compare_cmpt[11]))

#define CT2_RW_FIFO_START           (CT2_RW_FIFO_OFF * CT2_REG_SIZE)
#define CT2_RW_FIFO_END             (CT2_RW_FIFO_START + \
				     CT2_RW_FIFO_LEN * CT2_REG_SIZE)

/**
 * offset_to_baddr_lut_off - compute register file I/O parameters
 * @offset: RW map offset
 * @r1:     kernel I/O port (mapped virtual) address of PCI I/O Space 1
 * @r2:     kernel I/O port (mapped virtual) address of PCI I/O Space 2
 * @r1_lut: pointer to the LUT for @r1
 * @r2_lut: pointer to the LUT for @r2
 * @baddr:  pointer to an object, where either @r1 or @r2,
 *          depending on the value of @offset, will be stored
 * @lut:    pointer to an object, where the adress of the first element
 *          of either @r1_lut or @r2_lut, depending on the value of @offset,
 *          will be stored
 * @off:    pointer to an object, where the register offset relative to
 *          either PCI I/O Space 1 or 2, depending on the value of @offset,
 *          will be stored
 *
 * Identify a register and compute its offset in register units w.r.t.
 * its register space from @offset.
 *
 * The return value represents the offset into the "normalised" RW map
 * in the sense that it is guaranteed to contain only values inside the
 * interval [0, CT2_RW_RMAP_LEN).
 */

static inline
uint8_t offset_to_baddr_lut_off( loff_t                     offset,
                                 ct2_r1_io_addr_type        r1,
                                 ct2_r2_io_addr_type        r2,
                                 const ct2_r1_lut_type *    r1_lut,
                                 const ct2_r2_lut_type *    r2_lut,
                                 ct2_regs_io_addr_type *    baddr,
                                 const ct2_reg_dist_t **    lut,
                                 ct2_reg_dist_t *           off     )
{
    uint8_t     rw_rmap_offset;
    uint8_t     r2_offset, r2_offset_flag;


    //   oo oooo
    //  rff ffff
    // 02ff ffff
    rw_rmap_offset = ((uint8_t ) (offset / CT2_REG_SIZE)) & 0x7f;

    //  r
    // 0200 0000
    r2_offset = (1 << 6) & rw_rmap_offset;

    //   oo oooo
    //   ff ffff
    // 00ff ffff
    // (cf. (rw_rmap_offset - r2_offset)
    (*off) = rw_rmap_offset & (~(1 << 6));

    // if ( r2_offset != 0 ) {
    //     (*baddr) = &(r2->sel_filtre_input[0]);
    //     (*lut) = r2_lut;
    // } else {
    //     (*baddr) = &(r1->com_gene);
    //     (*lut) = r1_lut;
    // }
    r2_offset_flag = r2_offset != 0;
    (*baddr) = (ct2_regs_io_addr_type )(((ct2_io_addr_uint_type )r2) *        r2_offset_flag  +
                                        ((ct2_io_addr_uint_type )r1) * (0x1 ^ r2_offset_flag)   );
    (*lut)   = (const ct2_reg_dist_t * )(((uintptr_t )r2_lut) *        r2_offset_flag  +
                                         ((uintptr_t )r1_lut) * (0x1 ^ r2_offset_flag)   );

    return rw_rmap_offset;
}

/**
 * ct2_read - Device implementation of (p)read(v)(2)
 */

static
ssize_t ct2_read( struct file * file,
                  char __user * buf,
                  size_t        count,
                  loff_t *      offset )
{
    struct ct2_dcc *        dcc = (struct ct2_dcc * )file->private_data;
    struct ct2 *            dev = dcc->dev;
    ct2_regs_io_addr_type   raddr_base;
    const ct2_reg_dist_t *  rlut;
    ct2_reg_t               rbuf[CT2_LONGEST_RREAD_RANGE];
    ct2_reg_dist_t          roff, rcount;
    size_t                  bcount;
    uint8_t                 rw_rmap_offset;
    bool                    einval, rrange_contains_R;
    ssize_t                 rv = 0;

    ct2_mtrace_enter(dev);

    if (hfl_in_interval_ix(loff_t, (*offset), CT2_RW_FIFO_START, 
			   CT2_RW_FIFO_END) &&
	hfl_in_interval_ix(loff_t, (*offset + count - 1), CT2_RW_FIFO_START, 
			   CT2_RW_FIFO_END))
	return ct2_read_fifo(file, buf, count, offset);

    // Assume
    //          ( 0 <= (*offset) ) && ( (*offset) < CT2_RW_RMAP_LEN * CT2_REG_SIZE )
    // holds.
    einval = !hfl_in_interval_ix(loff_t, (*offset), 0, CT2_RW_RMAP_LEN * CT2_REG_SIZE);

    // We want the register offset into the normalised RW map
    // for our access control check(s).
    rw_rmap_offset = offset_to_baddr_lut_off((*offset),
                                             dev->regs.r1, dev->regs.r2,
                                             dev->r1_rd_lut, dev->r2_rd_lut,
                                             &raddr_base, &rlut, &roff      );

    // Offsets for which there are no registers defined have their
    // lengths set to  0  in the LUTs and will therefore trigger an error
    // here.  This is especially true regarding the test for the existence
    // of and the access to  p201_test_reg  which is implicitly contained
    // in the construction of the I/O Space 1 LUTs in
    // init_ct2_register_range_luts().

    // If we were to take  count  into consideration here, we might come
    // to false conclusions, as a read length of zero, although meaningless,
    // is not strictly illegal, but the access to a register at an invalid
    // offset is - regardless of the actual read length to be performed at
    // that offset.
    if ( einval || ( rlut[roff] == 0 ) ) {
        rv = -EINVAL;
        goto done;
    }

    // [include/linux/kernel.h:min_t()]
    rcount = min_t(ct2_reg_dist_t, rlut[roff], count / CT2_REG_SIZE);
    bcount = rcount * CT2_REG_SIZE;

    // Instead of tearing up the normalised RW map we went to great lengths
    // to to construct in the first place, we simply look at the register
    // read range whether it contains access controlled register(s).
    rrange_contains_R = hfl_in_interval_ix(uint8_t,
                                           ct2_reg_offset(1, ctrl_fifo_dma),
                                           rw_rmap_offset, (rw_rmap_offset + rcount)) ||
                        hfl_in_interval_ix(uint8_t,
                                           ct2_reg_offset(1, p201_test_reg),
                                           rw_rmap_offset, (rw_rmap_offset + rcount))   ;

    // Device access via DCCs must be serialised across all DCCs.
    ct2_dccs_sri(dev, rv, { goto done; }, {

        if ( !ct2_dcc_may_change_dev_state(dev, dcc) && rrange_contains_R ) {
            rv = -EACCES;
            goto ct2_dccs_sri_end;
        }

        // Copy the data from the device registers, ...
        ct2_regs_readv_sync(dev, ct2_io_addr_subscript(raddr_base, roff), rbuf, rcount);
    })

    // ..., possibly intercept an EACCES generated inside the critical section, ...
    if ( rv != 0 )
        goto done;

    // ... and (again) copy it out into userland.
    // [include/asm-generic/uaccess.h:copy_to_user()]
    if ( copy_to_user(buf, rbuf, bcount) != 0 ) {
        rv = -EFAULT;
        goto done;
    }

    // Return the actual number of (adjacent) registers read.
    (*offset) += bcount;
    rv = bcount;

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // ct2_read()

/**
 * ct2_read_fifo - Device implementation of (p)read(v)(2) for FIFO area
 *
 * Note: Will not check the available words in FIFO to avoid reseting
 * the error flags. Asume that the user already queried how much
 * data can be read
 */

static
ssize_t ct2_read_fifo( struct file * file,
		       char __user * buf,
		       size_t        count,
		       loff_t *      offset )
{
    struct ct2_dcc *        dcc = (struct ct2_dcc * )file->private_data;
    struct ct2 *            dev = dcc->dev;
    ct2_reg_t               i, nb_regs = count / CT2_REG_SIZE;
    ct2_reg_t __iomem *     fifo = dev->fifo;
    ct2_reg_t *             buffer = dev->fifo_buffer;
    ssize_t                 rv = 0;

    ct2_mtrace_enter(dev);

    // Device access via DCCs must be serialised across all DCCs.
    ct2_dccs_sri(dev, rv, { goto done; }, {

        // Reading the FIFO changes the device state
        if ( !ct2_dcc_may_change_dev_state(dev, dcc) ) {
            rv = -EACCES;
            goto ct2_dccs_sri_end;
        }

        // Copy the data directly from the FIFO to a kernel buffer, 
	// so we're sure it will not sleep
	for ( i = 0; i < nb_regs; i++ )
	    *buffer++ = readl(fifo++);
    })

    // ..., possibly intercept an EACCES generated inside the critical section, ...
    if ( rv != 0 )
        goto done;

    // ... and (again) copy it out into userland.
    // [include/asm-generic/uaccess.h:copy_to_user()]
    if ( copy_to_user(buf, dev->fifo_buffer, count) != 0 ) {
        rv = -EFAULT;
        goto done;
    }

    // Return the actual number of bytes read.
    (*offset) += count;
    rv = count;

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // ct2_read_fifo()

/**
 * ct2_write - Device implementation of (p)write(v)(2)
 */

static
ssize_t ct2_write( struct file *        file,
                   const char __user *  buf,
                   size_t               count,
                   loff_t *             offset )
{
    struct ct2_dcc *        dcc = (struct ct2_dcc * )file->private_data;
    struct ct2 *            dev = dcc->dev;
    ct2_regs_io_addr_type   waddr_base;
    const ct2_reg_dist_t *  wlut;
    ct2_reg_t               wbuf[CT2_LONGEST_RWRITE_RANGE];
    ct2_reg_dist_t          woff, rcount;
    size_t                  bcount;
    bool                    einval;
    ssize_t                 cfu_rv = 0;
    ssize_t                 rv = 0;


    ct2_mtrace_enter(dev);

    // cf. ct2_read()
    einval = !hfl_in_interval_ix(loff_t, (*offset), 0, CT2_RW_RMAP_LEN * CT2_REG_SIZE);

    // Since writing is a state changing operation, access control
    // checks based on register offsets do not make sense here.
    offset_to_baddr_lut_off((*offset),
                            dev->regs.r1, dev->regs.r2,
                            dev->r1_wr_lut, dev->r2_wr_lut,
                            &waddr_base, &wlut, &woff      );

    if ( einval || ( wlut[woff] == 0 ) ) {
        rv = -EINVAL;
        goto done;
    }

    rcount = min_t(ct2_reg_dist_t, wlut[woff], count / CT2_REG_SIZE);
    bcount = rcount * CT2_REG_SIZE;

    // Speculatively copy the data from userland into our transfer buffer.
    // [include/asm-generic/uaccess.h:copy_from_user()]
    if ( copy_from_user(wbuf, buf, bcount) != 0 )
        cfu_rv = -EFAULT;

    ct2_dccs_sri(dev, rv, { goto done; }, {

        if ( !ct2_dcc_may_change_dev_state(dev, dcc) ) {
            rv = -EACCES;
            goto ct2_dccs_sri_end;
        }

        // A non-zero value of  cfu_rv  at this point indicates
        // a storage access violation committed by the calling process
        // while we attempted to copy the data to be written from
        // user space.
        if ( cfu_rv != 0 ) {
            rv = cfu_rv;
            goto ct2_dccs_sri_end;
        }

        // Now copy (again) the data out into the device registers.
        ct2_regs_writev_sync(dev, wbuf, ct2_io_addr_subscript(waddr_base, woff), rcount);

        (*offset) += bcount;
        rv = bcount;
    })

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // ct2_write()

/**
 * ct2_llseek - Device implementation of lseek(2)
 */

static
loff_t ct2_llseek( struct file * file, loff_t offset, int whence )
{
    loff_t      off;


    ct2_mtrace_enter(((struct ct2_dcc * )(file->private_data))->dev);

    switch ( whence ) {

        case SEEK_SET: off = offset; break;
        case SEEK_CUR: off = file->f_pos + offset; break;
        case SEEK_END: off = CT2_RW_RMAP_LEN + offset; break;

        default:
            off = -EINVAL;
            goto done;
    }

    if ( !hfl_in_interval_ix(loff_t, off, 0, CT2_RW_RMAP_LEN) )
        off = -EINVAL;

done:

    ct2_mtrace_exit(((struct ct2_dcc * )(file->private_data))->dev);

    return off;

}   // ct2_llseek()


/*--------------------------------------------------------------------------*
 *                              Device ioctl(2)                             *
 *--------------------------------------------------------------------------*/

/**
 * ct2_ioctl - Device implementation of ioctl(2)
 */

static
int ct2_ioctl( struct inode *   inode,
               struct file *    file,
               unsigned int     cmd,
               u_long           user_arg )
{
    struct ct2_dcc *    dcc = (struct ct2_dcc * )file->private_data;
    struct ct2 *        dev = dcc->dev;
    int                 rv = 0;


    ct2_mtrace_enter(dev);

    // Extract the type and number bitfields, and don't decode
    // wrong cmds: return EINVAL if magic number or command number invalid.
    // [include/asm-generic/ioctl.h:_IOC_TYPE()]
    if ( _IOC_TYPE(cmd) != CT2_IOC_MAGIC ) {
        ct2_error(dev, "wrong magic number 0x%x (expected 0x%x)", _IOC_TYPE(cmd), CT2_IOC_MAGIC);
        rv = -EINVAL;
        goto done;
    }

    // The order of commands follows the required processing efficiency
    // of the commands.  The less time critical the execution of a command
    // is, the farther down the end it appears in the switch statement.
    switch ( cmd ) {

        case CT2_IOC_ACKINT:

            rv = acknowledge_interrupt(dcc, ((struct ct2_in __user * )user_arg));
            break;

        case CT2_IOC_AINQ:

            rv = attach_inq(dcc, ((ct2_size_type )user_arg));
            break;

        case CT2_IOC_DINQ:

            detach_inq(dcc);
            break;

        case CT2_IOC_RINQ:

            rv = drain_inq(dcc, file, ((struct ct2_inv __user * )user_arg));
            break;

        case CT2_IOC_FINQ:

            rv = flush_inq(dcc, ((struct timespec __user * )user_arg));
            break;

        case CT2_IOC_DEVRST:

            // Device access via DCCs must be serialised across all DCCs.
            ct2_dccs_sri(dev, rv, { goto done; }, {

                if ( !ct2_dcc_may_change_dev_state(dev, dcc) ) {
                    rv = -EACCES;
                    goto ct2_dccs_sri_end;
                }

                // We make it a prerequisite for a Device reset
                // that interrupts be disabled to avoid having to
                // serialise long accesses to both register files.
                if ( dev->init_status == DEV_INIT_REQ_INTR ) {
                    rv = -EBUSY;
                    goto ct2_dccs_sri_end;
                }

                reset_device(dev);
            })

            break;

        case CT2_IOC_EDINT:

            rv = enable_device_interrupts(dcc, file, ((ct2_size_type )user_arg));
            break;

        case CT2_IOC_DDINT:

            rv = disable_device_interrupts(dcc);
            break;

        case CT2_IOC_QXA:

            rv = grant_exclusive_access(dcc);
            break;

        case CT2_IOC_LXA:

            rv = revoke_exclusive_access(dcc);
            break;

        default:

            ct2_error(dev, "illegal command 0x%x", cmd);
            rv = -EINVAL;
    }

done:

    ct2_mtrace_exit(dev);

	return rv;

}   // ct2_ioctl()


/*--------------------------------------------------------------------------*
 *                        Device mmap(2) and poll(2)                        *
 *--------------------------------------------------------------------------*/

#if ( CT2_MM_FIFO_OFF != 0 )
# error "CT2_MM_FIFO_OFF is inconsistent with our mmap(2) implementation."
#endif

static
void ct2_vma_ops_open( struct vm_area_struct * vma )
{
    struct ct2 *    dev = (struct ct2 * )vma->vm_private_data;


    ct2_mtrace_enter(dev);

    ct2_dccs_sw(dev, {
        ct2_add_mmap(dev);
    })

    ct2_mtrace_exit(dev);
}

static
void ct2_vma_ops_close( struct vm_area_struct * vma )
{
    struct ct2 *    dev = (struct ct2 * )vma->vm_private_data;


    ct2_mtrace_enter(dev);

    ct2_dccs_sw(dev, {
        ct2_remove_mmap(dev);
    })

    ct2_mtrace_exit(dev);
}

static const struct vm_operations_struct ct2_vm_ops = {

    .open   = ct2_vma_ops_open,
    .close  = ct2_vma_ops_close,
};

/**
 * ct2_mmap - Device implementation of mmap(2)
 */

static
int ct2_mmap( struct file * file, struct vm_area_struct * vma )
{
    struct ct2_dcc *    dcc = (struct ct2_dcc * )file->private_data;
    struct ct2 *        dev = dcc->dev;
    struct pci_dev *    pci_dev = dev->pci_dev;
    // [include/linux/ioport.h:struct resource]
    resource_size_t     m, p, x;
    // [include/linux/mm_types.h:struct vm_area_struct]
    unsigned long       map_length = vma->vm_end - vma->vm_start;
    unsigned long       map_offset = vma->vm_pgoff << PAGE_SHIFT;
    int                 rv;


    ct2_mtrace_enter(dev);

    // We take the mmap(2) length literally and do /not/ silently truncate.
    if ( ( vma->vm_flags & (VM_WRITE|VM_EXEC) ) ||
         ( (map_offset + map_length) > pci_resource_len(pci_dev, CT2_PCI_BAR_FIFO) ) ) {
        rv = -EINVAL;
        goto done;
    }

    // [include/asm-generic/pgtable.h:pgprot_noncached()]
    vma->vm_page_prot = pgprot_noncached(vma->vm_page_prot);
    vma->vm_flags |= VM_IO;

    // Although, by inspection and definition, we are provided with an
    // /offset/ in units of a page size into our FIFO's region by the
    // syscall infrastructure, the FIFO region's physical start address,
    // r, and consequently the physical start address of the region to
    // be mapped,  m = r + map_offset, need not actually coincide with
    // the physical start address,  p = addr(pfn(m)), of the page  m
    // happens to lie in.  The shift to obtain the PFN for  m, pfn(m),
    // would simply throw away this information.  Since, according to
    // the user, the mapping is to be performed over  map_length  starting
    // from  m, ie over the interval  [m, m + map_length), and not
    // [p, p + map_length), as the interface to  io_remap_pfn_range()
    // suggests, we need to introduce  x  to account for the possible
    // case that  p < m, or equivalenty,  p + map_length < m + map_length,
    // such that  p + map_length + x = m + map_length  holds.
    // [mmap(2), include/linux/mm_types.h:struct vm_area_struct::vm_pgoff]
    m = pci_resource_start(pci_dev, CT2_PCI_BAR_FIFO) + map_offset;
    p = ((m >> PAGE_SHIFT) << PAGE_SHIFT);
    x = m - p;

    ct2_dccs_srt(dev, rv, { goto done; }, {

        if ( !ct2_dcc_has_xaccess(dev, dcc) ) {
            rv = -EACCES;
            goto ct2_dccs_srt_end;
        }

        // [arch/<arch>/include/asm/pgtable.h:io_remap_pfn_range()]
        if ( (rv = io_remap_pfn_range(vma, vma->vm_start,
                                      m >> PAGE_SHIFT, (map_length + x),
                                      vma->vm_page_prot                 )) != 0 )
            goto ct2_dccs_srt_end;

        ct2_add_mmap(dev);
        vma->vm_ops = &ct2_vm_ops;
        vma->vm_private_data = dev;
    })

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // ct2_mmap()
    
/**
 * ct2_poll - Device implementation of (e)poll(2)  and  select(2)
 */

static
unsigned int ct2_poll( struct file * file, poll_table * pt )
{
    struct ct2_dcc *    dcc = (struct ct2_dcc * )file->private_data;
    struct ct2 *        dev = dcc->dev;
    unsigned int        rv = 0;


    ct2_mtrace_enter(dev);

    ct2_dcc_poll_wait(dcc, file, pt);

    ct2_dccs_sr(dev, {

        if ( ct2_dcc_ins_available(dcc) )
            rv |= POLLIN | POLLRDNORM;

        // When interrupts are not enabled, it would
        // be rude to keep people hanging here forever.
        if ( !ct2_dcc_rcvs_intr(dcc) )
            rv |= POLLHUP;
    })

    ct2_mtrace_exit(dev);

    return rv;

}   // ct2_poll()


/*--------------------------------------------------------------------------*
 *                           Interrupt Processing                           *
 *--------------------------------------------------------------------------*/

/**
 * process_device_interrupts - bottom half of interrupt handling
 */

static
irqreturn_t process_device_interrupts( int intr_line, struct ct2 * dev )
{
    struct ct2_in   notice;


    // [kernel/time/timekeeping.c:getrawmonotonic()]
    getrawmonotonic(&(notice.stamp));
    notice.ctrl_it = (ct2_regs_read_sync_hi(dev, 1, ctrl_it) & dev->ctrl_it_mask);

    // Check if any IT control/status bit is set;
    // if none of bits is set in this register it means that the
    // interrupt is due to another device which uses the same
    // shared IRQ line.
    if ( notice.ctrl_it == 0 )
        // not ours
        return IRQ_NONE;

    ct2_post_in(dev, &notice);

    return IRQ_HANDLED;

}   // process_device_interrupts()

/**
 * distribute_interrupt_notifications - top half of interrupt handling
 */

static
void distribute_interrupt_notifications( struct work_struct * task )
{
    struct ct2 *        dev = container_of(task, struct ct2, inm.task);
    struct ct2_in       notice;


    // This is just to keep the compiler happy.
    notice.ctrl_it = 0;
    notice.stamp.tv_sec = 0;
    notice.stamp.tv_nsec = 0;

    while ( ct2_inm_fifo_fillpoint(dev) > 0 ) {

        ct2_receive_in(dev, &notice);

        // Tasklets are not interruptible.
        ct2_dccs_sr(dev, {
            ct2_dccs_for_each(dev, dcc, {
                ct2_dcc_post_in(dcc, &notice);
            });
        })
    }

}   // distribute_interrupt_notifications()


/*--------------------------------------------------------------------------*
 *                               Local Helpers                              *
 *--------------------------------------------------------------------------*/

/**
 * define_lut_entries - fill an interval of entries of a LUT
 * @lut:    reference to the first entry in the LUT
 * @lower:  starting register offset
 * @upper:  ending register offset
 *
 * The register offsets are defined such that
 *
 *  @lower == ct2_reg_offset(s, l)
 *
 *  @upper == ct2_reg_offset(s, u)
 *
 * and
 *
 *  @lower <= @upper
 *
 * for the given register space  s  and register names  l  and  u
 * simultaneously hold.
 */

static
void define_lut_entries( ct2_reg_dist_t lut[], unsigned int lower, unsigned int upper )
{
    while ( lower < upper ) {
        // cf. ct2_reg_interval_size()
        lut[lower] = (upper - lower) + 1;
        lower = lower + 1;
    }

    lut[upper] = 1;
}

/**
 * clear_ct2_reg_lut - initialise a LUT object
 * @ct2:    { c208, p201 }
 * @spc:    { 1, 2 }
 * @rw:     { rd, wr }
 */

#define clear_ct2_reg_lut(ct2, spc, rw)                                     \
    memset(&ct2_reg_lut_ident(ct2, spc, rw), 0x0,                           \
           sizeof(ct2_reg_lut_ident(ct2, spc, rw)))

/**
 * define_ct2_reg_lut_range - fill an interval of entries of a LUT using register names
 * @ct2:    { c208, p201 }
 * @spc:    { 1, 2 }
 * @rw:     { rd, wr }
 * @lower:  unprefixed register name within @spc for @ct2
 * @upper:  unprefixed register name within @spc for @ct2
 */

#define define_ct2_reg_lut_range(ct2, spc, rw, lower, upper)                            \
    define_lut_entries(((ct2_reg_dist_t * )&(ct2_reg_lut_ident(ct2, spc, rw)[0])),      \
                       ct2_reg_offset(spc, ct2 ## _ ## lower),                          \
                       ct2_reg_offset(spc, ct2 ## _ ## upper)                     )

/**
 * init_ct2_register_range_luts - construct the register file LUTs
 *
 * For each Device type and register file, we construct a read LUT
 * and write LUT which are used in the  ct2_read()  and  ct2_write()
 * methods, respectively, for our "register file type checks".
 */

static
void init_ct2_register_range_luts( void )
{
    // C208

    // I/O Space 1

    clear_ct2_reg_lut(c208, 1, rd);
    define_ct2_reg_lut_range(c208, 1, rd, com_gene, /* [ctrl_fifo_dma] */ source_it[1]);
    // [ctrl_it]
    // (_0x34_0x37.c208._reserved)
    // (_0x38_0x3f._reserved)
    define_ct2_reg_lut_range(c208, 1, rd, rd_cmpt[0], rd_latch_cmpt[11]);
    // (_0xa0_0xfb._reserved)
    // (_0xfc_0xff.c208._reserved)

    clear_ct2_reg_lut(c208, 1, wr);
    define_ct2_reg_lut_range(c208, 1, wr, com_gene, com_gene);
    // (ctrl_gene)
    // (temps)
    define_ct2_reg_lut_range(c208, 1, wr, niveau_out, soft_out);
    // (rd_in_out)
    // (rd_ctrl_cmpt)
    define_ct2_reg_lut_range(c208, 1, wr, cmd_dma, cmd_dma);
    // (ctrl_fifo_dma)
    define_ct2_reg_lut_range(c208, 1, wr, source_it[0], source_it[1]);
    // (ctrl_it)
    // (_0x34_0x37.c208._reserved)
    // (_0x38_0x3f._reserved)
    // (rd_cmpt)
    // (rd_latch_cmpt)
    // (_0xa0_0xfb._reserved)
    // (_0xfc_0xff.c208._reserved)

    // I/O Space 2

    clear_ct2_reg_lut(c208, 2, rd);
    define_ct2_reg_lut_range(c208, 2, rd, sel_filtre_input[0], conf_cmpt[11]);
    // (soft_enable_disable)
    // (soft_start_stop)
    // (soft_latch)
    define_ct2_reg_lut_range(c208, 2, rd, compare_cmpt[0], compare_cmpt[11]);
    // (_0xa4_0xff._reserved)

    clear_ct2_reg_lut(c208, 2, wr);
    define_ct2_reg_lut_range(c208, 2, wr, sel_filtre_input[0], compare_cmpt[11]);
    // (_0xa4_0xff._reserved)


    // P201

    // I/O Space 1

    clear_ct2_reg_lut(p201, 1, rd);
    define_ct2_reg_lut_range(p201, 1, rd, com_gene, ctrl_gene);
    // (_0x08_0x0b.p201._reserved)
    define_ct2_reg_lut_range(p201, 1, rd, niveau_out, /* [ctrl_fifo_dma] */ source_it[1]);
    // [ctrl_it]
    define_ct2_reg_lut_range(p201, 1, rd, niveau_in, niveau_in);
    // (_0x38_0x3f._reserved)
    define_ct2_reg_lut_range(p201, 1, rd, rd_cmpt[0], rd_latch_cmpt[11]);
    // (_0xa0_0xfb._reserved)
    if ( enable_p201_test_reg )
        define_ct2_reg_lut_range(p201, 1, rd, test_reg, test_reg);

    clear_ct2_reg_lut(p201, 1, wr);
    define_ct2_reg_lut_range(p201, 1, wr, com_gene, com_gene);
    // (ctrl_gene)
    // (_0x08_0x0b.p201._reserved)
    define_ct2_reg_lut_range(p201, 1, wr, niveau_out, soft_out);
    // (rd_in_out)
    // (rd_ctrl_cmpt)
    define_ct2_reg_lut_range(p201, 1, wr, cmd_dma, cmd_dma);
    // (ctrl_fifo_dma)
    define_ct2_reg_lut_range(p201, 1, wr, source_it[0], source_it[1]);
    // (ctrl_it)
    define_ct2_reg_lut_range(p201, 1, wr, niveau_in, niveau_in);
    // (_0x38_0x3f._reserved)
    // (rd_cmpt)
    // (rd_latch_cmpt)
    // (_0xa0_0xfb._reserved)
    if ( enable_p201_test_reg )
        define_ct2_reg_lut_range(p201, 1, wr, test_reg, test_reg);

    // I/O Space 2

    clear_ct2_reg_lut(p201, 2, rd);
    define_ct2_reg_lut_range(p201, 2, rd, sel_filtre_input[0], sel_filtre_input[1]);
    // (_0x08_0x13.p201._reserved)
    define_ct2_reg_lut_range(p201, 2, rd, sel_filtre_output, sel_filtre_output);
    // (_0x14_0x1f.p201._reserved)
    define_ct2_reg_lut_range(p201, 2, rd, sel_source_output, conf_cmpt[11]);
    // (soft_enable_disable)
    // (soft_start_stop)
    // (soft_latch)
    define_ct2_reg_lut_range(p201, 2, rd, compare_cmpt[0], compare_cmpt[11]);
    // (_0xa4_0xff._reserved)

    clear_ct2_reg_lut(p201, 2, wr);
    define_ct2_reg_lut_range(p201, 2, wr, sel_filtre_input[0], sel_filtre_input[1]);
    // (_0x08_0x13.p201._reserved)
    define_ct2_reg_lut_range(p201, 2, wr, sel_filtre_output, sel_filtre_output);
    // (_0x14_0x1f.p201._reserved)
    define_ct2_reg_lut_range(p201, 2, wr, sel_source_output, compare_cmpt[11]);
    // (_0xa4_0xff._reserved)

}   // init_ct2_register_range_luts()

static
bool check_pci_io_region( const struct ct2 * dev,
                          unsigned int       bar,
                          unsigned int       expected_type,
                          size_t             minimum_len    )
{
    struct pci_dev *    pci_dev = dev->pci_dev;
    unsigned int        type, len;


    ct2_mtrace_enter(dev);

    // [include/linux/pci.h:pci_resource_flags(), include/linux/ioport.h]
    type = (pci_resource_flags(pci_dev, bar) & (IORESOURCE_MEM|IORESOURCE_IO));
    if ( type != expected_type ) {
            ct2_error(dev,
                      "expected I/O resource type 0x%08x for BAR #%u, got 0x%08x",
                      expected_type, bar, type                                    );
        return false;
    }

    // [include/linux/pci.h:pci_resource_len()]
    len = pci_resource_len(pci_dev, bar);
    if ( len < minimum_len ) {
        ct2_error(dev,
                  "expected minimal extent %zu for BAR #%u, got %u",
                  minimum_len, bar, len                             );
        return false;
    }

    ct2_notice(dev,
               "value 0x%08llx in BAR #%u nominates a%s region of %u bytes",
               pci_resource_start(pci_dev, bar), bar,
               (type == IORESOURCE_MEM ? " memory" :
                (type == IORESOURCE_IO ? "n I/O" : "n unknown")), len       );

    ct2_mtrace_exit(dev);

    return true;
}

static
void reset_device( struct ct2 * dev )
{
    // That's the best we can do.
    ct2_reg_t   buf[CT2_NREGS_CONF_CMPT];


    ct2_mtrace_enter(dev);

    // 1.
    ct2_regs_clearv(dev, 1, source_it);

    // 2.
    ct2_regs_clear(dev, 1, niveau_out);

    // 3.
#define sel_filtre_input_ch_reset   (CT2_FILTRE_INPUT_FILT_MODE_SYNC << CT2_FILTRE_INPUT_FILT_MODE_OFF)
#define sel_filtre_input______1     sel_filtre_input_ch_reset
#define sel_filtre_input_____21     ((sel_filtre_input______1 << CT2_FILTRE_INPUT_ONECHAN_WIDTH) | sel_filtre_input_ch_reset)
#define sel_filtre_input____321     ((sel_filtre_input_____21 << CT2_FILTRE_INPUT_ONECHAN_WIDTH) | sel_filtre_input_ch_reset)
#define sel_filtre_input___4321     ((sel_filtre_input____321 << CT2_FILTRE_INPUT_ONECHAN_WIDTH) | sel_filtre_input_ch_reset)
#define sel_filtre_input__54321     ((sel_filtre_input___4321 << CT2_FILTRE_INPUT_ONECHAN_WIDTH) | sel_filtre_input_ch_reset)
#define sel_filtre_input_654321     ((sel_filtre_input__54321 << CT2_FILTRE_INPUT_ONECHAN_WIDTH) | sel_filtre_input_ch_reset)
    buf[0] = sel_filtre_input_654321;
    if ( dev->pci_dev->device == PCI_DEVICE_ID_ESRF_C208 ) {

        // 3.a.
        ct2_regs_write(dev, 1, adapt_50, C208_ADAPT_50_UMSK);

        // 3.b.
        buf[1] = sel_filtre_input_654321;
        ct2_regs_writev(dev, 2, sel_filtre_input, buf);

        // 4.a.
        ct2_regs_clearv(dev, 2, c208_sel_filtre_output);

        // 4.b.
        ct2_regs_vtile(dev, 2, c208_sel_source_output, buf, C208_SOURCE_OUTPUT_UMSK);

    } else {

        // 3.a.
        ct2_regs_write(dev, 1, adapt_50, P201_ADAPT_50_UMSK);

        // 3.b.
        buf[1] = sel_filtre_input___4321;
        ct2_regs_writev(dev, 2, sel_filtre_input, buf);

        // 3.c.
        ct2_regs_clear(dev, 1, p201_niveau_in);

        // 4.a.
        ct2_regs_clear(dev, 2, p201_sel_filtre_output);

        // 4.b.
        ct2_regs_write(dev, 2, p201_sel_source_output, P201_SOURCE_OUTPUT_UMSK);
    }

    // 5.
    ct2_regs_clear(dev, 1, soft_out);

    // 6.
    ct2_regs_clear(dev, 1, cmd_dma);

    // 7.
#define conf_cmpt_ch_reset          (CT2_CONF_CMPT_CLK_100_MHz << CT2_CONF_CMPT_CLK_OFF)
    ct2_regs_vtile(dev, 2, conf_cmpt, buf, conf_cmpt_ch_reset);

    // 8.
    ct2_regs_clearv(dev, 2, sel_latch);

    // 9.
    ct2_regs_clearv(dev, 2, compare_cmpt);

    // 10.
    ct2_regs_clear(dev, 1, com_gene);

    ct2_mtrace_exit(dev);

}   // reset_device()

static
int enable_device_interrupts( const struct ct2_dcc *    dcc,
                              const struct file *       file,
                              ct2_size_type             inq_len )
{
    struct ct2 *                dev = dcc->dev;
    gfp_t                       kmalloc_flags = GFP_KERNEL | __GFP_NOWARN;
    struct ct2_in_fifo_bhead *  fbh;
    int                         rv = 0;


    ct2_mtrace_enter(dev);

    if ( inq_len == 0 )
        inq_len = inq_length;

    if ( file->f_flags & O_NONBLOCK )
        kmalloc_flags |= __GFP_NORETRY;

    // Speculatively allocate the FBH.
    fbh = ct2_in_fifo_bhead_new(kmalloc_flags, inq_len);

    // (1) Device access via DCCs must be serialised across all DCCs.
    ct2_dccs_sri(dev, rv, { goto delete_then_done; }, {

        // (2)
        // Enabling the Device to generate interrupts is
        // a (potentially) state changing operation.
        if ( !ct2_dcc_may_change_dev_state(dev, dcc) ) {
            rv = -EACCES;
            goto ct2_dccs_sri_end;
        }

        // (3)
        // Do we already have the Device generate interrupts?
        if ( dev->init_status == DEV_INIT_REQ_INTR ) {
            if ( ct2_inm_fifo_capacity(dev) != inq_len )
                rv = -EBUSY;
            goto ct2_dccs_sri_end;
        }

        // (4)
        if ( fbh == NULL ) {

            ct2_fail(dev, "ct2_in_fifo_bhead_new(flags=0x%x) = NULL", kmalloc_flags);

            if ( file->f_flags & O_NONBLOCK )
                // XXX: Really ???
                rv = -EAGAIN;
            else
                rv = -ENOMEM;

            goto ct2_dccs_sri_end;
        }

        ct2_inm_fifo_init(dev, fbh);
        fbh = NULL;

        // ===== DEV_INIT_REQ_INTR =====

        if ( (rv = ct2_enable_interrupts(dev, process_device_interrupts)) != 0 ) {

            ct2_warn(dev, "ct2_enable_interrupts() = %d", rv);

            // (5)
            ct2_inm_fifo_reset(dev);

            goto ct2_dccs_sri_end;
        }

        // (6)
        dev->init_status = DEV_INIT_REQ_INTR;

        // Let all DCCs know we can receive interrupts now.
        ct2_dccs_for_each(dev, d, {
            ct2_dcc_en_intr(d);
        });
    })

delete_then_done:

    // At this stage,  fbh  can be  NULL  or not.  If it is not,
    // we were successful in allocating the FHB's storage but flunked
    // out at either (1), (2), or (3), in which case we will have no use
    // for the FBH and can release its storage.  But if it is, it means
    // either we failed to allocate storage for the FBH in the first
    // place (4), released the storage already after failing to
    // enable Device interrupts (5), or were indeed successful
    // in enabling interrupts (6).  Either way, we release only
    // those resources that were not yet properly accounted for.
    if ( fbh != NULL )
        ct2_in_fifo_bhead_delete(fbh);

    ct2_mtrace_exit(dev);

    return rv;

}   // enable_device_interrupts()

static
int disable_device_interrupts( const struct ct2_dcc * dcc )
{
    struct ct2 *    dev = dcc->dev;
    int             rv = 0;


    ct2_mtrace_enter(dev);

    // (cf. enable_device_interrupts())
    ct2_dccs_sri(dev, rv, { goto done; }, {

        if ( !ct2_dcc_may_change_dev_state(dev, dcc) ) {
            rv = -EACCES;
            goto ct2_dccs_sri_end;
        }

        // Are interrupts already disabled for this Device?
        if ( dev->init_status != DEV_INIT_REQ_INTR )
            goto ct2_dccs_sri_end;

        ct2_disable_interrupts(dev);

        // At this particular point we can be sure that there will
        // not be any Device interrupt deliveries by the kernel in
        // flight so we are safe to release all storage associated
        // with the FIFO.
        ct2_inm_fifo_reset(dev);

        // Revert back to the last possible init state
        // that's consistent with where we're at right now.
        dev->init_status = DEV_INIT_DEV_LIST_ADD;

        // Tell all DCCs we do not receive interrupts anymore,
        // sending all (potentially) waiting DCCs a (POLL)HUP.
        ct2_dccs_for_each(dev, d, {
            ct2_dcc_dis_intr(d);
        });
    })

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // disable_device_interrupts()

static
int acknowledge_interrupt( struct ct2_dcc * dcc, struct ct2_in __user * in )
{
    struct ct2 *    dev = dcc->dev;
    int             rv = 0;


    ct2_mtrace_enter(dev);

    ct2_dccs_sri(dev, rv, { goto done; }, {

        if ( ct2_dcc_has_inq(dcc) ) {
            // XXX
            rv = -ENXIO;
            goto ct2_dccs_sri_end;
        }

        if ( copy_to_user(in, ct2_dcc_get_const_in_ref(dcc),
                              sizeof(struct ct2_in)         ) != 0 ) {
            rv = -EFAULT;
            goto ct2_dccs_sri_end;
        }

        ct2_dcc_mark_in_as_read(dcc);
    })

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // acknowledge_interrupt()

static
int attach_inq( struct ct2_dcc * dcc, ct2_size_type q_len )
{
    // XXX
    return -ENOSYS;
}

static
void detach_inq( struct ct2_dcc * dcc )
{
}

static
int drain_inq( struct ct2_dcc *         dcc,
               const struct file *      file,
               struct ct2_inv __user *  inv   )
{
    // XXX
    return -ENOSYS;
}

static
int flush_inq( struct ct2_dcc * dcc, struct timespec __user * ts )
{
    // XXX
    return -ENOSYS;
}

static
int grant_exclusive_access( struct ct2_dcc * dcc )
{
    struct ct2 *    dev = dcc->dev;
    int             rv = 0;


    ct2_mtrace_enter(dev);

    // Exclusive Device access management must be serialised across all DCCs.
    ct2_dccs_sri(dev, rv, { goto done; }, {

        if ( !ct2_dcc_may_change_dev_state(dev, dcc) ) {
            rv = -EACCES;
            goto ct2_dccs_sri_end;
        }

        // Us being able to reach this point implies two things:
        // (1) there was no exclusive Device access granted before,
        //     in which case we can go ahead with it, or
        // (2) there is exclusive Device access granted currently,
        //     and we are the one whom it was granted to, in which
        //     case we are naturally entitled to re-grant it to
        //     ourselves.
        ct2_grant_xaccess(dev, dcc);
    })

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // grant_exclusive_access()

static
int revoke_exclusive_access( struct ct2_dcc * dcc )
{
    struct ct2 *    dev = dcc->dev;
    int             rv = 0;


    ct2_mtrace_enter(dev);

    // (cf. grant_exclusive_access())
    ct2_dccs_sri(dev, rv, { goto done; }, {

        // (1)
        if ( ct2_observes_xaccess(dev) ) {

            // (2)
            if ( !ct2_dcc_has_xaccess(dev, dcc) ) {
                rv = -EACCES;
                goto ct2_dccs_sri_end;
            }

            // (3)
            if ( ct2_is_mmapped(dev) ) {
                rv = -EBUSY;
                goto ct2_dccs_sri_end;
            }

            // Us being able to get that far implies that
            // (1) there is exclusive Device access granted currently,
            // (2) we are the one whom it was granted to, and
            // (3) the FIFO is not currently mmap(2)'ed, in which
            // case we are naturally entitled to give the
            // Device up again.
            ct2_revoke_xaccess(dev);
        }
    })

done:

    ct2_mtrace_exit(dev);

    return rv;

}   // revoke_exclusive_access()


/*--------------------------------------------------------------------------*
 * FPGA array                                                               *
 *--------------------------------------------------------------------------*/
/*
 * Include these files of which one contains array:
 * static char c208bit[]={...};
 * and the other one:
 * static char p201bit[]={...};
 * used/needed in FPGA load.
 *
 * N.B. Must include both since do not know whether have:
 *      - C208 card(s) only
 *      - P201 card(s) only
 *      - mixture of both 
 */

#include "c208_bit.c"
#include "p201_bit.c"

/**
 * CubReset - reset CUB
 * @amcc_base_addr: base address of AMCC operation registers (= badr[CT2_PCI_BAR_AMCC].u)
 *
 * Reset CUB before FPGA/Virtex loading
 */

static
void CubReset( u32 amcc_base_addr )
{
	u32    mcsr;
	u32    mcsr_address; /* address of AMCC MCSR */


    mcsr_address = amcc_base_addr + AMCC_OP_REG_MCSR;

	mcsr = inl(mcsr_address);
	/* Enable Add-On pin Reset out of AMCC & Reset both Fifos PCI<->Add-on*/
	mcsr |= 0x07000000; /* set bits 26,25,24 only */
	outl(mcsr,mcsr_address);

	mcsr = inl(mcsr_address);
	/* Disable Add-On pin Reset out of AMCC */
	mcsr &= 0xfeffffff; /* clr bit 24 only */
	outl(mcsr,mcsr_address);

	/* 
	 * Add short wait of 100 msec like in C111 soft although here
	 * Virtex Loading is split in 2 functions:
	 * CubReset(), load_fpga_bitstream() and some delay is introduced 
	 * automatically when leave CubReset() and before enter in
	 * load_fpga_bitstream() function.
	 */
        mdelay(100); /* 100 msec. */

}   // CubReset()

/**
 * load_fpga_bitstream - load FPGA/Virtex
 *
 * Load the CUB FPGA/Virtex.
 *
 * Return 0 when OK or appropriate error when not OK.
 */

static
int load_fpga_bitstream( const struct ct2 * dev )
{
    u32             amcc_base_addr = pci_resource_start(dev->pci_dev, CT2_PCI_BAR_AMCC);
    unsigned short  pci_device_id = dev->pci_dev->device;
	u32             mcsr;
	u32             mcsr_address;   // address of AMCC MCSR
	u32             load_address;   // Virtex load address
	int             i, nb_toload;
	u32             longval;


    ct2_mtrace_enter(dev);

    mcsr_address = amcc_base_addr + AMCC_OP_REG_MCSR;
    load_address = amcc_base_addr + AMCC_OP_REG_FIFO;

    CubReset(amcc_base_addr);

	/* 
	 * Load the contents of the array c208bit[] or p201bit[] into Virtex.
	 * 
	 * First 4 bytes are dummy           word (0xffffffff).
	 * Next  4 bytes are synchronization word (0xaa995566).
	 * Then is all the rest.
	 *
	 * No need to check if the c208bit[] or p201bit[] array is OK since
	 * this was done in bit2array.c program.
	 */

	/* items/bytes to load = length of c208bit[] or p201bit[] array */
    if ( pci_device_id == PCI_DEVICE_ID_ESRF_C208 ) {
		/* C208 */
		nb_toload = sizeof(c208bit)/sizeof(uint8_t);
        ct2_notice(dev, "Nb of bytes to load = %d", nb_toload);
		for (i = 0; i < nb_toload; i++) {
			//udelay(100);
			mcsr = inl(mcsr_address);
			if (mcsr & 0x1) {
                ct2_fail(dev, "PCI to Add-On FIFO full on writing at index = %d", i);
				return -ENOBUFS;
			}
			longval = ((u32)(c208bit[i])) & 0x000000ff;
			outl(longval, load_address);
		}
	} else {
		/* P201 */
		nb_toload = sizeof(p201bit)/sizeof(uint8_t);
        ct2_notice(dev, "Nb of bytes to load = %d", nb_toload);
		for (i = 0; i < nb_toload; i++) {
			//udelay(100);
			mcsr = inl(mcsr_address);
			if (mcsr & 0x1) {
                ct2_fail(dev, "PCI to Add-On FIFO full on writing at index = %d", i);
				return -ENOBUFS;
			}
			longval = ((u32)(p201bit[i])) & 0x000000ff;
			outl(longval, load_address);
		}
	}

	/* Post-loading operations: */
	mcsr = inl(mcsr_address);
	/* Reset both Fifos PCI<->Add-on */
	mcsr |= 0x06000000; /* set bits 26 and 25 only */
	outl(mcsr,mcsr_address);

    ct2_mtrace_exit(dev);

    return 0;

}   // load_fpga_bitstream()

/**
 * check_cub - check the CUB general status bits
 * @dev:    ptr to CT device structure struct ct2
 *
 * Check the CUB general status reg bits and return an error
 * if something of the following is not correct:
 * 	- 6 low voltages:3.3V,2.5V,1.8V,5V,+12V,-12V(1=OK)
 *      - PhaseLockLoop status(1=OK)
 *      - Virtex Temp. alarm or overtemperature:
 *        Alarm        is when Virtex T > 126 deg. C
 *        Over Temp.   is when Virtex T > 99 deg. C
 *        N.B. This function is called only for C208 card, since all
 *             these information does not exist for P201.
 *
 * Return 0 when OK or appropriate error when not OK.
 */

static
int check_cub( const struct ct2 * dev )
{
    int ret = -EPERM;
	u32	ctrl_gene, temps;
	u32	card_sn;
	u32	virtext = (u32)0;  /* - || - */
	u32	lvregt = (u32)0;   /* - || - */  
	u32	mezz_sn = (u32)0;  /* - || - */


    ct2_mtrace_enter(dev);

    ctrl_gene = ct2_regs_read(dev, 1, ctrl_gene);

    if ( dev->pci_dev->device == PCI_DEVICE_ID_ESRF_C208 ) {

        temps = ct2_regs_read(dev, 1, c208_temps);

	       /*
	 	* Check all bits
  	 	*/
		if(!(ctrl_gene & C208_CTRL_GENE_3_3V_STA)) {
            ct2_fail(dev, "CUB VCC 3.3V not ok");
			return(ret);
		}
        ct2_notice(dev, "CUB VCC 3.3V            : ok");

		if(!(ctrl_gene & C208_CTRL_GENE_2_5V_STA)) {
            ct2_fail(dev, "CUB VCC 2.5V not ok");
			return(ret);
		}
        ct2_notice(dev, "CUB VCC 2.5V            : ok");

		if(!(ctrl_gene & C208_CTRL_GENE_1_8V_STA)) {
            ct2_fail(dev, "CUB VCC 1.8V not ok");
			return(ret);
		}
        ct2_notice(dev, "CUB VCC 1.8V            : ok");

		if(!(ctrl_gene & C208_CTRL_GENE_5V_STA)) {
            ct2_fail(dev, "CUB VCC 5V not ok");
			return(ret);
		}
        ct2_notice(dev, "CUB VCC 5V            : ok");

		if(!(ctrl_gene & C208_CTRL_GENE_P12V_STA)) {
            ct2_fail(dev, "CUB VCC P12V not ok");
			return(ret);
		}
        ct2_notice(dev, "CUB VCC P12V          : ok");

		if(!(ctrl_gene & C208_CTRL_GENE_PLL_OK)) {
            ct2_fail(dev, "CUB external PLL lock not ok");
			return(ret);
		}
        ct2_notice(dev, "CUB external PLL lock  : ok");

		if(ctrl_gene & C208_CTRL_GENE_TEMP_ALERT) {
            ct2_fail(dev, "CUB temperature alarm (Virtex T > 126 deg. C)");
			return(ret);
		}
        ct2_notice(dev, "CUB temperature alarm  : ok");

		if(ctrl_gene & C208_CTRL_GENE_TEMP_OVERT) {
            ct2_fail(dev, "CUB overtemperature (Virtex T > 99 deg. C)");
			return(ret);
		}
        ct2_notice(dev, "CUB overtemperature  : ok");

		/* Get Virtex temperature */
		virtext = temps & C208_TEMPS_VIRTEX_TEMP_MSK; /* offset = 0 */
        ct2_notice(dev, "Virtex T (deg.C) = %d",virtext);

		/* Get Low Voltage Regulator Temprature */
		lvregt = (temps & C208_TEMPS_VREG_TEMP_MSK)>>C208_TEMPS_VREG_TEMP_OFF;
        ct2_notice(dev, "Low V reg T (deg.C) = %d",lvregt);

		/* Get CUB serial number */
		card_sn = (ctrl_gene & CT2_CTRL_GENE_CARDN_MSK)>>CT2_CTRL_GENE_CARDN_OFF;
        ct2_notice(dev, "CUB card serial number    : 0x%02x",card_sn);

		/* Get C208 mezzanine serial number */
		mezz_sn = (ctrl_gene & C208_CTRL_GENE_MEZZN_MSK)>>C208_CTRL_GENE_MEZZN_OFF;
        ct2_notice(dev, "C208 mezzanine serial number : 0x%02x",mezz_sn);

    } else {    // PCI_DEVICE_ID_ESRF_P201

        // Get CUB serial number
        card_sn = (ctrl_gene & CT2_CTRL_GENE_CARDN_MSK)>>CT2_CTRL_GENE_CARDN_OFF;
        ct2_notice(dev, "CUB card serial number    : 0x%02x",card_sn); 
	}

    ct2_mtrace_exit(dev);

    return 0;

}   // check_cub()


/*--------------------------------------------------------------------------*
 *                         Driver Attribute Methods                         *
 *--------------------------------------------------------------------------*/

static
ssize_t ct2_drv_revision_show( struct device_driver * drv, char * buf )
{
    ssize_t len = 0;


    ct2_mtrace0_enter;

    len = sprintf(buf, "%s", drv_revision);

    ct2_mtrace0_exit;

	return len;
}

static
ssize_t ct2_drv_status_show( struct device_driver * drv, char * buf )
{
    ssize_t len = 0;


    ct2_mtrace0_enter;

    len = sprintf(buf, "%u", mod_init_status);

    ct2_mtrace0_exit;

    return len;
}
