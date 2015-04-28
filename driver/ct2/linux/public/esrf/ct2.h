/* -*- mode: C; coding: utf-8 -*- */

/****************************************************************************
 *                                                                          *
 * ESRF C208/P201 Userland C interface                                      *
 *                                                                          *
 * Copyright (c) 2004 by European Synchrotron Radiation Facility,           *
 *                       Grenoble, France                                   *
 * Copyright © 2013-2014 Helmholtz-Zentrum Dresden Rossendorf               *
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

#if !defined ESRF_CT2_H
#define ESRF_CT2_H


#if defined __cplusplus

#include <cstddef>      // std::size_t
#include <cstdint>      // std::uint8_t, std::uint32_t

typedef std::size_t     ct2_size_type;
typedef std::uint32_t   ct2_reg_t;
typedef std::uint8_t    ct2_reg_dist_t;

#define ct2_st4tic_c4st(type, expr)     static_cast<type>(expr)

#else   // __cplusplus

#if defined __KERNEL__
# include <linux/types.h>
#else
# include <stddef.h>    // size_t
# include <stdint.h>    // uint8_t, uint32_t
#endif

typedef size_t          ct2_size_type;
typedef uint32_t        ct2_reg_t;
typedef uint8_t         ct2_reg_dist_t;

#define ct2_st4tic_c4st(type, expr)     ((type )(expr))

#endif  // !__cplusplus


/*==========================================================================*
 *                           Register Definitions                           *
 *==========================================================================*/

// R ... read with side effects
// W ... write with side effects
// r ... read without side effects (ie, with memory semantics)
// w ... write without side effects


/*--------------------------------------------------------------------------*
 *                       PCI I/O Space 1 Registers Map                      *
 *--------------------------------------------------------------------------*/

struct ct2_r1 {

    ct2_reg_t   /* 0x00..0x03 */    com_gene;           // r W      general control
    ct2_reg_t   /* 0x04..0x07 */    ctrl_gene;          // r        general status

    union {     /* 0x08..0x0b */
        struct {
            ct2_reg_t               temps;              // r        temperature reading(s)
        } c208;
        struct {
            ct2_reg_t               _reserved;
        } p201;
    } _0x08_0x0b;

    ct2_reg_t   /* 0x0c..0x0f */    niveau_out;         // r w      output enable and type selection
    ct2_reg_t   /* 0x10..0x13 */    adapt_50;           // r w      disable 50 Ω input load
    ct2_reg_t   /* 0x14..0x17 */    soft_out;           // r w      output fixed value selection
    ct2_reg_t   /* 0x18..0x1b */    rd_in_out;          // r        input sample and output readback
    ct2_reg_t   /* 0x1c..0x1f */    rd_ctrl_cmpt;       // r        counters status
    ct2_reg_t   /* 0x20..0x23 */    cmd_dma;            // r W      FIFO control
    ct2_reg_t   /* 0x24..0x27 */    ctrl_fifo_dma;      // R        FIFO status and error clear
    ct2_reg_t   /* 0x28..0x2f */    source_it[2];       // r w      interrupt source selection
    ct2_reg_t   /* 0x30..0x33 */    ctrl_it;            // R        interrupt status and clear

    union {     /* 0x34..0x37 */
        struct {
            ct2_reg_t               _reserved;
        } c208;
        struct {
            ct2_reg_t               niveau_in;          // r w      input level selection
        } p201;
    } _0x34_0x37;

    struct {    /* 0x38..0x3f */
        ct2_reg_t                   _reserved[2];
    } _0x38_0x3f;

    ct2_reg_t   /* 0x40..0x6f */    rd_cmpt[12];        // r        counter value sample
    ct2_reg_t   /* 0x70..0x9f */    rd_latch_cmpt[12];  // r        counter latch value readout

    struct {    /* 0xa0..0xfb */
        ct2_reg_t                   _reserved[23];
    } _0xa0_0xfb;

    union {     /* 0xfc..0xff */
        struct {
            ct2_reg_t               _reserved;
        } c208;
        struct {
            ct2_reg_t               test_reg;           // R w      test data register
        } p201;
    } _0xfc_0xff;
};

#define ct2_com_gene                com_gene
#define ct2_ctrl_gene               ctrl_gene
#define ct2_niveau_out              niveau_out
#define ct2_adapt_50                adapt_50
#define ct2_soft_out                soft_out
#define ct2_rd_in_out               rd_in_out
#define ct2_rd_ctrl_cmpt            rd_ctrl_cmpt
#define ct2_cmd_dma                 cmd_dma
#define ct2_ctrl_fifo_dma           ctrl_fifo_dma
#define ct2_source_it               source_it
#define ct2_ctrl_it                 ctrl_it
#define ct2_rd_cmpt                 rd_cmpt
#define ct2_rd_latch_cmpt           rd_latch_cmpt

#define c208_com_gene               ct2_com_gene
#define c208_ctrl_gene              ct2_ctrl_gene
#define c208_temps                  _0x08_0x0b.c208.temps
#define c208_niveau_out             ct2_niveau_out
#define c208_adapt_50               ct2_adapt_50
#define c208_soft_out               ct2_soft_out
#define c208_rd_in_out              ct2_rd_in_out
#define c208_rd_ctrl_cmpt           ct2_rd_ctrl_cmpt
#define c208_cmd_dma                ct2_cmd_dma
#define c208_ctrl_fifo_dma          ct2_ctrl_fifo_dma
#define c208_source_it              ct2_source_it
#define c208_ctrl_it                ct2_ctrl_it
#define c208_rd_cmpt                ct2_rd_cmpt
#define c208_rd_latch_cmpt          ct2_rd_latch_cmpt

#define p201_com_gene               ct2_com_gene
#define p201_ctrl_gene              ct2_ctrl_gene
#define p201_niveau_out             ct2_niveau_out
#define p201_adapt_50               ct2_adapt_50
#define p201_soft_out               ct2_soft_out
#define p201_rd_in_out              ct2_rd_in_out
#define p201_rd_ctrl_cmpt           ct2_rd_ctrl_cmpt
#define p201_cmd_dma                ct2_cmd_dma
#define p201_ctrl_fifo_dma          ct2_ctrl_fifo_dma
#define p201_source_it              ct2_source_it
#define p201_ctrl_it                ct2_ctrl_it
#define p201_niveau_in              _0x34_0x37.p201.niveau_in
#define p201_rd_cmpt                ct2_rd_cmpt
#define p201_rd_latch_cmpt          ct2_rd_latch_cmpt
#define p201_test_reg               _0xfc_0xff.p201.test_reg


