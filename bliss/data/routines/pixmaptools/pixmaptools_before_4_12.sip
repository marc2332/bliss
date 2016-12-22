

%Import QtGui/QtGuimod.sip

%Module qt4

%ModuleHeaderCode
extern "C" { void pixmap_import_array();}
%End

%PostInitialisationCode
pixmap_import_array();
%End
%Doc
<h1>Class IO</h1>
<p>
This class was copied from KPixmapIO and just rename IO
</p>
%End
 
class IO
{

%TypeHeaderCode
#include <pixmaptools_io.h>
%End

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
    QImage convertToImage(const QPixmap&);

    /**
     * Bitblt an image onto a pixmap.
     * @param dst The destination pixmap.
     * @param dx Destination x offset.
     * @param dy Destination y offset.
     * @param src The image to load.
     */
    void putImage(QPixmap*,int,int,const QImage *);

    /**
     * This function is identical to the one above. It only differs in the
     * arguments it accepts.
     */
    void putImage(QPixmap*,const QPoint &,const QImage *);

    /**
     * Transfer (a part of) a pixmap to an image.
     * @param src The source pixmap.
     * @param sx Source x offset.
     * @param sy Source y offset.
     * @param sw Source width.
     * @param sh Source height.
     * @return The image.
     */
    QImage getImage(const QPixmap*,int,int,int,int);

    /**
     * This function is identical to the one above. It only differs in the
     * arguments it accepts.
     */
    QImage getImage(const QPixmap*,const QRect&);

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
    void setShmPolicy(int);

    /**
     * Pre-allocate shared memory. IO will be able to transfer images
     * up to this size without resizing.
     * @param size The size of the image in @em pixels.
     */
    void preAllocShm(int);
};


%Doc
<h1>Class LUT</h1>
<p>
This class is a lookup for colormap
</p>
%End

class LUT
{
%TypeHeaderCode
#include <pixmaptools_lut.h>
%End

public :
  enum mapping_meth {LINEAR,LOG,SHIFT_LOG};
  
public:
  class Palette
  {
%TypeHeaderCode
#include <pixmaptools_lut.h>
%End
  public:
    enum palette_type {GREYSCALE,TEMP,RED,GREEN,BLUE,REVERSEGREY,MANY,GEOGRAPHICAL,USER};
    enum mode {RGBX,BGRX};
    enum endian {LSB,MSB};

