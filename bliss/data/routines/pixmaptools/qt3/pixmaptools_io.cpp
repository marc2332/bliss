/* -*- coding: utf-8 -*- */
/*
 * This file is part of the bliss project
 *
 * Copyright (c) 2015-2019 Beamline Control Unit, ESRF
 * Distributed under the GNU LGPLv3. See LICENSE for more info.
*/

#include <iostream>
#include <stdlib.h>

#include <pixmaptools_io.h>

#ifdef HAVE_X
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#endif

#ifdef HAVE_MITSHM
#include <sys/types.h>
#include <sys/shm.h>
#include <X11/extensions/XShm.h>
#endif




static const char ID[] = "pixmaptools";
static bool aRloginFlag = !!getenv("SSH_CLIENT");

struct IO::Data {
    int shmsize;
    int shmpolicy;
    int threshold;
    int bpp;
    int byteorder;
#ifdef HAVE_X
    XImage *ximage;
#endif

#ifdef HAVE_MITSHM
    XShmSegmentInfo *shminfo;
#endif
};


IO::IO()
{
    m_bShm = false;
    d = new Data;
    d->ximage = NULL;
    d->shmsize = 0;
    
#ifdef HAVE_MITSHM
    int ignore;
    if (!aRloginFlag && XQueryExtension(qt_xdisplay(), "MIT-SHM", &ignore, &ignore, &ignore)) {
	if (XShmQueryExtension(qt_xdisplay()))
	    m_bShm = true;
    }
    if (!m_bShm) {
	std::cerr << "" << ID << ": MIT-SHM not available!" << std::endl;
	return;
    }

    // Sort out bit format. Create a temporary XImage for this.
    d->shminfo = new XShmSegmentInfo;
    d->ximage = XShmCreateImage(qt_xdisplay(), (Visual *) QPaintDevice::x11AppVisual(),
				QPaintDevice::x11AppDepth(), ZPixmap, 0L, d->shminfo, 10, 10);
    d->bpp = d->ximage->bits_per_pixel;
    int bpp = d->bpp;
    if (d->ximage->byte_order == LSBFirst)
	bpp++;
    int red_shift = lowest_bit(d->ximage->red_mask);
    int green_shift = lowest_bit(d->ximage->green_mask);
    int blue_shift = lowest_bit(d->ximage->blue_mask);
    XDestroyImage(d->ximage); d->ximage = 0L;
    d->shmsize = 0;

    // Offer discrete possibilities for the bitformat. Each will have its
    // own routine. The general algorithm using bitshifts is much too slow;
    // this has to be done for every pixel!

    if ((bpp == 32) && (red_shift == 16) && (green_shift == 8) &&
	    (blue_shift == 0))
	d->byteorder = bo32_ARGB;
    else if ((bpp == 33) && (red_shift == 16) && (green_shift == 8) &&
	    (blue_shift == 0))
	d->byteorder = bo32_BGRA;
    else if ((bpp == 24) && (red_shift == 16) && (green_shift == 8) &&
	    (blue_shift == 0))
	d->byteorder = bo24_RGB;
    else if ((bpp == 25) && (red_shift == 16) && (green_shift == 8) &&
	    (blue_shift == 0))
	d->byteorder = bo24_BGR;
    else if ((bpp == 16) && (red_shift == 11) && (green_shift == 5) &&
	    (blue_shift == 0))
	d->byteorder = bo16_RGB_565;
    else if ((bpp == 16) && (red_shift == 10) && (green_shift == 5) &&
	    (blue_shift == 0))
	d->byteorder = bo16_RGB_555;
    else if ((bpp == 17) && (red_shift == 11) && (green_shift == 5) &&
	    (blue_shift == 0))
	d->byteorder = bo16_BGR_565;
    else if ((bpp == 16) && (red_shift == 10) && (green_shift == 5) &&
	    (blue_shift == 0))
	d->byteorder = bo16_BGR_555;
    else if ((bpp == 8) || (bpp == 9))
	d->byteorder = bo8;
    else {
	m_bShm = false;
	std::cerr << "" << ID << ": Byte order not supported!" << std::endl;
	std::cerr << "" << ID << ": red = " << d->ximage->red_mask << ", green = " << d->ximage->green_mask << ", blue = " << d->ximage->blue_mask << std::endl;
	std::cerr << "" << ID << ": Please report to <jansen@kde.org>" << std::endl;
    }
#endif
}