/*--------------------------------------------------------------------------*
 *                       PCI I/O Space 2 Registers Map                      *
 *--------------------------------------------------------------------------*/

struct ct2_r2 {

    ct2_reg_t   /* 0x00..0x07 */    sel_filtre_input[2];    // r w      input filter selection

    union {     /* 0x08..0x13 */                            // r w      output filter selection
        struct {
            ct2_reg_t               sel_filtre_output[3];
        } c208;
        struct {
            ct2_reg_t               _reserved[2];
            ct2_reg_t               sel_filtre_output;
        } p201;
    } _0x08_0x13;

    union {     /* 0x14..0x1f */                            // r w      output source selection
        struct {
            ct2_reg_t               sel_source_output[3];
        } c208;
        struct {
            ct2_reg_t               _reserved[2];
            ct2_reg_t               sel_source_output;
        } p201;
    } _0x14_0x1f;

    ct2_reg_t   /* 0x20..0x37 */    sel_latch[6];           // r w      counter latch source selection
    ct2_reg_t   /* 0x38..0x67 */    conf_cmpt[12];          // r w      counter configuration
    ct2_reg_t   /* 0x68..0x6b */    soft_enable_disable;    //   W      counters enable and disable
    ct2_reg_t   /* 0x6c..0x6f */    soft_start_stop;        //   W      counters programmed start and stop
    ct2_reg_t   /* 0x70..0x73 */    soft_latch;             //   W      counters value programmed latch
    ct2_reg_t   /* 0x74..0xa3 */    compare_cmpt[12];       // r W      comparator latch value

    struct {    /* 0xa4..0xff */
        ct2_reg_t                   _reserved[23];
    } _0xa4_0xff;
};

#define ct2_sel_filtre_input        sel_filtre_input
#define ct2_sel_latch               sel_latch
#define ct2_conf_cmpt               conf_cmpt
#define ct2_soft_enable_disable     soft_enable_disable
#define ct2_soft_start_stop         soft_start_stop
#define ct2_soft_latch              soft_latch
#define ct2_compare_cmpt            compare_cmpt

#define c208_sel_filtre_input       ct2_sel_filtre_input
#define c208_sel_filtre_output      _0x08_0x13.c208.sel_filtre_output
#define c208_sel_source_output      _0x14_0x1f.c208.sel_source_output
#define c208_sel_latch              ct2_sel_latch
#define c208_conf_cmpt              ct2_conf_cmpt
#define c208_soft_enable_disable    ct2_soft_enable_disable
#define c208_soft_start_stop        ct2_soft_start_stop
#define c208_soft_latch             ct2_soft_latch
#define c208_compare_cmpt           ct2_compare_cmpt

#define p201_sel_filtre_input       ct2_sel_filtre_input
#define p201_sel_filtre_output      _0x08_0x13.p201.sel_filtre_output
#define p201_sel_source_output      _0x14_0x1f.p201.sel_source_output
#define p201_sel_latch              ct2_sel_latch
#define p201_conf_cmpt              ct2_conf_cmpt
#define p201_soft_enable_disable    ct2_soft_enable_disable
#define p201_soft_start_stop        ct2_soft_start_stop
#define p201_soft_latch             ct2_soft_latch
#define p201_compare_cmpt           ct2_compare_cmpt


/**
 * ct2_+ - register file size and offset
 * @spc:    { 1, 2 }
 * @reg:    identifier naming a member in the respective struct ct2_r@spc
 * @lower:  identifier naming a member in the respective struct ct2_r@spc
 * @upper:  identifier naming a member in the respective struct ct2_r@spc
 */

#define ct2_sizeof_spc(spc)                         (sizeof(struct ct2_r ## spc))
#define ct2_spc_size(spc)                           (ct2_st4tic_c4st(ct2_reg_dist_t, ct2_sizeof_spc(spc)/sizeof(ct2_reg_t)))

#define ct2_sizeof_reg(spc, reg)                    (sizeof(((struct ct2_r ## spc * )(0))->reg))
#define ct2_reg_size(spc, reg)                      (ct2_st4tic_c4st(ct2_reg_dist_t, ct2_sizeof_reg(spc, reg)/sizeof(ct2_reg_t)))

#define ct2_offsetof_reg(spc, reg)                  (offsetof(struct ct2_r ## spc, reg))
#define ct2_reg_offset(spc, reg)                    (ct2_st4tic_c4st(ct2_reg_dist_t, ct2_offsetof_reg(spc, reg)/sizeof(ct2_reg_t)))
#define ct2_sizeof_reg_interval(spc, lower, upper)  ((ct2_offsetof_reg(spc, upper) - ct2_offsetof_reg(spc, lower)) + ct2_sizeof_reg(spc, upper))
#define ct2_reg_interval_size(spc, lower, upper)    (ct2_st4tic_c4st(ct2_reg_dist_t, ct2_sizeof_reg_interval(spc, lower, upper)/sizeof(ct2_reg_t)))



/*============================================================================*
 *                  BIT FIELDS, MASKS, OFFSETS, MACROS DEFINITIONS            *
 *                                                                            *
 * N.B. Masks/offsets that are valid for both C208 and P201 start with CT2_,  *
 *      C208 specific start with C208_, P201 specif.start with P201_          *
 *============================================================================*/

/*----------------------------------------------------------------------------*
 * Definitions for "low" 12 bits (0-11) and "high" 12 (16-27) bits masks      *
 *             used to mask useful bits in several registers.                 *
 *             Since cards have 12 counters and on C208 also 12 channels, the *
 *             usefull register part is either "low" or "high" 12 bits.       *
 *             For P201 which has only 10 channels, provide also masks for    *
 *             "low" 10 bits (0-9) and "high" 12 (16-25) bits.                *
 *----------------------------------------------------------------------------*/
#define CT2_LO12BITS_MSK           0x00000fff /* Mask for bits 0-11            */
#define CT2_LO12BITS_OFF           0          /* Offset for the low word       */
#define CT2_HI12BITS_MSK           0x0fff0000 /* Mask for bits 16-27           */
#define CT2_HI12BITS_OFF           16         /* Offset for the high word      */
#define CT2_LO10BITS_MSK           0x000003ff /* Mask for bits 0-9             */
#define CT2_LO10BITS_OFF           0          /* Offset for the low word       */
#define CT2_HI10BITS_MSK           0x03ff0000 /* Mask for bits 16-25           */
#define CT2_HI10BITS_OFF           16         /* Offset for the high word      */


/*--------------------------------------------------------------------------*
 *                         PCI I/O Space 1 Registers                        *
 *--------------------------------------------------------------------------*/

