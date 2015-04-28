/*-----------------------------------------------------------------------------
 *
 * File:        bit2arr.c
 * $Header: /segfs/bliss/cvs/driver/ESRF/ct2/src/bit2arr.c,v 2.7 2012/07/06 10:27:41 perez Exp $
 * Project:     Linux Device Driver for CUB+mezzanine Compact-PCI board
 *
 * Description: This is a small program that transforms contents of bit
 *              file (after sync words) into a C-array so that new kbuild
 *              mechanism can create the corresponding .o file to be then
 *              linked with drivers's object file to form .ko module.
 *
 * Author(s):   F.Sever
 *
 * Original:    Apr 2006, 
 *
 * $Revision: 2.7 $
 *
 * $Log: bit2arr.c,v $
 * Revision 2.7  2012/07/06 10:27:41  perez
 * Port to esrflinux1-4
 *
 * Revision 2.1  2010/12/02 03:43:27  ahoms
 * * Transferred CT2 project from /segfs/linux/drivers/ct2/kernel2.6/v2.0
 *
 *
 *  Copyright (c) 2006 by European Synchrotron Radiation Facility,
 *                       Grenoble, France
 *
 *----------------------------------------------------------------------------*/

/*----------------------------------------------------------------------
 * Linux header files
 *---------------------------------------------------------------------*/
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <string.h>
#include <getopt.h>
#include <libgen.h>
#include <termios.h>
#include <ctype.h>
#include <errno.h>
#ifdef COM
/* next include file does not exist in RedHat Linux; it existed in Suse */
#include <op_types.h> /* for u8,u16,u32 */
#endif
#include <sys/param.h>
#include <sys/stat.h>

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;




/**
 * swap_Byte() - swap bits [D0-D7] to [D7_D0] in a given byte.
 * @byte: the byte to swap
 *
 * Returns the swapped byte
 */

u8 swap_Byte(u8 byte)
{
        int i;
        u8 reverse_data;

        /* printf("swap_Byte(): In\n"); */
        for (i = 0, reverse_data = 0; i < 8; i ++) {
                reverse_data <<= 1;
                reverse_data |= ((byte >> i) & 0x1);
        }
        /* printf("swap_Byte(): Out\n"); */

        return(reverse_data);
} /* end of function swap_Byte() */




/**
 * get_BitFileSize() - get size of bit file in bytes
 * @bit_file: the name of .BIT (= FPGA) file
 * @file_size: FPGA file size in bytes
 *
 * Returns 0 if OK or error
 */

int get_BitFileSize(char *bit_file, u32 *file_size)
{
        struct stat statbuf;

        printf("get_BitFileSize(): In\n");

        if (stat(bit_file, &statbuf)) {
                printf("Error getting .bit file %s size\n", bit_file);
        	printf("get_BitFileSize(): Out\n");
		*file_size = 0;
        	printf("get_BitFileSize(): Out\n");
                return(errno);
	}
	printf("Size of bit file is %d bytes\n", (int)statbuf.st_size);
	*file_size = (u32)statbuf.st_size;
        printf("get_BitFileSize(): Out\n");
	return 0;
}




/**
 * read_BitFile() - read .BIT file into buffer with a correct size
 * @fp: file pointer returned by open_BitFile()
 * @buffer: buffer allocated with sufficient size in calling environement.
 * @count: usefull buffer length
 *
 * Returns 0 if OK or error
 */

int read_BitFile(FILE *fp, u8 *buffer, int *count)
{
        u8  *p;

        int c0, c1, c2, c3;
        int c4, c5, c6, c7;
        *count = 0;

	printf("read_BitFile(): In\n");

        /*
         * Scan BIT file Header for retrieving general informations
	 * untill detecting dummy (0xffffffff) and synchronization
	 * (0xaa995566) words.
         */
        printf("- Header  BIT string : ");
	fflush(stdout);

        do {
                c0 = fgetc(fp); c1 = fgetc(fp); c2 = fgetc(fp); c3 = fgetc(fp);

                if ((c0 == 0xFF) && (c1 == 0xFF) &&
                    (c2 == 0xFF) && (c3 == 0xFF)) {

                        c4 = fgetc(fp); c5 = fgetc(fp);
                        c6 = fgetc(fp); c7 = fgetc(fp);

                        if ((c4 == 0xAA) && (c5 == 0x99) &&
                            (c6 == 0x55) && (c7 == 0x66)) {
                                printf("\n- Sync Word detected ($AA995566).\n");
                                if (fseek(fp, -8, SEEK_CUR) == -1) {
                		        printf("Error in fseek\n");
                                        return(errno);
                                }
                                break;
                        }
                }

                if ( isascii(c0) && isprint(c0) && (ftell(fp) < 1024) ) {
                        if (iscntrl(c0)) printf(" ");
                        else printf("%c", c0);
                        fflush(stdout);
                }

                if (fseek(fp, -3, SEEK_CUR) == -1) {
                	printf("Error in fseek\n");
                        return(errno);
                }

        } while (c3 != EOF);

        if (c3 == EOF) {
                printf("No synchronization word found\n");
                return(-1);
        }
        printf("Synchronization word found\n");

	/*
	 * Swap bits D0-D7 to D7-D0 for every useful byte
	 */
	p = buffer;
        printf("ptr to start of buffer = %p\n", ((void * )p));

        do {
                *p++ = swap_Byte(c0 = fgetc(fp));

                if (*count <= 10)
                    printf("\t\tFile : %02x - Ram : %02x\n", c0,buffer[*count]);

                (*count) += 1;

        } while (c0 != EOF);

        *count = *count - 1;      /* discard EOF char */

        printf("  FPGA Bit-Stream length = %d bits\n", (*count)*8);

	printf("read_BitFile(): Out\n");

	return(0);
}




