#ifndef __PIXMAPTOOLS_LUT
#define __PIXMAPTOOLS_LUT

#include "qimage.h"

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
    enum palette_type {GREYSCALE,TEMP,RED,GREEN,BLUE,REVERSEGREY,MANY,GEOGRAPHICAL,USER};
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
    void _calcPalette(unsigned int palette[],int fmin, int fmax,mapping_meth) throw();

    unsigned int _dataPalette[0x10000];
    mode         _mode;
  };
public:
  template<class IN> static void map_on_min_max_val(const IN *data,unsigned int *anImagePt,
						    int column,int row,Palette &aPalette,
						    mapping_meth aMeth,
						    IN &dataMin,IN &dataMax);

  template<class IN> static void map_on_plus_minus_sigma(const IN *data,unsigned int *anImagePt,
							 int column,int row,Palette &aPalette,
							 mapping_meth aMeth,
							 double aSigmaFactor,
							 IN &dataMinUse4LookUp,IN &dataMaxUse4LookUp);


  template<class IN> static void map(const IN *data,unsigned int *anImagePt,
				     int column,int row,
				     Palette&,mapping_meth,
				     IN dataMin,IN dataMax);
};
#endif