/*----------------------------------------------------------------------------*
 * Definitions for the COM_GENE (general command) register(R/W)               *
 *----------------------------------------------------------------------------*/
#define CT2_COM_GENE_UMSK          0x0000009f /* Used bits mask                */
#define CT2_COM_GENE_ENAB_OSC      0x00000010 /* en(1)/dis(0)able oscillator   */
#define CT2_COM_GENE_SOFT_RESET    0x00000080 /* soft reset(1)                 */
#define CT2_COM_GENE_FREQ_MSK      0x0000000f /* Frequency bitmask             */
#define CT2_COM_GENE_FREQ_OFF      0          /* Frequency offset              */

#define ct2_clock_freq_ctor(a, b, c, d, e)  (((a) << 4)|((b) << 3)|((c) << 2)|((d) << 1)|((e) << 0))

#define CT2_COM_GENE_CLOCK_DISABLED         ct2_clock_freq_ctor(0,  0, 0, 0, 0)

#define CT2_COM_GENE_CLOCK_AT_20_MHz        ct2_clock_freq_ctor(1,  0, 1, 0, 1)
#define CT2_COM_GENE_CLOCK_AT_25_MHz        ct2_clock_freq_ctor(1,  0, 1, 0, 0)
#define CT2_COM_GENE_CLOCK_AT_30_MHz        ct2_clock_freq_ctor(1,  0, 0, 1, 0)
#define CT2_COM_GENE_CLOCK_AT_33_33_MHz     ct2_clock_freq_ctor(1,  0, 0, 0, 1)
#define CT2_COM_GENE_CLOCK_AT_40_MHz        ct2_clock_freq_ctor(1,  1, 1, 1, 1)
#define CT2_COM_GENE_CLOCK_AT_45_MHz        ct2_clock_freq_ctor(1,  1, 1, 0, 1)
#define CT2_COM_GENE_CLOCK_AT_50_MHz        ct2_clock_freq_ctor(1,  1, 1, 0, 0)
#define CT2_COM_GENE_CLOCK_AT_60_MHz        ct2_clock_freq_ctor(1,  1, 0, 1, 0)
#define CT2_COM_GENE_CLOCK_AT_66_66_MHz     ct2_clock_freq_ctor(1,  1, 0, 0, 1)
#define CT2_COM_GENE_CLOCK_AT_70_MHz        ct2_clock_freq_ctor(1,  0, 1, 1, 0)
#define CT2_COM_GENE_CLOCK_AT_75_MHz        ct2_clock_freq_ctor(1,  1, 0, 0, 0)
#define CT2_COM_GENE_CLOCK_AT_80_MHz        ct2_clock_freq_ctor(1,  0, 1, 1, 1)
#define CT2_COM_GENE_CLOCK_AT_90_MHz        ct2_clock_freq_ctor(1,  1, 1, 1, 0)
#define CT2_COM_GENE_CLOCK_AT_100_MHz       ct2_clock_freq_ctor(1,  0, 0, 0, 0)

/*----------------------------------------------------------------------------*
 * Definitions for the CTRL_GENE (general control) register(R)                *
 *----------------------------------------------------------------------------*/
#define C208_CTRL_GENE_UMSK       0xfcffff7f /* Used bits mask                */
#define P201_CTRL_GENE_UMSK       0x0000ff0f /* Used bits mask                */
#define CT2_CTRL_GENE_FIFO_MSK     0x0000000f /* AMCC fifo flags mask          */
#define CT2_CTRL_GENE_FIFO_OFF	  0          /* AMCC fifo flags offset        */
#define C208_CTRL_GENE_PLL_OK     0x00000010 /* external PLL synchronised     */
#define C208_CTRL_GENE_TEMP_ALERT 0x00000020 /* Virtex T > 126 degrees        */
#define C208_CTRL_GENE_TEMP_OVERT 0x00000040 /* Virtex T >  99 degrees        */
#define CT2_CTRL_GENE_CARDN_MSK    0x0000ff00 /* card(C208 or P201) ser.nb mask*/
#define CT2_CTRL_GENE_CARDN_OFF    8          /* card serial number offset     */
#define C208_CTRL_GENE_MEZZN_MSK  0x00ff0000 /* C208 mezzanine serial nb msk  */
#define C208_CTRL_GENE_MEZZN_OFF  16         /* C208 mezz. serial nb offset   */
#define C208_CTRL_GENE_3_3V_STA   0x04000000 /* status of 3.3V (1 = OK)       */
#define C208_CTRL_GENE_2_5V_STA   0x08000000 /* status of 2.5V (1 = OK)       */
#define C208_CTRL_GENE_1_8V_STA   0x10000000 /* status of 1.8V (1 = OK)       */
#define C208_CTRL_GENE_5V_STA     0x20000000 /* status of   5V (1 = OK)       */
#define C208_CTRL_GENE_P12V_STA   0x40000000 /* status of +12V (1 = OK)       */
#define C208_CTRL_GENE_M12V_STA   0x80000000 /* status of -12V (1 = OK)       */
#define C208_CTRL_GENE_LV_MSK     0xfc000000 /* LV status msk(all LVstogether)*/
#define C208_CTRL_GENE_LV_OFF     26         /* offset for LV status          */

#define C208_VOLTS_OK(genctrl) ((BIT_TST(genctrl, C208_CTRL_GENE_3_3V_STA)) && \
                       (BIT_TST(genctrl, C208_CTRL_GENE_2_5V_STA)) && \
                       (BIT_TST(genctrl, C208_CTRL_GENE_1_8V_STA)) && \
                       (BIT_TST(genctrl, C208_CTRL_GENE_5V_STA)) && \
                       (BIT_TST(genctrl, C208_CTRL_GENE_P12V_STA)) && \
                       (BIT_TST(genctrl, C208_CTRL_GENE_M12V_STA)))

/*----------------------------------------------------------------------------*
 * Definitions for TEMPS (temperature) register(R) - only exists for C208     *
 *----------------------------------------------------------------------------*/
#define C208_TEMPS_VIRTEX_TEMP_MSK 0x0000007f /* Virtex Temperature mask      */
#define C208_TEMPS_VIRTEX_TEMP_OFF 0          /* Virtex Temperature offset    */
#define C208_TEMPS_VREG_TEMP_MSK   0x00007f00 /* Voltage(2.5V,1.8V)reg. T mask*/
#define C208_TEMPS_VREG_TEMP_OFF   8          /* Voltage regulators T offset  */
#define C208_TEMPS_UMSK            0x00007f7f /* Used bits mask               */