    explicit Palette(palette_type = USER,mode = RGBX);
%TypeCode
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#define PY_ARRAY_UNIQUE_SYMBOL _PixmapNumpyArray
#include "numpy/arrayobject.h"
#include <iostream>
using namespace std;
extern "C"
{
  void pixmap_import_array()
  {
    import_array();
  }
}
template<class IN> void _create_palette_from_data(unsigned int *aDestPalette,const IN *aSrcPalette)
{
  Py_BEGIN_ALLOW_THREADS;
  for(int i = 0;i < 0x10000;++i,++aDestPalette,aSrcPalette += 4)
     {
      *aDestPalette  = aSrcPalette[0] & 0xff;
      *aDestPalette |= (aSrcPalette[1] & 0xff) << 8;
      *aDestPalette |= (aSrcPalette[2] & 0xff) << 16;
      *aDestPalette |= (aSrcPalette[3] & 0xff) << 24;	
     }
  Py_END_ALLOW_THREADS;
}
%End
    SIP_PYOBJECT getPaletteData();
%MethodCode
  unsigned int *aPaletteDataPt;
  int aSize;
  Py_BEGIN_ALLOW_THREADS;
  sipCpp->getPaletteData(aPaletteDataPt,aSize);
  Py_END_ALLOW_THREADS;
  sipRes = PyString_FromStringAndSize((const char *)aPaletteDataPt,aSize);
  delete aPaletteDataPt;
%End
    void setPaletteData(SIP_PYOBJECT);
%MethodCode
  PyArrayObject *colormapData;
  if(!(colormapData = (PyArrayObject*)PyArray_ContiguousFromObject(a0,NPY_NOTYPE,0,0)))
    {
      LutError *sipExceptionCopy = new LutError("Couldn't create an array");	
      sipRaiseTypeException(sipType_LutError,sipExceptionCopy);
      return NULL;
    }
   else
    {	
	int aNbVal = 1;
	for(int i = 0;i < PyArray_NDIM(colormapData);++i)
	  aNbVal *= PyArray_DIM(colormapData,i);
	if(aNbVal != (0x10000 * 4))
	   {
	      LutError *sipExceptionCopy = new LutError("Palette must have 65536 entry of RBGX or BGRX");
      	      sipRaiseTypeException(sipType_LutError,sipExceptionCopy);
              Py_DECREF(colormapData);
	      return NULL;
	   }
	unsigned int aTmpPalette[0x10000];
	switch(PyArray_TYPE(colormapData))
	{
 	 case NPY_BYTE:
	 case NPY_UBYTE:
	      _create_palette_from_data(aTmpPalette,(unsigned char*)PyArray_DATA(colormapData));break;
         case NPY_SHORT:
	 case NPY_USHORT:
	      _create_palette_from_data(aTmpPalette,(unsigned short*)PyArray_DATA(colormapData));break;
         case NPY_INT:
	 case NPY_UINT:
	       _create_palette_from_data(aTmpPalette,(unsigned int*)PyArray_DATA(colormapData));break;
	 case NPY_LONG:
	 case NPY_ULONG:
               _create_palette_from_data(aTmpPalette,(unsigned long*)PyArray_DATA(colormapData));break;
	 default:
	  {
	      LutError *sipExceptionCopy = new LutError("Palette type can by char,int,long,short");
      	      sipRaiseTypeException(sipType_LutError,sipExceptionCopy);
              Py_DECREF(colormapData);
	      return NULL;
          }
	}
	try
	{
	  sipCpp->setPaletteData(aTmpPalette,sizeof(aTmpPalette));
	}
	catch(LutError &err)
	{
	      LutError *sipExceptionCopy = new LutError(err);
      	      sipRaiseTypeException(sipType_LutError,sipExceptionCopy);
              Py_DECREF(colormapData);
	      return NULL;
	}
	
	Py_DECREF(colormapData);
    }
%End
    void fillPalette(palette_type) throw();
    void fillSegment(int from,int to,
		     double R1,double G1,double B1,
		     double R2,double G2,double B2) throw(LutError);
  };
  class Scaling
  {
%TypeHeaderCode
#include <pixmaptools_lut.h>
%End
  public:
    enum image_type {UNDEF,
		     Y8,	// monochrome 8bits
		     Y16,	// monochrome 16bits
		     Y32,	// monochrome 32bits
		     Y64,	// monochrome 64bits
		     I420,	// YVU 8bits
		     RGB555,
		     RGB565,
		     RGB24,
		     RGB32,
		     BGR24,
		     BGR32,
		     BAYER_RG8,	// BAYER RG 8bits (prosilica)
		     BAYER_RG16, // BAYER RG 16bits (prosilica)
		     BAYER_BG8,	// BAYER BG 8bits (basler)
		     BAYER_BG16, // BAYER BG 16bits (basler)
		     YUV411,
		     YUV422,
		     YUV444,
		     YUV422PACKED};

    enum mode {UNACTIVE,QUICK,ACCURATE,COLOR_MAPPED};
    
    Scaling();
    ~Scaling();

    void current_type(LUT::Scaling::image_type &aType /Out/) const;
    void min_max_mapping(double &minVal /Out/,double &maxVal /Out/) const;
    
    void set_custom_mapping(double minVal,double maxVal);
    
    void get_mode(LUT::Scaling::mode& /Out/) const;
    void set_mode(LUT::Scaling::mode);

    void fill_palette(LUT::Palette::palette_type);
    
    void set_palette_mapping_meth(LUT::mapping_meth);

    void autoscale_min_max(const unsigned char *data,int column,int row,
			   LUT::Scaling::image_type aType);