IO::~IO()
{
  destroyXImage();
  destroyShmSegment();
  delete d;
}

QPixmap IO::convertToPixmap(const QImage &img)
{
    int size = img.width() * img.height();
    if (m_bShm && aRloginFlag && (img.depth() > 1) && (d->bpp > 8) && (size > d->threshold)) {
	QPixmap dst(img.width(), img.height());
	putImage(&dst, 0, 0, &img);
	return dst;
    } else {
	QPixmap dst;
	dst.convertFromImage(img);
	return dst;
    }
	
}

QImage IO::convertToImage(const QPixmap &pm)
{
    QImage image;
    int size = pm.width() * pm.height();
    if (m_bShm && aRloginFlag && (d->bpp >= 8) && (size > d->threshold))
	image = getImage(&pm, 0, 0, pm.width(), pm.height());
    else
	image = pm.convertToImage();
    return image;
}


void IO::putImage(QPixmap *dst, const QPoint &offset, 
		  const QImage *src)
{
    putImage(dst, offset.x(), offset.y(), src);
}


void IO::putImage(QPixmap *dst, int dx, int dy, const QImage *src)
{
#ifdef HAVE_MITSHM
  int size = src->width() * src->height();
  if (m_bShm && aRloginFlag && (src->depth() > 1) && (d->bpp > 8) && (size > d->threshold))
    {
      initXImage(src->width(), src->height());
      convertToXImage(*src);
//       XShmPutImage(qt_xdisplay(), dst->handle(), qt_xget_temp_gc(qt_xscreen(),false), d->ximage,
// 		   dx, dy, 0, 0, src->width(), src->height(), false);
      XShmPutImage(qt_xdisplay(), dst->handle(), qt_xget_temp_gc(qt_xscreen(),false), d->ximage,
 		   0,0,dx, dy, src->width(), src->height(), false);

      XSync(qt_xdisplay(), false);
      doneXImage();
    } 
  else 
#endif
    {
      QPixmap pix;
      pix.convertFromImage(*src);
      bitBlt(dst, dx, dy, &pix, 0, 0, pix.width(), pix.height());
    }
}

QImage IO::getImage(const QPixmap *src, const QRect &rect)
{
  return getImage(src, rect.x(), rect.y(), rect.width(), rect.height());
}

QImage IO::getImage(const QPixmap *src, int sx, int sy, int sw, int sh)
{
  QImage image;
#ifdef HAVE_MITSHM
  int size = src->width() * src->height();
  if ((m_bShm && aRloginFlag) && (d->bpp >= 8) && (size > d->threshold)) 
    {
      initXImage(sw, sh);
      XShmGetImage(qt_xdisplay(), src->handle(), d->ximage, sx, sy, AllPlanes);
      image = convertFromXImage();
      doneXImage();
    } 
  else 
#endif
    {
      QPixmap pix(sw, sh);
      bitBlt(&pix, 0, 0, src, sx, sy, sw, sh);
      image = pix.convertToImage();
    }
  return image;
}

void IO::preAllocShm(int size)
{
    destroyXImage();
    createShmSegment(size);
}

void IO::setShmPolicy(int policy)
{
    switch (policy) {
    case ShmDontKeep:
	d->shmpolicy = ShmDontKeep;
	d->threshold = 5000;
	break;
    case ShmKeepAndGrow:
	d->shmpolicy = ShmKeepAndGrow;
	d->threshold = 2000;
	break;
    default:
	break;
    }
}

void IO::initXImage(int w, int h)
{
#ifdef HAVE_X
    if (d->ximage && (w == d->ximage->width) && (h == d->ximage->height))
	return;

    createXImage(w, h);
    int size = d->ximage->bytes_per_line * d->ximage->height;
    if (size > d->shmsize)
	createShmSegment(size);
    d->ximage->data = d->shminfo->shmaddr;
#endif
}


void IO::doneXImage()
{
    if (d->shmpolicy == ShmDontKeep) {
	destroyXImage();
	destroyShmSegment();
    }
}