/*----------------------------------------------------------------------------*
 * Definitions for NIVEAU_OUT (output level) register(R/W).                   *
 * Remark: Better name for this register would be CHAN_TYPE!                  *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define C208_NIVEAU_OUT_UMSK	  CT2_LO12BITS_MSK | CT2_HI12BITS_MSK 
#define P201_NIVEAU_OUT_UMSK	  0x03000300

/*----------------------------------------------------------------------------*
 * Definitions for ADAPT_50 (en/disable 50 Ohm on input) register(R/W)        *
 *----------------------------------------------------------------------------*/
#define C208_ADAPT_50_UMSK        CT2_LO12BITS_MSK  /* Used bits mask          */
#define P201_ADAPT_50_UMSK        CT2_LO10BITS_MSK  /* Used bits mask          */

/*----------------------------------------------------------------------------*
 * Definitions for SOFT_OUT (soft output = like Digital Out) register(R/W)    *
 *----------------------------------------------------------------------------*/
#define C208_SOFT_OUT_UMSK        CT2_LO12BITS_MSK  /* Used bits mask          */
#define P201_SOFT_OUT_UMSK        0x00000300       /* Used bits mask          */

/*----------------------------------------------------------------------------*
 * Definitions for RD_IN_OUT (Virtex I/O; like Digital IN) register(R)        *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define C208_RD_IN_OUT_UMSK       CT2_LO12BITS_MSK | CT2_HI12BITS_MSK  
#define P201_RD_IN_OUT_UMSK       0x03000000 | CT2_LO10BITS_MSK  
#define C208_RD_IN_OUT_INPUT_MSK  CT2_LO12BITS_MSK  /* Input  level mask       */
#define P201_RD_IN_OUT_INPUT_MSK  CT2_LO10BITS_MSK  /* Input  level mask       */
#define CT2_RD_IN_OUT_INPUT_OFF    0                /* Input  level offset     */
#define C208_RD_IN_OUT_OUTPUT_MSK CT2_HI12BITS_MSK  /* Output level mask       */
#define C208_RD_IN_OUT_OUTPUT_OFF CT2_HI12BITS_OFF  /* Output level offset     */
#define P201_RD_IN_OUT_OUTPUT_MSK 0x03000000       /* Output level mask       */
#define P201_RD_IN_OUT_OUTPUT_OFF 24               /* Output level offset     */

/*----------------------------------------------------------------------------*
 * Definitions for RD_CTRL_CMPT (counter run/enable status) register(R)       *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define CT2_RD_CTRL_CMPT_UMSK      CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
#define CT2_RD_CTRL_CMPT_ENDIS_MSK CT2_LO12BITS_MSK  /* counter soft en/disable */
#define CT2_RD_CTRL_CMPT_ENDIS_OFF CT2_LO12BITS_OFF
#define CT2_RD_CTRL_CMPT_ACQ_MSK   CT2_HI12BITS_MSK  /* counter idle/running    */
#define CT2_RD_CTRL_CMPT_ACQ_OFF   CT2_HI12BITS_OFF

/*----------------------------------------------------------------------------*
 * Definitions for CMD_DMA (dma command) register(R/W)                        *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define CT2_CMD_DMA_UMSK           CT2_LO12BITS_MSK | CT2_HI12BITS_MSK | 0x80000000
#define CT2_CMD_DMA_TRIG_MSK       CT2_LO12BITS_MSK  /* DMA trigger condition   */
#define CT2_CMD_DMA_TRIG_OFF       CT2_LO12BITS_OFF  /*     choice              */
#define CT2_CMD_DMA_TRANS_MSK      CT2_HI12BITS_MSK  /* enable DMA transfer     */
#define CT2_CMD_DMA_TRANS_OFF      CT2_HI12BITS_OFF  /*     choice              */
#define CT2_CMD_DMA_TRANSALL_BIT   31 /* 1: overall enable of DMA transf 
                                           (if this bit is not set the latches
                                            selected in bits 16-27 are not
                                            transferred).
                                        0: reset FIFOs and error memory       */

/*----------------------------------------------------------------------------*
 * Definitions for CTRL_FIFO_DMA (dma control) register(R/W)                  *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define CT2_CTRL_DMA_UMSK               CT2_LO12BITS_MSK | 0x001f0000
#define CT2_CTRL_DMA_NW_MSK             CT2_LO12BITS_MSK /*nb wrds in FIFO to rd*/
#define CT2_CTRL_DMA_NW_OFF             CT2_LO12BITS_OFF
#define CT2_CTRL_DMA_ERR_MSK            0x00070000
#define CT2_CTRL_DMA_ERR_OFF            16
#define CT2_CTRL_DMA_ERR_TRIG_LOST_BIT  16    /* 1: error one DMA trigger lost */
#define CT2_CTRL_DMA_ERR_READ_FIFO_BIT  17    /* 1: error during FIFO read     */
#define CT2_CTRL_DMA_ERR_WRITE_FIFO_BIT 18    /* 1: error during FIFO write    */
#define CT2_CTRL_DMA_FLAGS_MSK          0x00180000
#define CT2_CTRL_DMA_FLAGS_OFF          19
#define CT2_CTRL_DMA_FIFO_EMPTY_BIT     19    /* 1: FIFO empty                 */
#define CT2_CTRL_DMA_FIFO_FULL_BIT      20    /* 1: FIFO full                  */

/*----------------------------------------------------------------------------*
 * Definitions for SOURCE_IT_A  register(R/W)                                 *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define C208_SRC_IT_A_UMSK        CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
#define P201_SRC_IT_A_UMSK        CT2_LO10BITS_MSK | CT2_HI10BITS_MSK
#define C208_SRC_IT_A_RE_MSK      CT2_LO12BITS_MSK /* IT src = Raising Edge    */
#define C208_SRC_IT_A_RE_OFF      CT2_LO12BITS_OFF
#define P201_SRC_IT_A_RE_MSK      CT2_LO10BITS_MSK /* IT src = Raising Edge    */
#define P201_SRC_IT_A_RE_OFF      CT2_LO10BITS_OFF
#define C208_SRC_IT_A_FE_MSK      CT2_HI12BITS_MSK /* IT src = Falling Edge    */
#define C208_SRC_IT_A_FE_OFF      CT2_HI12BITS_OFF
#define P201_SRC_IT_A_FE_MSK      CT2_HI10BITS_MSK /* IT src = Falling Edge    */
#define P201_SRC_IT_A_FE_OFF      CT2_HI10BITS_OFF