    void autoscale_plus_minus_sigma(const unsigned char *data,int column,int row,
				    LUT::Scaling::image_type aType,double aSigmaFactor);
   };
%TypeCode
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#define PY_ARRAY_UNIQUE_SYMBOL _PixmapNumpyArray
#define NO_IMPORT_ARRAY
#include "numpy/arrayobject.h"

#define MAP_FUNCTION \
  PyArrayObject *src; \
  if(!(src = (PyArrayObject*)PyArray_ContiguousFromObject(a0,NPY_NOTYPE,2,2))) \
    { \
      LutError *sipExceptionCopy = new LutError("Input Array must be a 2x2 array"); \
      sipRaiseTypeException(sipType_LutError,sipExceptionCopy); \
      return NULL; \
    } \
    int column,row; \
    column = PyArray_DIM(src,1);	\
    row = PyArray_DIM(src,0);	\
    PyObject *aRImage;\
    switch(PyArray_TYPE(src))	\
    { \
	case NPY_BYTE: \
		{ \
		MAP_IMAGE(char); \
		sipRes = Py_BuildValue("(O(b,b))",aRImage,aMin,aMax); \
		break; \
		} \
	case NPY_UBYTE: \
		{ \
		MAP_IMAGE(unsigned char); \
		sipRes = Py_BuildValue("(O(B,B))",aRImage,aMin,aMax); \
		break; \
		} \
         case NPY_SHORT: \
		{ \
		MAP_IMAGE(short); \
		sipRes = Py_BuildValue("(O(h,h))",aRImage,aMin,aMax); \
		break; \
		} \
	 case NPY_USHORT: \
		{ \
		MAP_IMAGE(unsigned short); \
		sipRes = Py_BuildValue("(O(H,H))",aRImage,aMin,aMax); \
		break; \
		} \
         case NPY_INT: \
		{ \
		MAP_IMAGE(int); \
		sipRes = Py_BuildValue("(O(i,i))",aRImage,aMin,aMax); \
		break; \
		} \
	 case NPY_UINT: \
		{ \
		MAP_IMAGE(unsigned int); \
		sipRes = Py_BuildValue("(O(I,I))",aRImage,aMin,aMax); \
		break; \
		} \
	 case NPY_LONG: \
		{ \
		MAP_IMAGE(long); \
		sipRes = Py_BuildValue("(O(l,l))",aRImage,aMin,aMax); \
		break; \
		} \
	 case NPY_ULONG: \
		{ \
		MAP_IMAGE(unsigned long); \
		sipRes = Py_BuildValue("(O(k,k))",aRImage,aMin,aMax); \
		break; \
		} \
	 case NPY_FLOAT: \
		{ \
		MAP_IMAGE(float); \
		sipRes = Py_BuildValue("(O(f,f))",aRImage,aMin,aMax); \
		break; \
		} \
	 case NPY_DOUBLE: \
		{ \
		MAP_IMAGE(double); \
		sipRes = Py_BuildValue("(O(d,d))",aRImage,aMin,aMax); \
		break; \
		} \
	 default: \
	  { \
	      LutError *sipExceptionCopy = new LutError("Input Array type not supported"); \
      	      sipRaiseTypeException(sipType_LutError,sipExceptionCopy); \
              Py_DECREF(src); \
	      return NULL; \
          } \
     }\
 Py_DECREF(src);\
 Py_DECREF(aRImage);
%End

 static SIP_PYTUPLE map_on_min_max_val(SIP_PYOBJECT,Palette&,mapping_meth);
%MethodCode
#ifdef MAP_IMAGE
#undef MAP_IMAGE
#endif
#define MAP_IMAGE(TYPE)\
 TYPE aMin,aMax;\
 QImage aMappedImage(column,row,QImage::Format_ARGB32);\
 Py_BEGIN_ALLOW_THREADS;\
 LUT::map_on_min_max_val<TYPE>((TYPE*)PyArray_DATA((PyArrayObject*)src), \
						  (unsigned int*)aMappedImage.bits(), \
						  column,row,*a1,a2,aMin,aMax);	\
 Py_END_ALLOW_THREADS;\
 aRImage = sipConvertFromNewInstance(new QImage(aMappedImage),sipClass_QImage,NULL);
MAP_FUNCTION
%End