void IO::destroyXImage()
{
#ifdef HAVE_X
   if (d->ximage) {
	XDestroyImage(d->ximage); 
	d->ximage = 0L;
    }
#endif
}

void IO::createXImage(int w, int h)
{
#ifdef HAVE_MITSHM
  destroyXImage();
  d->ximage = XShmCreateImage(qt_xdisplay(), (Visual *) QPaintDevice::x11AppVisual(),
			      QPaintDevice::x11AppDepth(), ZPixmap, 0L, d->shminfo, w, h);
#endif
}

void IO::destroyShmSegment()
{
#ifdef HAVE_MITSHM
  if (d->shmsize) {
    XShmDetach(qt_xdisplay(), d->shminfo);
    shmdt(d->shminfo->shmaddr);
    d->shmsize = 0;
  }
#endif
}

void IO::createShmSegment(int size)
{
#ifdef HAVE_X
  destroyShmSegment();
  d->shminfo->shmid = shmget(IPC_PRIVATE, size, IPC_CREAT|0777);
  if (d->shminfo->shmid < 0) {
    std::cerr << "" << ID << ": Could not get sysv shared memory segment" << std::endl;
    m_bShm = false;
    return;
  }

  d->shminfo->shmaddr = (char *) shmat(d->shminfo->shmid, 0, 0);
  if (d->shminfo->shmaddr < 0) {
    std::cerr << "" << ID << ": Could not attach sysv shared memory segment" << std::endl;
    m_bShm = false;
    shmctl(d->shminfo->shmid, IPC_RMID, 0);
    return;
  }

  d->shminfo->readOnly = false;
  if (!XShmAttach(qt_xdisplay(), d->shminfo)) {
    std::cerr << "" << ID << ": X-Server could not attach shared memory segment" << std::endl;
    m_bShm = false;
    shmdt(d->shminfo->shmaddr);
    shmctl(d->shminfo->shmid, IPC_RMID, 0);
    return;
  }

  d->shmsize = size;
  XSync(qt_xdisplay(), false);
  shmctl(d->shminfo->shmid, IPC_RMID, 0);
#endif
}


/*
 * The following functions convertToXImage/convertFromXImage are a little
 * long. This is because of speed, I want to get as much out of the inner
 * loop as possible.
 */