/*----------------------------------------------------------------------------*
 * Definitions for SOURCE_IT_B  register(R/W)                                 *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define CT2_SRC_IT_B_UMSK          CT2_LO12BITS_MSK | 0x00007000
#define CT2_SRC_IT_B_END_MSK       CT2_LO12BITS_MSK  /* IT src = END of counter */
#define CT2_SRC_IT_B_END_OFF       CT2_LO12BITS_OFF
#define CT2_SRC_IT_B_ENDFILL_BIT   12 /* IT at end of 1 cycle = 1 transfer of
                                        selected latches into FIFO after DMA
                                        trigger
                                      */
#define CT2_SRC_IT_B_HALFFULL_BIT  13 /* IT at half fill FIFO after DMAtrig    */
#define CT2_SRC_IT_B_ERROR_BIT     14 /* IT due to error (see CTRL_FIFO_DMA)   */

/*----------------------------------------------------------------------------*
 * Definitions for CTRL_IT  register(R)                                       *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define C208_CTRL_IT_UMSK         0x0effffff
#define P201_CTRL_IT_UMSK         0x0efff3ff
#define C208_CTRL_IT_REFE_MSK     CT2_LO12BITS_MSK  /* IT = Rais./Fall. Edge   */
#define C208_CTRL_IT_REFE_OFF     CT2_LO12BITS_OFF
#define P201_CTRL_IT_REFE_MSK     CT2_LO10BITS_MSK  /* IT = Rais./Fall. Edge   */
#define P201_CTRL_IT_REFE_OFF     CT2_LO10BITS_OFF
#define CT2_CTRL_IT_END_MSK        0x00fff000       /* IT = END of ctn.0-11   */
#define CT2_CTRL_IT_END_OFF        12
#define CT2_CTRL_IT_ENDFILL_BIT    25 /* IT at end of 1 cycle = 1 transfer of
                                        selected latches into FIFO after DMA
                                        trigger
                                      */
#define CT2_CTRL_IT_HALFFULL_BIT   26 /* IT at half fill FIFO after DMA trig   */
#define CT2_CTRL_IT_ERROR_BIT      27 /* IT due to error (see CTRL_FIFO_DMA)   */

/*----------------------------------------------------------------------------*
 * Definitions for NIVEAU_IN register(R/W) - only exists for P201             *
 *----------------------------------------------------------------------------*/
#define P201_NIVEAU_IN_UMSK       CT2_LO10BITS_MSK | CT2_HI10BITS_MSK
#define P201_NIVEAU_IN_TTL_MSK    CT2_LO10BITS_MSK  /* TTL in level mask       */
#define P201_NIVEAU_IN_TTL_OFF    CT2_LO10BITS_OFF
#define P201_NIVEAU_IN_NIM_MSK    CT2_HI10BITS_MSK  /* NIM in level mask       */
#define P201_NIVEAU_IN_NIM_OFF    CT2_HI10BITS_OFF


/*--------------------------------------------------------------------------*
 *                         PCI I/O Space 2 Registers                        *
 *--------------------------------------------------------------------------*/

/*----------------------------------------------------------------------------*
 * Definitions for SEL_FILTRE_INPUT_A/B (input filter select) registers (R/W) *
 *----------------------------------------------------------------------------*/
#define CT2_FILTRE_INPUT_UMSK               0x3fffffff
#define CT2_FILTRE_INPUT_FREQ_FIELD_MSK     0x7  /* freq. bit field needs 3 bits  */
#define CT2_FILTRE_INPUT_ONECHAN_WIDTH      5    /* 5 bits cover input filter
                                                selection for each channel */
#define CT2_FILTRE_INPUT_FILT_MODE_OFF      3    /* offset of filter mode: */
#define CT2_FILTRE_INPUT_FILT_MODE_SSPC     0x0
#define CT2_FILTRE_INPUT_FILT_MODE_SYNC     0x1
#define CT2_FILTRE_INPUT_FILT_MODE_SYM      0x2
#define CT2_FILTRE_INPUT_FILT_MODE_ASYM     0x3
#define CT2_FILTRE_INPUT_FILT_MODE_MSK      0x3

/*----------------------------------------------------------------------------*
 * Definitions for SEL_FILTRE_OUTPUT_A/B/C (output filter select) regs (R/W)  *
 * For P201 only the last (= the 3rd) output filter reg. is used              *
 *----------------------------------------------------------------------------*/
#define C208_FILTRE_OUTPUT_UMSK         0x3fffffff  /* used bits mask         */
#define P201_FILTRE_OUTPUT_UMSK         0x00001f1f  /* used bits mask         */
#define CT2_FILTRE_OUTPUT_FREQ_FIELD_MSK 0x7  /* freq bit field needs 3 bits   */
#define CT2_FILTRE_OUTPUT_ONECHAN_WIDTH  5    /* 5 bits cover input filter
                                                selection for each channel */
#define CT2_FILTRE_OUTPUT_FILTENAB_OFF   3    /* offset of filter en/disable 
                                                bit within 5 bits
                                              */
#define CT2_FILTRE_OUTPUT_POLARITY_OFF   4    /* offset of polarity inversion 
                                                bit within 5 bits 
                                              */

/*----------------------------------------------------------------------------*
 * Definitions for SEL_SOURCE_OUTPUT_A/B/C (output source select) regs (R/W)  *
 * For P201 only the last (= the 3rd) output source reg. is used              *
 *----------------------------------------------------------------------------*/
#define C208_SOURCE_OUTPUT_UMSK         0x7f7f7f7f  /* used bits mask         */
#define P201_SOURCE_OUTPUT_UMSK         0x00007f7f  /* used bits mask         */

/*----------------------------------------------------------------------------*
 * Definitions for SEL_LATCH_A/B/C/D/E/F (latch select) registers (R/W)       *
 * ctn = [0,11] = counter number                                              *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define CT2_SEL_LATCH_UMSK	  CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
#define CT2_SEL_LATCH_MSK(ctn) ((ctn % 2)? CT2_LO12BITS_MSK : CT2_HI12BITS_MSK)
#define CT2_SEL_LATCH_OFF(ctn) ((ctn % 2)? CT2_HI12BITS_OFF : CT2_HI12BITS_OFF)

/*----------------------------------------------------------------------------*
 * Definitions for CONF_CMPT_1/12 (counter configuration) registers (R/W)     *
 *----------------------------------------------------------------------------*/
