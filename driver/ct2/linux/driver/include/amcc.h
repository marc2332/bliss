/*+*******************************************************************
File:        amcc.h
$Header: /segfs/bliss/cvs/driver/ESRF/ct2/include/amcc.h,v 2.7 2012/07/06 10:27:39 perez Exp $
Project:     Any ESRF Device Driver using ESRF-CUB based devices

Description: Definitions for AMCC PCI Library 

Author(s):   Phillipe Chappelet

$Revision: 2.7 $  

$Log: amcc.h,v $
Revision 2.7  2012/07/06 10:27:39  perez
Port to esrflinux1-4

Revision 2.2  2010/10/20 10:35:17  ahoms
* Renamed ctXXX source files to ct2XXX

Revision 2.1  2010/10/20 09:51:55  ahoms
* First adaptation to BLISS driver structure
* First implementation of the new Hook structure:
  + Added counter argument to library ct_hookInstall/Release (ct_hooksetup)
  + Full introduction of Hook structures: dev + cnt_chan + latch_chan + event
  + Verify that hook event does not remain active at device close
* Removed obsolete C++ counter scheme error codes
* Transferred bit_manip.h and amcc.h from /segfs/linux/drivers/common
* Added __attribute__((unused)) to static look-up tables in ct2.h
  

Copyright (c) 2000 by European Synchrotron Radiation Facility,
                      Grenoble, France

********************************************************************-*/

#ifndef _AMCC_H
#define _AMCC_H


#ifdef __cplusplus
extern "C"
{
#endif


#define CARRY_FLAG 0x01         /* 80x86 Flags Register Carry Flag bit */

/******************************************************************************/
/*   PCI Functions    **                                                      */
/******************************************************************************/

#define PCI_FUNCTION_ID           0xb1
#define PCI_BIOS_PRESENT          0x01
#define FIND_PCI_DEVICE           0x02
#define FIND_PCI_CLASS_CODE       0x03
#define GENERATE_SPECIAL_CYCLE    0x06
#define READ_CONFIG_BYTE          0x08
#define READ_CONFIG_WORD          0x09
#define READ_CONFIG_DWORD         0x0a
#define WRITE_CONFIG_BYTE         0x0b
#define WRITE_CONFIG_WORD         0x0c
#define WRITE_CONFIG_DWORD        0x0d

/******************************************************************************/
/*   PCI Return Code List                                                     */
/******************************************************************************/

#define SUCCESSFUL               0x00
#define NOT_SUCCESSFUL           0x01
#define FUNC_NOT_SUPPORTED       0x81
#define BAD_VENDOR_ID            0x83
#define DEVICE_NOT_FOUND         0x86
#define BAD_REGISTER_NUMBER      0x87

/******************************************************************************/
/*   PCI Configuration Space Registers     **                                 */
/******************************************************************************/

#define PCI_CS_VENDOR_ID         0x00
#define PCI_CS_DEVICE_ID         0x02
#define PCI_CS_COMMAND           0x04
#define PCI_CS_STATUS            0x06
#define PCI_CS_REVISION_ID       0x08
#define PCI_CS_CLASS_CODE        0x09
#define PCI_CS_CACHE_LINE_SIZE   0x0c
#define PCI_CS_MASTER_LATENCY    0x0d
#define PCI_CS_HEADER_TYPE       0x0e
#define PCI_CS_BIST              0x0f
#define PCI_CS_BASE_ADDRESS_0    0x10
#define PCI_CS_BASE_ADDRESS_1    0x14
#define PCI_CS_BASE_ADDRESS_2    0x18
#define PCI_CS_BASE_ADDRESS_3    0x1c
#define PCI_CS_BASE_ADDRESS_4    0x20
#define PCI_CS_BASE_ADDRESS_5    0x24
#define PCI_CS_EXPANSION_ROM     0x30
#define PCI_CS_INTERRUPT_LINE    0x3c
#define PCI_CS_INTERRUPT_PIN     0x3d
#define PCI_CS_MIN_GNT           0x3e
#define PCI_CS_MAX_LAT           0x3f

/******************************************************************************/
/*   AMCC Operation Register Offsets                                          */
/******************************************************************************/

#define BADR0   1
#define BADR1   2
#define BADR2   3
#define BADR3   4
#define BADR4   5
#define BADR5   6

/* put next set also since used by Phillipe */
#define AMCC_BADR0   1
#define AMCC_BADR1   2
#define AMCC_BADR2   3
#define AMCC_BADR3   4
#define AMCC_BADR4   5
#define AMCC_BADR5   6


#define AMCC_OP_REG_OMB1         0x00
#define AMCC_OP_REG_OMB2         0x04
#define AMCC_OP_REG_OMB3         0x08 
#define AMCC_OP_REG_OMB4         0x0c
#define AMCC_OP_REG_IMB1         0x10
#define AMCC_OP_REG_IMB2         0x14
#define AMCC_OP_REG_IMB3         0x18 
#define AMCC_OP_REG_IMB4         0x1c
#define AMCC_OP_REG_FIFO         0x20
#define AMCC_OP_REG_MWAR         0x24
#define AMCC_OP_REG_MWTC         0x28
#define AMCC_OP_REG_MRAR         0x2c
#define AMCC_OP_REG_MRTC         0x30
#define AMCC_OP_REG_MBEF         0x34
#define AMCC_OP_REG_INTCSR       0x38
#define AMCC_OP_REG_MCSR         0x3c
#define AMCC_OP_REG_MCSR_NVDATA  (AMCC_OP_REG_MCSR + 2) /* Data in byte 2 */
#define AMCC_OP_REG_MCSR_NVCMD   (AMCC_OP_REG_MCSR + 3) /* Command in byte 3 */


#ifdef __cplusplus
}
#endif


#endif /* _AMCC_H */