QImage IO::convertFromXImage()
{
  QImage image;
#ifdef HAVE_X
  int x, y;
  int width = d->ximage->width, height = d->ximage->height;
  int bpl = d->ximage->bytes_per_line;
  char *data = d->ximage->data;

  if (d->bpp == 8) {
    image.create(width, height, 8);

    // Query color map. Don't remove unused entries as a speed
    // optmization.
    int i, ncells = 256;
    XColor *cmap = new XColor[ncells];
    for (i=0; i<ncells; i++)
      cmap[i].pixel = i;
    XQueryColors(qt_xdisplay(), QPaintDevice::x11AppColormap(),
		 cmap, ncells);
    image.setNumColors(ncells);
    for (i=0; i<ncells; i++)
      image.setColor(i, qRgb(cmap[i].red, cmap[i].green, cmap[i].blue >> 8));
  } else
    image.create(width, height, 32);

  switch (d->byteorder) {

  case bo8:
    {
      for (y=0; y<height; y++)
	memcpy(image.scanLine(y), data + y*bpl, width);
      break;
    }

  case bo16_RGB_565: 
  case bo16_BGR_565:
    {
      Q_INT32 pixel, *src;
      QRgb *dst, val;
      for (y=0; y<height; y++) {
	src = (Q_INT32 *) (data + y*bpl);
	dst = (QRgb *) image.scanLine(y);
	for (x=0; x<width/2; x++) {
	  pixel = *src++;
	  val = ((pixel & 0xf800) << 8) | ((pixel & 0x7e0) << 4) |
	    ((pixel & 0x1f) << 3);
	  *dst++ = val;
	  pixel >>= 16;
	  val = ((pixel & 0xf800) << 8) | ((pixel & 0x7e0) << 4) |
	    ((pixel & 0x1f) << 3);
	  *dst++ = val;
	}
	if (width%2) {
	  pixel = *src++;
	  val = ((pixel & 0xf800) << 8) | ((pixel & 0x7e0) << 4) |
	    ((pixel & 0x1f) << 3);
	  *dst++ = val;
	}
      }
      break;
    }

  case bo16_RGB_555: 
  case bo16_BGR_555:
    {
      Q_INT32 pixel, *src;
      QRgb *dst, val;
      for (y=0; y<height; y++) {
	src = (Q_INT32 *) (data + y*bpl);
	dst = (QRgb *) image.scanLine(y);
	for (x=0; x<width/2; x++) {
	  pixel = *src++;
	  val = ((pixel & 0x7c00) << 9) | ((pixel & 0x3e0) << 6) |
	    ((pixel & 0x1f) << 3);
	  *dst++ = val;
	  pixel >>= 16;
	  val = ((pixel & 0x7c00) << 9) | ((pixel & 0x3e0) << 6) |
	    ((pixel & 0x1f) << 3);
	  *dst++ = val;
	}
	if (width%2) {
	  pixel = *src++;
	  val = ((pixel & 0x7c00) << 9) | ((pixel & 0x3e0) << 6) |
	    ((pixel & 0x1f) << 3);
	  *dst++ = val;
	}
      }
      break;
    }

  case bo24_RGB:
    {
      char *src;
      QRgb *dst;
      int w1 = width/4;
      Q_INT32 d1, d2, d3;
      for (y=0; y<height; y++) {
	src = data + y*bpl;
	dst = (QRgb *) image.scanLine(y);
	for (x=0; x<w1; x++) {
	  d1 = *((Q_INT32 *)src);
	  d2 = *((Q_INT32 *)src + 1);
	  d3 = *((Q_INT32 *)src + 2);
	  src += 12;
	  *dst++ = d1;
	  *dst++ = (d1 >> 24) | (d2 << 8);
	  *dst++ = (d3 << 16) | (d2 >> 16);
	  *dst++ = d3 >> 8;
	}
	for (x=w1*4; x<width; x++) {
	  d1 = *src++ << 16;
	  d1 += *src++ << 8;
	  d1 += *src++;
	  *dst++ = d1;
	}
      }
      break;
    }

  case bo24_BGR:
    {
      char *src;
      QRgb *dst;
      int w1 = width/4;
      Q_INT32 d1, d2, d3;
      for (y=0; y<height; y++) {
	src = data + y*bpl;
	dst = (QRgb *) image.scanLine(y);
	for (x=0; x<w1; x++) {
	  d1 = *((Q_INT32 *)src);
	  d2 = *((Q_INT32 *)src + 1);
	  d3 = *((Q_INT32 *)src + 2);
	  src += 12;
	  *dst++ = d1;
	  *dst++ = (d1 >> 24) | (d2 << 8);
	  *dst++ = (d3 << 16) | (d2 >> 16);
	  *dst++ = d3 >> 8;
	}
	for (x=w1*4; x<width; x++) {
	  d1 = *src++;
	  d1 += *src++ << 8;
	  d1 += *src++ << 16;
	  *dst++ = d1;
	}
      }
      break;
    }

  case bo32_ARGB: 
  case bo32_BGRA:
    {
      for (y=0; y<height; y++)
	memcpy(image.scanLine(y), data + y*bpl, width*4);
      break;
    }

  }
#endif
  return image;
}