#define CT2_CONF_CMPT_UMSK          0xc7ffffff	/* Used bits mask             */
#define CT2_CONF_CMPT_CLK_MSK       0x0000007f
#define CT2_CONF_CMPT_CLK_OFF       0
#define CT2_CONF_CMPT_CLK_100_MHz   0x5
#define CT2_CONF_CMPT_GATE_MSK      0x00001f80
#define CT2_CONF_CMPT_GATE_OFF      7	
#define CT2_CONF_CMPT_HSTART_MSK    0x000fe000
#define CT2_CONF_CMPT_HSTART_OFF    13	
#define CT2_CONF_CMPT_HSTOP_MSK     0x07f00000
#define CT2_CONF_CMPT_HSTOP_OFF     20	
#define CT2_CONF_CMPT_CLEAR_BIT     30	
#define CT2_CONF_CMPT_STOP_BIT      31

/*----------------------------------------------------------------------------*
 * Definitions for SOFT_ENABLE_DISABLE register (W)                           *
 * reg = value of soft_enable_disable register, ctn = [0,11] = counter number *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define CT2_SOFT_ENABLE_DISABLE_UMSK  CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
#define CT2_SOFT_ENABLE_ALL_MSK     CT2_LO12BITS_MSK
#define CT2_SOFT_ENABLE_ALL_OFF     CT2_LO12BITS_OFF
#define CT2_SOFT_DISABLE_ALL_MSK    CT2_HI12BITS_MSK
#define CT2_SOFT_DISABLE_ALL_OFF    CT2_HI12BITS_OFF
#define CT2_SOFT_ENABLE(reg,ctn)    BIT_SETB(reg,ctn)
#define CT2_SOFT_DISABLE(reg,ctn)   BIT_SETB(reg,ctn+16)

/*----------------------------------------------------------------------------*
 * Definitions for SOFT_START_STOP register (W)                               *
 * reg = value of soft_start_stop register, crn = [0,11] = counter number     *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define CT2_SOFT_START_STOP_UMSK   CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
#define CT2_SOFT_START_ALL_MSK     CT2_LO12BITS_MSK
#define CT2_SOFT_START_ALL_OFF     CT2_LO12BITS_OFF
#define CT2_SOFT_STOP_ALL_MSK      CT2_HI12BITS_MSK
#define CT2_SOFT_STOP_ALL_OFF      CT2_HI12BITS_OFF
#define CT2_SOFT_START(reg,ctn)    BIT_SETB(reg,ctn)
#define CT2_SOFT_STOP(reg,ctn)     BIT_SETB(reg,ctn+16)

/*----------------------------------------------------------------------------*
 * Definitions for SOFT_LATCH register (W)                                    *
 * reg = value of soft_latch register, ctn = [0,11] = counter number          *
 *----------------------------------------------------------------------------*/
/* used bits mask                                                             */
#define CT2_SOFT_LATCH_UMSK         CT2_LO12BITS_MSK
#define CT2_SOFT_LATCH_ALL_MSK      CT2_LO12BITS_MSK
#define CT2_SOFT_LATCH_ALL_OFF      CT2_LO12BITS_OFF
#define CT2_SOFT_LATCH(reg,ctn)     BIT_SETB(reg,ctn)


/* XXX */

#define CT2_NREGS_SOURCE_IT                 (ct2_reg_size(1, source_it))
#define CT2_NREGS_RD_CMPT                   (ct2_reg_size(1, rd_cmpt))
#define CT2_NREGS_RD_LATCH_CMPT             (ct2_reg_size(1, rd_latch_cmpt))

#define CT2_NREGS_SEL_FILTRE_INPUT          (ct2_reg_size(2, sel_filtre_input))
#define CT2_NREGS_SEL_FILTRE_OUTPUT_C208    (ct2_reg_size(2, c208_sel_filtre_output))
#define CT2_NREGS_SEL_FILTRE_OUTPUT_P201    (ct2_reg_size(2, p201_sel_filtre_output))
#define CT2_NREGS_SEL_SOURCE_OUTPUT_C208    (ct2_reg_size(2, c208_sel_source_output))
#define CT2_NREGS_SEL_SOURCE_OUTPUT_P201    (ct2_reg_size(2, p201_sel_source_output))
#define CT2_NREGS_SEL_LATCH                 (ct2_reg_size(2, sel_latch))
#define CT2_NREGS_CONF_CMPT                 (ct2_reg_size(2, conf_cmpt))
#define CT2_NREGS_COMPARE_CMPT              (ct2_reg_size(2, compare_cmpt))



/*==========================================================================*
 *                         Kernel Device Interface                          *
 *==========================================================================*/

/**
 * Each C208/P201 instance in a Linux system, hereafter referred to simply
 * as a "Device", is manifested as a single character special file that
 * provides userland access to the PCI I/O Space 1 and 2 Registers Maps,
 * the Scaler Values FIFO of, and delivery of interrupts from the Device,
 * as well as an independent general Device Reset.  There is also a control
 * mechanism for exclusive Device access based on open file descriptions to
 * the Device.
 *
 * A Device may have any number of open file descriptions associated with
 * it through which Device operations, as defined below - in particular
 * those that result in a Device state change - may be performed.  In order
 * for userland to be granted exclusive state changing rights for a Device,
 * they must first lay explicit claim to the Device via an open file
 * description associated with the Device.
 *
 * Once granted exclusive access, only Device state changing operation
 * requests via the same open file description through which exclusive
 * access rights were actually granted will be honoured across all open
 * file descriptions associated with a Device.  Exclusivity exists as
 * long as the open file description used to obtain exclusivity exists
 * and vanishes if that open file description is going away or is
 * explicitly given up.
 *
 * A Device state changing operation in the above sense is the read from
 * a location in the Scaler Values FIFO or a readable Device register with
 * side effects, the write to a writable Device register, the management
 * of Device interrupt delivery, or the management of exclusive Device
 * accesses itself.
 */

/*--------------------------------------------------------------------------*
 *                   PCI I/O Space 1 and 2 Registers Maps                   *
 *--------------------------------------------------------------------------*/