/**
 * create_Array() - create array to be included in driver's source file
 * @bitfile: the name of .BIT (= FPGA) file, to extract the name to be used
 *           for the array
 * @buffer: buffer with bytes to be downloaded into FPGA (already correctly 
 *          swapped)
 * @count: usefull buffer length
 * @fp: file pointer of open output file = .c file containing byte array
 *
 */

void create_Array(char *bitfile, char *buffer, int count, FILE *fp)
{
        u8  *p;
	char arrname[MAXPATHLEN];
        int  i = 0;

        printf("create_Array(): In\n");
        printf("create_Array(): Input bit File name = %s\n", bitfile);
        printf("create_Array(): Output Array File pointer = 0x%p\n", ((void * )fp));

	/* extract the name from the bit file */
	strcpy(arrname, strtok(basename(bitfile), "."));
	printf("Array name = %s\n", arrname);

	fprintf(fp, "static uint8_t %sbit[] = {",arrname);

	p = buffer;
	for (i = 0; i < count; i++) {
		if (i != count - 1) {
			fprintf(fp,"0x%02x,",*p++);
		} else {
			fprintf(fp,"0x%02x",*p++);
		}
	}
	fprintf(fp,"};\n");
		
        printf("create_Array(): Out\n");
}



int main(int argc, char *argv[]) {

	char    infile[MAXPATHLEN];
	char    outfile[MAXPATHLEN];
	char    interm[MAXPATHLEN];
	u8      *buffer;
	FILE    *fpin, *fpout;
	int     file_size;
	int     count;
	int     ret = 0;

	if ( ( argc < 2 ) || ( argc > 3 ) ) {
		printf("Usage: %s <IN-bit-file> [<OUT-C-source-file>]\n",argv[0]);
		return(1);
	}

	fpin = (FILE *)NULL;
	fpout = (FILE *)NULL;

	strcpy(infile,argv[1]);
	printf("Main: In bit file = %s\n", infile);

    if ( argc == 2 ) {

        /* need next one since strtok destroys orig.string */
        strcpy(interm,argv[1]);
        printf("Main: In bit file = %s\n", infile);
        strcpy(outfile, strtok(basename(interm), "."));
        strcat(outfile,"_bit.c");

    } else {

        snprintf(outfile, sizeof(outfile), "%s", argv[2]);

    }

	printf("Main: Out source file = %s\n", outfile);

        fpin = fopen(infile, "r");
        if (fpin == NULL) {
                printf("Main: Error opening bit-file %s\n", infile);
                return(errno);
        }
        printf("Main: Bit File pointer = 0x%p\n", ((void * )fpin));

	ret = get_BitFileSize(infile, &file_size);
	if (ret) return(ret);
	printf("Main: Size of bit file is %d bytes\n", file_size);

	/* added 10 to file_size on 09/11/2006 as found in c111 soft */
	//buffer = (u8 *)calloc(file_size+10, 1);
	buffer = (u8 *)calloc(file_size, 1);
	if (buffer == NULL) {
		printf("Main: Error allocating buffer\n");
		return(errno);
	}
	printf("Main: Local Buffer pointer = 0x%p\n", ((void * )buffer));

	ret = read_BitFile(fpin, buffer, &count);
	if (ret) return(ret);
	printf("Main: Usefull Buffer size = %d\n", count);
	fclose(fpin);


	/* Try reducing count for 10 bytes, since currently have the 
	 * following problem (output of /var/log/messages when loading
	 * c216 driver):
	 * 
	 * Nb of bytes to load = 336680
	 * Nov  9 16:38:19 l-cb032-2 kernel: c216:LoadVirtex():
	 *              PCI to Add-On FIFO full on writing at index = 336672 
	 * 
	 * We see the problem arise 8 bytes before the end.
	 * We can try to cut these 8 bytes, by reducing count by 10.
	 */
	count -= 10;

        fpout = fopen(outfile, "w+");
        if (fpout == NULL) {
                printf("Error opening array-file %s\n", outfile);
                return(errno);
        }
        printf("Main: Output Array File pointer = 0x%p\n", ((void * )fpout));

	create_Array(infile, buffer, count, fpout);
	fclose(fpout);

	free(buffer);

	return 0;
}