void IO::convertToXImage(const QImage &img)
{
#ifdef HAVE_X
  int x, y;
  int width = d->ximage->width, height = d->ximage->height;
  int bpl = d->ximage->bytes_per_line;
  char *data = d->ximage->data;

  switch (d->byteorder) {

  case bo16_RGB_555: 
  case bo16_BGR_555:

    if (img.depth() == 32) {
      QRgb *src, pixel;
      Q_INT32 *dst, val;
      for (y=0; y<height; y++) {
	src = (QRgb *) img.scanLine(y);
	dst = (Q_INT32 *) (data + y*bpl);
	for (x=0; x<width/2; x++) {
	  pixel = *src++;
	  val = ((pixel & 0xf80000) >> 9) | ((pixel & 0xf800) >> 5) |
	    ((pixel & 0xff) >> 3);
	  pixel = *src++;
	  val |= (((pixel & 0xf80000) >> 9) | ((pixel & 0xf800) >> 5) |
		  ((pixel & 0xff) >> 3)) << 16;
	  *dst++ = val;
	}
	if (width%2) {
	  pixel = *src++;
	  *((Q_INT16 *)dst) = ((pixel & 0xf80000) >> 9) | 
	    ((pixel & 0xf800) >> 5) | ((pixel & 0xff) >> 3);
	}
      }
    } else {
      uchar *src;
      Q_INT32 val, *dst;
      QRgb pixel, *clut = img.colorTable();
      for (y=0; y<height; y++) {
	src = img.scanLine(y);
	dst = (Q_INT32 *) (data + y*bpl);
	for (x=0; x<width/2; x++) {
	  pixel = clut[*src++];
	  val = ((pixel & 0xf80000) >> 9) | ((pixel & 0xf800) >> 5) |
	    ((pixel & 0xff) >> 3);
	  pixel = clut[*src++];
	  val |= (((pixel & 0xf80000) >> 9) | ((pixel & 0xf800) >> 5) |
		  ((pixel & 0xff) >> 3)) << 16;
	  *dst++ = val;
	}
	if (width%2) {
	  pixel = clut[*src++];
	  *((Q_INT16 *)dst) = ((pixel & 0xf80000) >> 9) | 
	    ((pixel & 0xf800) >> 5) | ((pixel & 0xff) >> 3);
	}
      }
    }
    break;

  case bo16_RGB_565: 
  case bo16_BGR_565:

    if (img.depth() == 32) {
      QRgb *src, pixel;
      Q_INT32 *dst, val;
      for (y=0; y<height; y++) {
	src = (QRgb *) img.scanLine(y);
	dst = (Q_INT32 *) (data + y*bpl);
	for (x=0; x<width/2; x++) {
	  pixel = *src++;
	  val = ((pixel & 0xf80000) >> 8) | ((pixel & 0xfc00) >> 5) |
	    ((pixel & 0xff) >> 3);
	  pixel = *src++;
	  val |= (((pixel & 0xf80000) >> 8) | ((pixel & 0xfc00) >> 5) |
		  ((pixel & 0xff) >> 3)) << 16;
	  *dst++ = val;
	}
	if (width%2) {
	  pixel = *src++;
	  *((Q_INT16 *)dst) = ((pixel & 0xf80000) >> 8) | 
	    ((pixel & 0xfc00) >> 5) | ((pixel & 0xff) >> 3);
	}
      }
    } else {
      uchar *src;
      Q_INT32 val, *dst;
      QRgb pixel, *clut = img.colorTable();
      for (y=0; y<height; y++) {
	src = img.scanLine(y);
	dst = (Q_INT32 *) (data + y*bpl);
	for (x=0; x<width/2; x++) {
	  pixel = clut[*src++];
	  val = ((pixel & 0xf80000) >> 8) | ((pixel & 0xfc00) >> 5) |
	    ((pixel & 0xff) >> 3);
	  pixel = clut[*src++];
	  val |= (((pixel & 0xf80000) >> 8) | ((pixel & 0xfc00) >> 5) |
		  ((pixel & 0xff) >> 3)) << 16;
	  *dst++ = val;
	}
	if (width%2) {
	  pixel = clut[*src++];
	  *((Q_INT16 *)dst) = ((pixel & 0xf80000) >> 8) | 
	    ((pixel & 0xfc00) >> 5) | ((pixel & 0xff) >> 3);
	}
      }
    }
    break;

  case bo24_RGB:

    if (img.depth() == 32) {
      char *dst;
      int w1 = width/4;
      QRgb *src, d1, d2, d3, d4;
      for (y=0; y<height; y++) {
	src = (QRgb *) img.scanLine(y);
	dst = data + y*bpl;
	for (x=0; x<w1; x++) {
	  d1 = (*src++ & 0xffffff); 
	  d2 = (*src++ & 0xffffff);
	  d3 = (*src++ & 0xffffff); 
	  d4 = (*src++ & 0xffffff);
	  *((Q_INT32 *)dst) = d1 | (d2 << 24);
	  *((Q_INT32 *)dst+1) = (d2 >> 8) | (d3 << 16);
	  *((Q_INT32 *)dst+2) = (d4 << 8) | (d3 >> 16);
	  dst += 12;
	}
	for (x=w1*4; x<width; x++) {
	  d1 = *src++;
	  *dst++ = qRed(d1);
	  *dst++ = qGreen(d1);
	  *dst++ = qBlue(d1);
	}
      }
    } else {
      uchar *src, *dst;
      int w1 = width/4;
      QRgb *clut = img.colorTable(), d1, d2, d3, d4;
      for (y=0; y<height; y++) {
	src = img.scanLine(y);
	dst = (uchar *) data + y*bpl;
	for (x=0; x<w1; x++) {
	  d1 = (clut[*src++] & 0xffffff);
	  d2 = (clut[*src++] & 0xffffff);
	  d3 = (clut[*src++] & 0xffffff);
	  d4 = (clut[*src++] & 0xffffff);
	  *((Q_INT32 *)dst) = d1 | (d2 << 24);
	  *((Q_INT32 *)dst+1) = (d2 >> 8) | (d3 << 16);
	  *((Q_INT32 *)dst+2) = (d4 << 8) | (d3 >> 16);
	  dst += 12;
	}
	for (x=w1*4; x<width; x++) {
	  d1 = clut[*src++];
	  *dst++ = qRed(d1);
	  *dst++ = qGreen(d1);
	  *dst++ = qBlue(d1);
	}
      }
    }
    break;

  case bo24_BGR:

    if (img.depth() == 32) {
      char *dst;
      QRgb *src, d1, d2, d3, d4;
      int w1 = width/4;
      for (y=0; y<height; y++) {
	src = (QRgb *) img.scanLine(y);
	dst = data + y*bpl;
	for (x=0; x<w1; x++) {
	  d1 = (*src++ & 0xffffff); 
	  d2 = (*src++ & 0xffffff);
	  d3 = (*src++ & 0xffffff); 
	  d4 = (*src++ & 0xffffff);
	  *((Q_INT32 *)dst) = d1 | (d2 << 24);
	  *((Q_INT32 *)dst+1) = (d2 >> 8) | (d3 << 16);
	  *((Q_INT32 *)dst+2) = (d4 << 8) | (d3 >> 16);
	  dst += 12;
	}
	for (x=w1*4; x<width; x++) {
	  d1 = *src++;
	  *dst++ = qBlue(d1);
	  *dst++ = qGreen(d1);
	  *dst++ = qRed(d1);
	}
      }
    } else {
      uchar *src, *dst;
      int w1 = width/4;
      QRgb *clut = img.colorTable(), d1, d2, d3, d4;
      for (y=0; y<height; y++) {
	src = img.scanLine(y);
	dst = (uchar *) data + y*bpl;
	for (x=0; x<w1; x++) {
	  d1 = (clut[*src++] & 0xffffff);
	  d2 = (clut[*src++] & 0xffffff);
	  d3 = (clut[*src++] & 0xffffff);
	  d4 = (clut[*src++] & 0xffffff);
	  *((Q_INT32 *)dst) = d1 | (d2 << 24);
	  *((Q_INT32 *)dst+1) = (d2 >> 8) | (d3 << 16);
	  *((Q_INT32 *)dst+2) = (d4 << 8) | (d3 >> 16);
	  dst += 12;
	}
	for (x=w1*4; x<width; x++) {
	  d1 = clut[*src++];
	  *dst++ = qBlue(d1);
	  *dst++ = qGreen(d1);
	  *dst++ = qRed(d1);
	}
      }
    }
    break;

  case bo32_ARGB: 
  case bo32_BGRA:

    if (img.depth() == 32) {
      for (y=0; y<height; y++)
	memcpy(data + y*bpl, img.scanLine(y), width*4);
    } else {
      uchar *src;
      QRgb *dst, *clut = img.colorTable();
      for (y=0; y<height; y++) {
	src = img.scanLine(y);
	dst = (QRgb *) (data + y*bpl);
	for (x=0; x<width; x++)
	  *dst++ = clut[*src++];
      }
    }
    break;

  }
#endif
}