 static SIP_PYTUPLE map_on_plus_minus_sigma(SIP_PYOBJECT,Palette&,mapping_meth,double);
%MethodCode
#ifdef MAP_IMAGE
#undef MAP_IMAGE
#endif
#define MAP_IMAGE(TYPE)\
 TYPE aMin,aMax;\
 QImage aMappedImage(column,row,QImage::Format_ARGB32);\
 Py_BEGIN_ALLOW_THREADS;\
 LUT::map_on_plus_minus_sigma<TYPE>((TYPE*)PyArray_DATA(src),(unsigned int*)aMappedImage.bits(),column,row,*a1,a2,a3,aMin,aMax);\
 Py_END_ALLOW_THREADS;\
 aRImage = sipConvertFromNewInstance(new QImage(aMappedImage),sipClass_QImage,NULL);
MAP_FUNCTION
%End
 static SIP_PYTUPLE map(SIP_PYOBJECT,Palette&,mapping_meth,double,double);
%MethodCode
#ifdef MAP_IMAGE
#undef MAP_IMAGE
#endif
#define MAP_IMAGE(TYPE)\
 TYPE aMin = (TYPE)a3;\
 TYPE aMax = (TYPE)a4;\
 if(a3 < 0. && aMin > 0) aMin = 0;\
 QImage aMappedImage(column,row,QImage::Format_ARGB32);\
 Py_BEGIN_ALLOW_THREADS;\
 LUT::map<TYPE>((TYPE*)PyArray_DATA(src),(unsigned int*)aMappedImage.bits(),column,row,*a1,a2,aMin,aMax);\
 Py_END_ALLOW_THREADS;\
 aRImage = sipConvertFromNewInstance(new QImage(aMappedImage),sipClass_QImage,NULL);
MAP_FUNCTION
%End

 static SIP_PYTUPLE transform_autoscale(SIP_PYOBJECT,Palette&,mapping_meth);
%MethodCode
#ifdef MAP_IMAGE
#undef MAP_IMAGE
#endif
#define MAP_IMAGE(TYPE)\
 TYPE aMin,aMax;\
 npy_intp dims[] = {npy_intp(row << 2),npy_intp(column)};\
 aRImage = PyArray_SimpleNew(2,dims,NPY_UBYTE); \
 Py_BEGIN_ALLOW_THREADS;\
 LUT::map_on_min_max_val<TYPE>((TYPE*)PyArray_DATA((PyArrayObject*)src), \
			       (unsigned int*)PyArray_DATA((PyArrayObject*)aRImage), \
			       column,row,*a1,a2,aMin,aMax);		\
 Py_END_ALLOW_THREADS;
MAP_FUNCTION
%End