/**
 * Access to the two Device register files is provided via any of the
 * (p)read(v)(2), (p)write(v)(2), and  lseek(2)  system calls on the open
 * file description obtained from an  open(2)  on the character special file
 * associated with the Device.  To that end, the two register files are mapped
 * into the read-write Device space embedded within the type of the  offset
 * argument to the aforementioned system calls in the intervals
 *
 *  [CT2_RW_R1_OFF, CT2_RW_R1_OFF + CT2_RW_R1_LEN)
 *
 * for the PCI I/O Space 1 Registers Map and
 *
 *  [CT2_RW_R2_OFF, CT2_RW_R2_OFF + CT2_RW_R2_LEN)
 *
 * for the PCI I/O Space 2 Registers Map with the exception that  CTRL_IT  of
 * the PCI I/O Space 1 Registers Map is not made available via this mechanism.
 *
 * The  count  and  offset  arguments to the system calls are interpreted in
 * units of  ct2_reg_t  instead of a byte, with  buf, in particular, having
 * type "pointer to (possibly) cv-qualified ct2_reg_t".  The respective return
 * values on success are the number of  ct2_reg_t  units transferred.  Other
 * than that, no changes in the semantics were introduced.
 *
 * In order for userland to successfully read from a readable Device
 * register with side effects or write to a writable Device register, permission
 * to change the Device state must be derivable from the open file description
 * associated with the Device.  If this is not the case, the operation will fail
 * with  errno  containing the value  EACCES.  Further, a read from a write-only
 * register, a write to a read-only register, a read or write beginning at an
 * address that has no register assigned to it, or any operation that specifies
 * a start address lying outside the intervals defined above will fail with
 * errno  set to the value  EINVAL.  Data transfers over a contiguous range
 * of registers with a valid start address but extending beyond the register
 * range are silently truncated to where the register range ends.  This
 * includes data transfers across the boundaries of each of the two
 * intervals defined above.
 */

#define CT2_RW_R1_OFF           (0)
#define CT2_RW_R2_OFF           (64)
#define CT2_RW_R1_LEN           (CT2_RW_R2_OFF - CT2_RW_R1_OFF)
#define CT2_RW_R2_LEN           (64)


/*--------------------------------------------------------------------------*
 *                            Scaler Values FIFO                            *
 *--------------------------------------------------------------------------*/

/**
 * Access to the Scaler Values FIFO of a Device is provided via the  mmap(2)
 * system call on the open file description obtained from an  open(2)  on the
 * character special file associated with the Device.  The FIFO is mapped
 * neither for writing nor execution into the mmap Device space embedded
 * within the type of the  offset  argument to  mmap(2)  beginning at
 * CT2_FIFO_MMAP_OFF  page size unit bytes for as many bytes as the
 * Device says its FIFO is large (+).
 *
 * In order for userland to successfully  mmap(2)  the FIFO of a Device,
 * exclusive access to the Device must have been obtained, otherwise the call
 * will fail with  errno  set to  EACCES.  The call will also fail, with  errno
 * set to  EINVAL, if any of the  length  or  offset  arguments is invalid w.r.t.
 * the region within the mmap Device space as defined above or if it is to be
 * mapped for writing or execution.
 *
 * NOTE: As long as there exists at least one mapping of the FIFO into
 *       userspace, every attempt to  close(2)  the open file description
 *       that was used to obtain the initial mapping will fail with
 *       errno  set to  EBUSY.
 *
 * (+) This information may be obtained from the sysfs entry to the
 *     PCI node of the Device.
 */

#define CT2_MM_FIFO_OFF         (0)


/*--------------------------------------------------------------------------*
 *           Interrupt Delivery, Device Reset, and Access Control           *
 *--------------------------------------------------------------------------*/

/**
 * The delivery of interrupts generated by a Device, the management of which,
 * and the control of access to the Device, as well as the general Device Reset
 * are performed via special commands to the  ioctl(2)  system call on the open
 * file description obtained from an  open(2)  on the character special file
 * associated with the Device, while any of the  (e)poll(2)  and  select(2)
 * system call(s) may be employed by userland for the asynchronous
 * notification of (the availability of new) interrupts.
 */

#include <linux/ioctl.h>        // _IO*()

#if defined __KERNEL__
# include <linux/time.h>        // struct timespec
#else
# include <time.h>
#endif


struct ct2_in {
    ct2_reg_t               ctrl_it;
    struct timespec         stamp;
};

struct ct2_inv {
    struct ct2_in * const   inv;
    ct2_size_type           inv_len;
};


#define CT2_IOC_MAGIC           'w'

/**
 * CT2_IOC_DEVRST - "[DEV]ice [R]e[S]e[T]"
 *
 * arguments:
 *
 *  -
 *
 * A "Device Reset" shall be defined as the following sequence of operations on
 * the device where we provide a value for every register in the memory sense of
 * the word that can be written to.
 *
 *  1.  disable the generation of interrupts
 *  2.  disable output drivers/stages, ie enable their high impedance state (XXX)
 *  3.  a.  remove the input load from the input stages,
 *      b.  set the input filter master clock frequency divider to (the default of) "1",
 *          capture synchronously but bypass the input filters, and,
 *      c.  on the P201, disable the inputs altogether (XXX)
 *  4.  a.  set the output filter master clock frequency divider to (the default of) "1",
 *          bypass the output filter,
 *          set the output value polarity to "normal", and
 *      b.  fix the output logic value to "0"
 *  5.  set the programmable output logic level to "0"
 *  6.  inhibit any Device internal data movement of the Scaler Values FIFO,
 *      flush the FIFO, and clear FIFO error flags
 *  7.  set the counter clock source to (the default of) the master clock,
 *      open the counter clock gate wide, and
 *      disconnect any internally wired counter control connections
 *  8.  inhibit storage of the counter value in each CCL unit's latch
 *  9.  clear each CCL unit's comparator latch and counter
 * 10.  disable the master clock and
 *      set the clock frequency selector to (the default of) "100 MHz"
 *
 * NOTE: Since we must regard the generation and acknowledgement of interrupts
 *       as state changing operations, and the whole purpose of a general Device
 *       reset is to arrive at a known state, we require that the generation of
 *       interrupts be /disabled/ during the reset.
 *
 * returns:
 *
 *  zero on success
 *  non-zero on failure with  errno  set appropriately:
 *
 *    EACCES  exclusive access was set up previously for the Device, but for
 *            a different open file description than the one in the request
 *
 *    EBUSY   interrupts are still enabled, preventing the request to be
 *            processed
 *
 *    EINTR   the caller was interrupted while waiting for permission to
 *            exclusively access the Device
 *
 *    EINVAL  some arguments to the  ioctl(2)  call where invalid
 */

#define CT2_IOC_DEVRST          _IO (CT2_IOC_MAGIC, 0)

