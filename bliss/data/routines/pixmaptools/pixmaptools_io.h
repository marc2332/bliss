#ifdef __unix
#define HAVE_X 1
#define HAVE_MITSHM 1
#endif

#include <iostream>

#include "qimage.h"
#include "qpixmap.h"

/* int32 was long before, now int, because of amd64 */
typedef char       int8; typedef unsigned char      uint8;
typedef short     int16; typedef unsigned short     uint16;
typedef int       int32; typedef unsigned int       uint32;
typedef long long int64; typedef unsigned long long uint64;
typedef float   float32;
typedef double  float64;

class IO
{
 public:
  IO(const QPixmap&);
  ~IO();

  /**
   * Convert an image to a pixmap.
   * @param image The image to convert.
   * @return The pixmap containing the image.
   */
  QPixmap convertToPixmap(const QImage&);
    
  /**
   * Convert a pixmap to an image.
   * @param pixmap The pixmap to convert.
   * @return The image.
   */
  QImage convertToImage(const QPixmap &pixmap);

  /**
   * Bitblt an image onto a pixmap.
   * @param dst The destination pixmap.
   * @param dx Destination x offset.
   * @param dy Destination y offset.
   * @param src The image to load.
   */
  void putImage(QPixmap *dst, int dx, int dy, const QImage *src);

  /**
   * This function is identical to the one above. It only differs in the
   * arguments it accepts.
   */
  void putImage(QPixmap *dst, const QPoint &offset, const QImage *src);

  /**
   * Transfer (a part of) a pixmap to an image.
   * @param src The source pixmap.
   * @param sx Source x offset.
   * @param sy Source y offset.
   * @param sw Source width.
   * @param sh Source height.
   * @return The image.
   */
  QImage getImage(const QPixmap *src, int sx, int sy, int sw, int sh);

  /**
   * This function is identical to the one above. It only differs in the
   * arguments it accepts.
   */
  QImage getImage(const QPixmap *src, const QRect &rect);

  /**
   * Shared memory allocation policies.
   */
  enum ShmPolicies {
    ShmDontKeep,
    ShmKeepAndGrow
  };

  /**
   * Set the shared memory allocation policy. See the introduction for
   * IO for a discussion.
   * @param policy The alloction policy.
   */
  void setShmPolicy(int policy);

  /**
   * Pre-allocate shared memory. IO will be able to transfer images
   * up to this size without resizing.
   * @param size The size of the image in @em pixels.
   */
  void preAllocShm(int size);

 private:
  /*
   * Supported XImage byte orders. The notation ARGB means bytes
   * containing A:R:G:B succeed in memory.
   */
  enum ByteOrders {
    bo32_ARGB, bo32_BGRA, bo24_RGB, bo24_BGR,
    bo16_RGB_565, bo16_BGR_565, bo16_RGB_555, 
    bo16_BGR_555, bo8
  };
  bool   m_bShm;
  struct Data;
  struct Data *d;

  void initXImage(int w, int h);
  void doneXImage();
  void createXImage(int w, int h);
  void destroyXImage();
  void createShmSegment(int size);
  void destroyShmSegment();
  void convertToXImage(const QImage &);
  QImage convertFromXImage();

  // returns the position (0..63) of highest bit set in a word, or 0 if none.
#define Z(N) if ((x>>N)&(((typeof(x))1<<N)-1)) { x>>=N; i+=N; }
/*   static int highest_bit(uint8  x) {int i=0;              Z(4)Z(2)Z(1)return i;} */
/*   static int highest_bit(uint16 x) {int i=0;          Z(8)Z(4)Z(2)Z(1)return i;} */
  static int highest_bit(uint32 x) {int i=0;     Z(16)Z(8)Z(4)Z(2)Z(1)return i;}
/*   static int highest_bit(uint64 x) {int i=0;Z(32)Z(16)Z(8)Z(4)Z(2)Z(1)return i;} */
#undef Z
  // returns the position (0..63) of lowest bit set in a word, or 0 if none.
  template <class T> static int lowest_bit(T n) { return highest_bit((~n+1)&n); }
};