 static SIP_PYTUPLE transform(SIP_PYOBJECT,Palette&,mapping_meth,double,double);
%MethodCode
#ifdef MAP_IMAGE
#undef MAP_IMAGE
#endif
#define MAP_IMAGE(TYPE)\
 TYPE aMin = (TYPE)a3;\
 TYPE aMax = (TYPE)a4;\
 npy_intp dims[] = {npy_intp(row << 2),npy_intp(column)};\
 aRImage = PyArray_SimpleNew(2,dims,NPY_UBYTE); \
 Py_BEGIN_ALLOW_THREADS;\
 LUT::map<TYPE>((TYPE*)PyArray_DATA((PyArrayObject*)src),		\
		(unsigned int*)PyArray_DATA((PyArrayObject*)aRImage),	\
		column,row,*a1,a2,aMin,aMax);				\
 Py_END_ALLOW_THREADS;
MAP_FUNCTION
%End

static SIP_PYTUPLE raw_video_2_image(const unsigned char *data,int column,int row,
				     LUT::Scaling::image_type anImageType,
				     LUT::Scaling &aScaling);
%MethodCode
 bool aReturnFlag;
 QImage aMappedImage(a1,a2,QImage::Format_ARGB32);
 Py_BEGIN_ALLOW_THREADS;
 aReturnFlag = LUT::raw_video_2_image(a0,(unsigned int*)aMappedImage.bits(),a1,a2,
			       	      a3,*a4);
 Py_END_ALLOW_THREADS;
 PyObject *aRImage = sipConvertFromNewInstance(new QImage(aMappedImage),sipClass_QImage,NULL);
 sipRes = Py_BuildValue("(O,N))",aReturnFlag ? Py_True : Py_False,aRImage);
%End

static SIP_PYOBJECT raw_video_2_luma(const unsigned char *data,int column,int row,
				     LUT::Scaling::image_type anImageType);
%MethodCode
unsigned char* luma = NULL;
Py_BEGIN_ALLOW_THREADS;
luma = LUT::raw_video_2_luma(a0,a1,a2,a3);
Py_END_ALLOW_THREADS;
npy_intp dims[] = {npy_intp(a2),npy_intp(a1)};
if(luma)
  {
    switch(a3)
      {
      case LUT::Scaling::Y8: 
      case LUT::Scaling::RGB555: 
      case LUT::Scaling::RGB565: 
      case LUT::Scaling::RGB24: 
      case LUT::Scaling::RGB32: 
      case LUT::Scaling::BGR24: 
      case LUT::Scaling::BGR32: 
      case LUT::Scaling::BAYER_RG8: 
      case LUT::Scaling::YUV411: 
      case LUT::Scaling::YUV422: 
      case LUT::Scaling::YUV444: 
	sipRes = PyArray_SimpleNewFromData(2,dims,NPY_UBYTE,luma);break;
      case LUT::Scaling::Y16: 
      case LUT::Scaling::BAYER_RG16: 
	sipRes = PyArray_SimpleNewFromData(2,dims,NPY_USHORT,luma);break;
      case LUT::Scaling::Y32:
	sipRes = PyArray_SimpleNewFromData(2,dims,NPY_INT32,luma);break;
      default:
	sipRes = NULL;
      }
    if(sipRes)
#ifdef NPY_ARRAY_OWNDATA
      PyArray_ENABLEFLAGS((PyArrayObject*)sipRes,NPY_ARRAY_OWNDATA);
#else
      ((PyArrayObject*)sipRes)->flags |= NPY_OWNDATA;
#endif
  }
else
sipRes = NULL;
%End
};
class LutError
{
%TypeHeaderCode
#include <pixmaptools_lut.h>
%End

public:
  LutError(const char * aMessage);
  ~LutError();
 const char* msg() const;
};