/**
 * CT2_IOC_EDINT - "[E]nable [D]evice [INT]errupts"
 *
 * arguments:
 *
 *  1:  capacity of the interrupt notification queue
 *
 * Have the Operating System set up everything associated with the Device
 * that is required so that we can receive Device interrupts once we enable
 * their generation at the Device proper via SOURCE_IT_A/B.
 *
 * In order to not lose any notification of such interrupts, a queue is set
 * up between the actual interrupt handler and the context that eventually
 * makes them available to interested listeners whose capacity must be given
 * as the argument.  Here, a value of  0  means that the default as determined
 * by the module parameter "inq_length" shall be used for the capacity of
 * the queue.
 *
 * If interrupts are already enabled with a queue capacity  c, the request
 * to re-enable them with a queue capacity  d  will be considered a success
 * without actually performing the required actions if both  c  and  d  are
 * equal and an error otherwise.
 *
 * returns:
 *
 *  zero on success
 *  non-zero on failure with  errno  set appropriately:
 *
 *    EACCES  exclusive access was set up previously for the Device, but for
 *            a different open file description than the one in the request
 *
 *    EBUSY   interrupts are already enabled with a queue capacity different
 *            from the one in the argument of the request
 *
 *    ENOMEM  failure to allocate storage for the notification queue and
 *            the open file description in the request was in blocking mode
 *
 *    EAGAIN  similar to the ENOMEM case, only that the open file description
 *            in the request was in non-blocking mode
 *
 *    EINTR   the caller was interrupted while waiting for permission to
 *            exclusively access the Device
 *
 *    EINVAL  some arguments to the  ioctl(2)  call where invalid
 */

#define CT2_IOC_EDINT           _IOW(CT2_IOC_MAGIC, 01, ct2_size_type)

/**
 * CT2_IOC_DDINT - "[D]isable [D]evice [INT]errupts"
 *
 * arguments:
 *
 *  -
 *
 * Undo everything that was set up during a (previous) CT2_IOC_EDINT call,
 * ignoring the request if interrupts are already disabled.
 *
 * NOTE: No attempts are being made in ensuring that the Device itself
 *       actually ceased to generate interrupts.  Failure to observe this
 *       will most likely result in the kernel complaining about interrupts
 *       "nobody cared" for etcpp.
 *
 * returns:
 *
 *  zero on success
 *  non-zero on failure with  errno  set appropriately:
 *
 *    EACCES  exclusive access was set up previously for the Device, but for
 *            a different open file description than the one in the request
 *
 *    EINTR   the caller was interrupted while waiting for permission to
 *            exclusively access the Device
 *
 *    EINVAL  some arguments to the  ioctl(2)  call where invalid
 */

#define CT2_IOC_DDINT           _IO (CT2_IOC_MAGIC, 02)

/**
 * CT2_IOC_ACKINT - "[ACK]nowledge [INT]errupt"
 *
 * arguments:
 *
 *  1:  pointer to an interrupt notification object
 *
 * Obtain the accumulation of all delivered interrupt notifications since the
 * last successful CT2_IOC_ACKINT call prior to the current request along with
 * the time the most recent delivery occurred, clearing  CTRL_IT  in the
 * interrupt notification storage and updating its time to the time of
 * the current request.  The time is obtained from the clock with ID
 * CLOCK_MONOTONIC_RAW.
 *
 * A value of  0  in  ctrl_it  of the object the argument points to indicates
 * that there were no new interrupt notifications while a non-zero value hints
 * at the delivery of at least one such notification.  In the former case, the
 * stamp  member contains the time the value of  CTRL_IT  in the interrupt
 * notification storage was last read while in the latter, the time  CTRL_IT
 * was last updated is saved.
 *
 * returns:
 *
 *  zero on success
 *  non-zero on failure with  errno  set appropriately:
 *
 *    EFAULT  the argument of the request does not point into a valid
 *            object of type  struct ct2_in  in the calling user context's
 *            address space
 *
 *    EINTR   the caller was interrupted while waiting for permission to
 *            exclusively access the Device
 *
 *    EINVAL  some arguments to the  ioctl(2)  call where invalid
 *
 *    ENXIO   an INQ has been detected to be attached to the open file
 *            description of the request although INQs are not implemented
 */

#define CT2_IOC_ACKINT          _IOR(CT2_IOC_MAGIC, 10, struct ct2_in *)

/**
 * CT2_IOC_AINQ - "[A]ttach [I]nterrupt [N]otification [Q]ueue"
 *
 * returns:
 *
 *    ENOSYS  not implemented
 */

#define CT2_IOC_AINQ            _IOW(CT2_IOC_MAGIC, 11, ct2_size_type)

/**
 * CT2_IOC_DINQ - "[D]etach [I]nterrupt [N]otification [Q]ueue"
 *
 * returns:
 *
 *    ENOSYS  not implemented
 */

#define CT2_IOC_DINQ            _IO (CT2_IOC_MAGIC, 12)

/**
 * CT2_IOC_RINQ - "D[R]ain [I]nterrupt [N]otification [Q]ueue"
 *
 * returns:
 *
 *    ENOSYS  not implemented
 */

#define CT2_IOC_RINQ            _IOR(CT2_IOC_MAGIC, 13, struct ct2_inv *)

/**
 * CT2_IOC_FINQ - "[F]lush [I]nterrupt [N]otification [Q]ueue"
 *
 * returns:
 *
 *    ENOSYS  not implemented
 */

#define CT2_IOC_FINQ            _IOR(CT2_IOC_MAGIC, 14, struct timespec *)

/**
 * CT2_IOC_QXA - "re[Q]uesting e[X]clusive device [A]ccess"
 *
 * arguments:
 *
 *  -
 *
 * Request exclusive access for the open file description in the call.
 *
 * returns:
 *
 *  zero on success
 *  non-zero on failure with  errno  set appropriately:
 *
 *    EACCES  exclusive access was set up previously for the Device, but for
 *            a different open file description than the one in the request
 *
 *    EINTR   the caller was interrupted while waiting for permission to
 *            exclusively access the Device
 *
 *    EINVAL  some arguments to the  ioctl(2)  call where invalid
 */

#define CT2_IOC_QXA             _IO (CT2_IOC_MAGIC, 21)

/**
 * CT2_IOC_LXA - "re[L]inquishing e[X]clusive device [A]ccess"
 *
 * arguments:
 *
 *  -
 *
 * Give up exclusive access for the open file description in the call,
 * ignoring the request if there was no exclusive Device access granted
 * at all.
 *
 * returns:
 *
 *  zero on success
 *  non-zero on failure with  errno  set appropriately:
 *
 *    EACCES  exclusive access was set up previously for the Device, but for
 *            a different open file description than the one in the request
 *
 *    EBUSY   at least one  mmap(2)  of the Scaler Values FIFO was still active
 *
 *    EINTR   the caller was interrupted while waiting for permission to
 *            exclusively access the Device
 *
 *    EINVAL  some arguments to the  ioctl(2)  call where invalid
 */

#define CT2_IOC_LXA             _IO (CT2_IOC_MAGIC, 22)


#endif  // ESRF_CT2_H
