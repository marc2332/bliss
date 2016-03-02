#ifndef __PIXMAPTOOLS_LUT
#define __PIXMAPTOOLS_LUT

#include <stdlib.h>
#include "qimage.h"
#include <cstdlib>

class LutError
{
public:
  LutError(const char * aMessage)
  {
    if(aMessage)
      _msg = strdup(aMessage);
    else
      _msg = strdup("");
  }
  LutError(const LutError &aLutError)
  {
    if(aLutError._msg) 
      _msg = strdup(aLutError._msg);
    else
      _msg = strdup("");
  }
  ~LutError() {free(_msg);}

  const char* msg() const {return _msg;}
private:
  char *_msg;
};

class LUT
{
public :
  enum mapping_meth {LINEAR,LOG,SHIFT_LOG};
  struct XServer_Info;
  
public:
  class Palette
  {
    friend class LUT;
  public:
    enum palette_type {GREYSCALE,TEMP,RED,GREEN,BLUE,REVERSEGREY,MANY,FIT2D,USER};
    enum mode {RGBX,BGRX};
    enum endian {LSB,MSB};

    explicit Palette(palette_type = USER,mode = BGRX) throw();
    
    void setPaletteData(const unsigned int *aPaletteDataPt,int aSize) throw(LutError);
    void getPaletteData(unsigned int* &aPaletteDataPt,int &aSize);
    void fillPalette(palette_type) throw();
    void fillSegment(int from,int to,
		     double R1,double G1,double B1,
		     double R2,double G2,double B2) throw(LutError);
  private:
    
    void _fillSegment(const XServer_Info&,
		      int from,int to,
		      double R1,double G1,double B1,double R2,double G2,double B2) throw();
    void _calcPalette(unsigned int palette[],int fmin, int fmax,LUT::mapping_meth) throw();

    unsigned int _dataPalette[0x10000];
    mode         _mode;
  };

public:
  template<class IN> static void map_on_min_max_val(const IN *data,unsigned int *anImagePt,
						    int column,int row,Palette &aPalette,
						    mapping_meth aMeth,
						    IN &dataMin,IN &dataMax);

  template<class IN> static void map(const IN *data,unsigned int *anImagePt,
				     int column,int row,
				     Palette&,mapping_meth,
				     IN dataMin,IN dataMax);

  // function to transform raw video format into rgb(32bits BGRA8888) image
  class Scaling
  {
  public:
    friend class LUT;
    struct luma;

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
		     YUV444};

    enum mode {UNACTIVE,QUICK,ACCURATE,COLOR_MAPPED};
    
    Scaling();
    ~Scaling();

    void current_type(image_type &aType) const;
    void min_max_mapping(double &minVal,double &maxVal) const;
    
    void set_custom_mapping(double minVal,double maxVal);
    
    void get_mode(mode&) const;
    void set_mode(mode);

    void fill_palette(LUT::Palette::palette_type);
    
    void set_palette_mapping_meth(LUT::mapping_meth);

    void autoscale_min_max(const unsigned char *data,int column,int row,
			   image_type aType);

    void autoscale_plus_minus_sigma(const unsigned char *data,int column,int row,
				    image_type aType,double aSigmaFactor);

  private:
    mutable pthread_mutex_t _lock;
    double	            _minValue,_maxValue;	// min max
    luma		   *_Luma;
    mode		    _mode;

    void _get_minmax_and_mode(double &minVal,double &maxVal,
			      mode &aMode);
  };
  static bool raw_video_2_image(const unsigned char *data,unsigned int *anImagePt,
				int column,int row,
				LUT::Scaling::image_type anImageType,
				Scaling &aScaling);

  static unsigned char* raw_video_2_luma(const unsigned char *data,
					 int column,int row,
					 LUT::Scaling::image_type anImageType);
};
#endif