class Stat
{
%TypeHeaderCode
#include <pixmaptools_stat.h>
%End
%TypeCode
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#define PY_ARRAY_UNIQUE_SYMBOL _PixmapNumpyArray
#define NO_IMPORT_ARRAY
#include "numpy/arrayobject.h"
template<class IN> 
inline void _histo_full(IN* data,int nbElem,NPY_TYPES type,PyObject* &Y,PyObject* &X)
{
  std::vector<IN> vectorX;
  std::vector<int> vectorY;
  Py_BEGIN_ALLOW_THREADS;
  Stat::histo_full<IN>(data,nbElem,vectorY,vectorX);
  Py_END_ALLOW_THREADS;
  npy_intp ydims[] = {npy_intp(vectorY.size())};
  Y = PyArray_SimpleNew(1,ydims,NPY_INT);
  typename std::vector<int>::iterator i = vectorY.begin();
  for(int * Ydata = (int*)PyArray_DATA((PyArrayObject*)Y);
      i != vectorY.end();++i,++Ydata)
    *Ydata = *i;

  npy_intp xdims[] = {npy_intp(vectorX.size())};
  X = PyArray_SimpleNew(1,xdims,type);
  typename std::vector<IN>::iterator j = vectorX.begin();
  for(IN *Xdata = (IN*)PyArray_DATA((PyArrayObject*)X);
      j != vectorX.end();++j,++Xdata)
       *Xdata = *j;
}

template<class IN>
inline void _histo(IN* data,int nbElem,NPY_TYPES type,PyObject* &Y,PyObject* &X,
		   int bins,const IN aMinVal,const IN aMaxVal)
{
  std::vector<IN> vectorX;
  std::vector<int> vectorY;
  Py_BEGIN_ALLOW_THREADS;
  Stat::histo<IN>(data,nbElem,vectorY,vectorX,bins,aMinVal,aMaxVal);
  Py_END_ALLOW_THREADS;
  npy_intp ydims[] = {npy_intp(vectorY.size())};
  Y = PyArray_SimpleNew(1,ydims,NPY_INT);
  typename std::vector<int>::iterator i = vectorY.begin();
  for(int * Ydata = (int*)PyArray_DATA((PyArrayObject*)Y);
      i != vectorY.end();++i,++Ydata)
    *Ydata = *i;

  npy_intp xdims[] = {npy_intp(vectorX.size())};
  X = PyArray_SimpleNew(1,xdims,type);
  typename std::vector<IN>::iterator j = vectorX.begin();
  for(IN *Xdata = (IN*)PyArray_DATA((PyArrayObject*)X);
      j != vectorX.end();++j,++Xdata)
    *Xdata = *j;
}

#define HISTO_FUNCTION \
  PyArrayObject *src; \
  if(!(src = (PyArrayObject*)PyArray_ContiguousFromObject(a0,NPY_NOTYPE,0,0))) \
    return NULL; \
    \
    int nbElem = PyArray_NDIM(src);  \
    npy_intp *dims = PyArray_DIMS(src); \
    for(int i = 1;i < nbElem;++i) \
       nbElem *= dims[i]; \
    PyObject *Y,*X;\
    switch(PyArray_TYPE(src))	\
    { \
	case NPY_BYTE: \
		{ \
		HISTO(char); \
		break; \
		} \
	case NPY_UBYTE: \
		{ \
		HISTO(unsigned char); \
		break; \
		} \
         case NPY_SHORT: \
		{ \
		HISTO(short); \
		break; \
		} \
	 case NPY_USHORT: \
		{ \
		HISTO(unsigned short); \
		break; \
		} \
         case NPY_INT: \
		{ \
		HISTO(int); \
		break; \
		} \
	 case NPY_UINT: \
		{ \
		HISTO(unsigned int); \
		break; \
		} \
	 case NPY_LONG: \
		{ \
		HISTO(long); \
		break; \
		} \
	 case NPY_ULONG: \
		{ \
		HISTO(unsigned long); \
		break; \
		} \
	 case NPY_FLOAT: \
		{ \
		HISTO(float); \
		break; \
		} \
	 case NPY_DOUBLE: \
		{ \
		HISTO(double); \
		break; \
		} \
	 default: \
	      return NULL; \
     }\
 sipRes = Py_BuildValue("(O,O)",Y,X); \
 Py_DECREF(src);\
 Py_DECREF(X);\
 Py_DECREF(Y);
%End

public:
static SIP_PYTUPLE histo_full(SIP_PYOBJECT);
%MethodCode
#ifdef HISTO
#undef HISTO
#endif
#define HISTO(TYPE) _histo_full((TYPE*)PyArray_DATA(src),nbElem,\
				(NPY_TYPES)PyArray_TYPE(src),Y,X);
HISTO_FUNCTION
%End

static SIP_PYOBJECT histo(SIP_PYOBJECT,int,double = 0,double = 0);
%MethodCode
#ifdef HISTO
#undef HISTO
#endif
#define HISTO(TYPE)  \
 TYPE maxVal,minVal;\
 minVal = (TYPE)a2; \
 maxVal = (TYPE)a3; \
 _histo((TYPE*)PyArray_DATA(src),nbElem,			\
	(NPY_TYPES)PyArray_TYPE(src),Y,X,a1,minVal,maxVal);
HISTO_FUNCTION
%End
};
