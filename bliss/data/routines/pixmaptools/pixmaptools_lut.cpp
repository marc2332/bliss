#include "pixmaptools_lut.h"
#include <math.h>

struct LUT::XServer_Info {
  int byte_order;
  int pixel_size;

  unsigned int rshift;
  unsigned int rbit;

  unsigned int gshift;
  unsigned int gbit;
  
  unsigned int bshift;
  unsigned int bbit;

  unsigned int ashift;
  unsigned int abit;
};

struct lutConfiguration
{
  lutConfiguration()
  {
    LUT::XServer_Info &Xservinfo = _config[LUT::Palette::RGBX];
    Xservinfo.pixel_size = 4;
    short aVal = 1;
    Xservinfo.byte_order = *((char*)&aVal) ? LUT::Palette::LSB : LUT::Palette::MSB;
    Xservinfo.rshift = 0,Xservinfo.rbit = 8;

    Xservinfo.gshift = 8,Xservinfo.gbit = 8;

    Xservinfo.bshift = 16,Xservinfo.bbit = 8;

    Xservinfo.ashift = 24,Xservinfo.abit = 8;

    Xservinfo = _config[LUT::Palette::BGRX];
    Xservinfo.pixel_size = 4;
    Xservinfo.byte_order = *((char*)&aVal) ? LUT::Palette::LSB : LUT::Palette::MSB;

    Xservinfo.ashift = 24,Xservinfo.abit = 8;

    Xservinfo.rshift = 16,Xservinfo.rbit = 8;

    Xservinfo.gshift = 8,Xservinfo.gbit = 8;

    Xservinfo.bshift = 0,Xservinfo.bbit = 8;
    double *aPt = _logCache;
    for(int i = 0;i < 0x10000;++i,++aPt)
      *aPt = log10(i);
  }
  const LUT::XServer_Info& getServerInfo(LUT::Palette::mode aMode){return _config[aMode];}
  inline double log(int aVal) const {return _logCache[aVal];}
  LUT::XServer_Info _config[2];
  double _logCache[0x10000];
};

static lutConfiguration theLutConfiguration;

typedef union {
  struct {
    unsigned char b1;
    unsigned char b2;
    unsigned char b3;
    unsigned char b4;
  } c;
  unsigned int p;
} swaptype;

/** @brief constructor of the Palette object
 *
 *  @param aMode there is two possible mode (RGBX or BGRX)
*/
LUT::Palette::Palette(palette_type pType,mode aMode) throw() : _mode(aMode)
{
  if(pType == USER) 
    memset(_dataPalette,0,sizeof(_dataPalette));
  else
    fillPalette(pType);
}
/** @brief create standard palette
 */
void LUT::Palette::fillPalette(palette_type aType) throw()
{
  const XServer_Info &config = theLutConfiguration.getServerInfo(_mode);
  switch(aType)
    {
    case TEMP:
      _fillSegment(config,0     , 0x4000,  0, 0, 1, 0, 1, 1);
      _fillSegment(config,0x4000, 0x8000,  0, 1, 1, 0, 1, 0);
      _fillSegment(config,0x8000, 0xc000,  0, 1, 0, 1, 1, 0);
      _fillSegment(config,0xc000, 0x10000, 1, 1, 0, 1, 0, 0);
      break;
    case MANY:
      _fillSegment(config,0     , 0x2aaa,  0, 0, 1, 0, 1, 1);
      _fillSegment(config,0x2aaa, 0x5555,  0, 1, 1, 0, 1, 0);
      _fillSegment(config,0x5555, 0x8000,  0, 1, 0, 1, 1, 0);
      _fillSegment(config,0x8000, 0xaaaa,  1, 1, 0, 1, 0, 0);
      _fillSegment(config,0xaaaa, 0xd555,  1, 0, 0, 1, 1, 0);
      _fillSegment(config,0xd555, 0x10000, 1, 1, 0, 1, 1, 1);
      break;
    case GEOGRAPHICAL:
      _fillSegment(config,0, 0x1999, 0, 0, 0, 0, 0, 1);
      _fillSegment(config,0x1999, 0x3333, 0, 0, 1, 0.7686274509803922, 0.7686274509803922, 1);
      _fillSegment(config,0x3333, 0x4ccc,0.7686274509803922, 0.7686274509803922, 1, 
		   0.54117647058823526, 0.86274509803921573, 0.21568627450980393);
      _fillSegment(config,0x4ccc, 0x6666, 0.54117647058823526, 0.86274509803921573, 0.21568627450980393,
		   1, 1, 0.47058823529411764);
      _fillSegment(config,0x6666, 0x8000, 1, 1, 0.47058823529411764,
		   1, 0.7686274509803922, 0.36078431372549019);
      _fillSegment(config,0x8000, 0x9999, 1, 0.7686274509803922, 0.36078431372549019,
		   1, 0.74901960784313726, 0);
      _fillSegment(config,0x9999, 0xb336, 1, 0.74901960784313726, 0,
		   0.7686274509803922, 0.5, 0);
      _fillSegment(config,0xb336, 0xccd0, 0.7686274509803922, 0.5, 0, 
		   0.86274509803921573, 0.24313725490196078, 1);
      _fillSegment(config,0xccd0, 0xe66a, 0.86274509803921573, 0.24313725490196078, 1,
		   0.86274509803921573, 0.5, 1);
      _fillSegment(config,0xe66a, 0x10000, 0.86274509803921573, 0.5, 1,
		   1, 1, 1);
      break;
    case BLUE: 
      _fillSegment(config,0, 0x10000, 0, 0, 0, 0, 0, 1); break;
    case GREEN:
      _fillSegment(config,0, 0x10000, 0, 0, 0, 0, 1, 0); break;
    case RED:
      _fillSegment(config,0, 0x10000, 0, 0, 0, 1, 0, 0);break;
    case REVERSEGREY:
      _fillSegment(config,0, 0x10000, 1, 1, 1, 0, 0, 0);break;
    case GREYSCALE:
    default:
      _fillSegment(config,0, 0x10000, 0, 0, 0, 1, 1, 1);
      break;
    }
}
/**
 * @brief fill a contigus segment of the palette
 * @param from first index of the segment
 * @param to last index of the segment
 * @param RGB -> R = R1 + (R2 - R1) * (i-from) / (to - from)
 */
void LUT::Palette::fillSegment(int from,int to,
			       double R1,double G1,double B1,
			       double R2,double G2,double B2) throw(LutError)
{
  const XServer_Info &config = theLutConfiguration.getServerInfo(_mode);
  if(from < 0)
    throw LutError("fillSegment : from must be > 0");
  if(to > 0x10000) 
    throw LutError("fillSegment : to must be lower or equal to 65536");
  if(from > to)
    throw LutError("fillSegment : form must be lower than to");
  _fillSegment(config,from,to,R1,G1,B1,R2,G2,B2);
}
/// @brief set the data palette
void LUT::Palette::setPaletteData(const unsigned int *aPaletteDataPt,int aSize) throw(LutError)
{
  if(aSize != sizeof(int) * 0x10000)
    throw LutError("setPaletteData : Palette must be have 65536 value");
  memcpy(_dataPalette,aPaletteDataPt,aSize);
}

///@brief get the data palette
void LUT::Palette::getPaletteData(unsigned int * &aPaletteDataPt,int &aSize)
{
  aPaletteDataPt = new unsigned int[0x10000];
  memcpy(aPaletteDataPt,_dataPalette,sizeof(unsigned int) * 0x10000);
  aSize = sizeof(unsigned int) * 0x10000;
}
///@brief util to fill the palette
void LUT::Palette::_fillSegment(const XServer_Info &Xservinfo,
				int from, int to,
				double R1,double G1,double B1,double R2,double G2,double B2) throw()
{
  unsigned int *ptr;
  int R, G, B;
  double Rcol, Gcol, Bcol, Rcst, Gcst, Bcst;
  double coef, width, rwidth, gwidth, bwidth; 
  swaptype value;

  /* R = R1 + (R2 - R1) * (i-from) / (to - from)
     palette_col = (int)(R * (2**rbit-1) + 0.5) << rshift |
     (int)(G * (2**gbit-1) + 0.5) << gshift |
     (int)(B * (2**bbit-1) + 0.5) << bshift
  */

  Rcol = (1<<Xservinfo.rbit) - 1;
  Rcst = Rcol * R1 + 0.5;
  Gcol = (1<<Xservinfo.gbit) - 1;
  Gcst = Gcol * G1 + 0.5;
  Bcol = (1<<Xservinfo.bbit) - 1;
  Bcst = Bcol * B1 + 0.5;
  width = double(to - from);
  rwidth = Rcol * (R2 - R1) / width;
  gwidth = Gcol * (G2 - G1) / width;
  bwidth = Bcol * (B2 - B1) / width;
  int diff = to-from;

#if defined (__i386__) || defined(__x86_64__)
  if (Xservinfo.byte_order == LSB) 
    {
      for (ptr = _dataPalette + from,coef = 0;coef < diff;++coef,++ptr) 
	{
	  R = int(Rcst + rwidth * coef);
	  G = int(Gcst + gwidth * coef);
	  B = int(Bcst + bwidth * coef);
	  *ptr = (R << Xservinfo.rshift) | (G << Xservinfo.gshift) | (B << Xservinfo.bshift) | (0xff << Xservinfo.ashift);
	}
    }
  else
    {
      for (ptr = _dataPalette + from,coef = 0;coef < diff;++coef,++ptr) 
	{
	  R = int(Rcst + rwidth * coef);
	  G = int(Gcst + gwidth * coef);
	  B = int(Bcst + bwidth * coef);
	  value.p = (R << Xservinfo.rshift) | (G << Xservinfo.gshift) | (B << Xservinfo.bshift) | (0xff << Xservinfo.ashift);
	  *ptr = value.c.b1 << 24 | value.c.b2 << 16 | value.c.b3 << 8;
	}
    }
#else
  if (Xservinfo.byte_order == MSB) 
    {
      
      for (ptr = _dataPalette + from,coef = 0;coef < diff;++coef,++ptr) 
	{
	  R = int(Rcst + rwidth * coef);
	  G = int(Gcst + gwidth * coef);
	  B = int(Bcst + bwidth * coef);
	  *ptr = (R << Xservinfo.rshift) | (G << Xservinfo.gshift) | (B << Xservinfo.bshift) | (0xff << Xservinfo.ashift);
	}
    }
  else
    {
      for (ptr = _dataPalette + from,coef = 0;coef < diff;++coef,++ptr) 
	{
	  R = int(Rcst + rwidth * coef);
	  G = int(Gcst + gwidth * coef);
	  B = int(Bcst + bwidth * coef);
	  value.p = (R << Xservinfo.rshift) | (G << Xservinfo.gshift) | (B << Xservinfo.bshift) | (0xff << Xservinfo.ashift);
	  *ptr = value.c.b4 << 16 | value.c.b3 << 8 | value.c.b2;
	}
    }
#endif
}
///@brief calc a palette for the data
void LUT::Palette::_calcPalette(unsigned int palette[],int fmin, int fmax, 
				mapping_meth meth) throw()
{
  double lmin, lmax;
  /*
    SPS_LINEAR:   mapdata = A * data + B
    SPS_LOG   :   mapdata = (A * log(data)) + B
  */
  if (!fmin && meth != LUT::LINEAR) 
    fmin = 1;
  double A,B;
  if(fmax - fmin)
    {
    if (meth == LUT::LINEAR) 
      lmin = fmin,lmax = fmax;
    else
      lmin = log10(fmin),lmax = log10(fmax);

    A = 0xffff / (lmax - lmin);
    B = - (0xffff * lmin) / (lmax - lmin);

    double round_min;
    if(meth == LUT::LINEAR)
      round_min = A * fmin + B;
    else
      round_min = (A * log10(fmin)) + B;

    if(round_min < 0.0 && round_min > -1E-5 )
      B += round_min;
  }
  else 
    A = 1.0,B = 0.0;


  unsigned int *pal = palette;
  unsigned int *palend = palette;
  *(pal + 0xffff) = *(_dataPalette + 0xffff);
  *pal = *_dataPalette;
  pal += fmin ; palend += fmax;
  if (meth == LINEAR) 
    for(int j = fmin;pal <= palend && j <= fmax;++j,++pal)
      *pal = *(_dataPalette + int(A * j + B)); 
  else
    for(int j = fmin;pal <= palend && j <= fmax;++j,++pal)
      *pal = *(_dataPalette + int(A * theLutConfiguration.log(j) + B));
}

// LUT TEMPLATE
/** @brief transform <b>data</b> to an image using the palette give in args
 * 
 *  autoscale data on min/max
 *  @param data the data source array
 *  @param anImagePt a data dest array it size must be >= sizeof(int) * nb pixel
 *  @param column the number of column of the source data
 *  @param row the number of row of the source data
 *  @param aPalette the palette colormap used to transform source data to an image
 *  @param aMeth the mapping methode
 *  @param dataMin return the min data value
 *  @param dataMax return the max data value
 */
template<class IN> void __attribute__ ((used)) LUT::map_on_min_max_val(const IN *data,
								       unsigned int *anImagePt,int column,int row,
								       Palette &aPalette,
								       mapping_meth aMeth,
								       IN &dataMin,IN &dataMax)
{
  if(aMeth != LOG)
    _find_min_max(data,column * row,dataMin,dataMax);
  else
    _find_minpos_max(data,column * row,dataMin,dataMax);
  map(data,anImagePt,column,row,aPalette,aMeth,dataMin,dataMax);
}
/** @brief transform <b>data</b> to an image using the palette give in args
 * 
 *  autoscale data on sigma factor, lookup will be done between -> average + ou - sigma_factor * standardDeviation
 *  @param data the data source array
 *  @param anImagePt a data dest array it size must be >= sizeof(int) * nb pixel
 *  @param column the number of column of the source data
 *  @param row the number of row of the source data
 *  @param aPalette the palette colormap used to transform source data to an image
 *  @param aMeth the mapping methode
 *  @param aSigmaFactor the sigma factor
 *  @param dataMinUse4LookUp return the min data use for the lookup
 *  @param dataMaxUse4LookUp return the max data use for the lookup
 */
template<class IN> void LUT::map_on_plus_minus_sigma(const IN *data,unsigned int *anImagePt,int column,int row,
						     Palette &aPalette,
						     mapping_meth aMeth,
						     double aSigmaFactor,
						     IN &dataMinUse4LookUp,IN &dataMaxUse4LookUp)
{
  IN anAverage,aStd;
  IN dataMin,dataMax;
  if(aMeth != LOG)
    _find_min_max(data,column * row,dataMin,dataMax);
  else
    _find_minpos_max(data,column * row,dataMin,dataMax);
  _get_average_std(data,column * row,anAverage,aStd) ;
  double tmpMin4LookUp = anAverage - aSigmaFactor * aStd;
  dataMinUse4LookUp = IN(tmpMin4LookUp);

  if(tmpMin4LookUp < 0. && dataMinUse4LookUp > 0) dataMinUse4LookUp = 0; // FOR UNSIGNED
  if(dataMinUse4LookUp < dataMin) dataMinUse4LookUp = dataMin;

  dataMaxUse4LookUp = IN(anAverage + aSigmaFactor * aStd);
  map(data,anImagePt,column,row,aPalette,aMeth,dataMinUse4LookUp,dataMaxUse4LookUp);
}
/** @brief calculate the average and the standard deviation
 */
template<class IN> static void _get_average_std(const IN *aData,int aNbValue,IN &anAverage,IN &aStd) 
{
  const IN *aTmpPt = aData;
  double aSum = 0.;
  for(int i = 0;i < aNbValue;++i,++aTmpPt)
    aSum += *aTmpPt;
  double localAverage = aSum / aNbValue;
  anAverage = (IN)localAverage;

  //STD
  aTmpPt = aData;
  aSum = 0.;
  for(int i = 0;i < aNbValue;++i,++aTmpPt)
    {
      double diff = *aTmpPt - localAverage;
      diff *= diff;
      aSum += diff;
    }
  aSum /= aNbValue;
  aStd = (IN) sqrt(aSum);
}
/** @brief transform <b>data</b> to an image using the palette an dataMin and dataMax given in args
 *  
 *  simple look up between dataMin and dataMax
 *  @see map_on_min_max_val
 */
template<class IN> static void _find_min_max(const IN *aData,int aNbValue,IN &dataMin,IN &dataMax)
{
  dataMax = dataMin = *aData;++aData;
  for(int i = 1;i < aNbValue;++i,++aData)
    {
      if(*aData > dataMax) dataMax = *aData;
      else if(*aData < dataMin) dataMin = *aData;
    }
}

template<class IN> static void _find_minpos_max(const IN *aData,int aNbValue,IN &dataMin,IN &dataMax)
{
  dataMax = *aData;
  if(*aData > 0) dataMin = *aData;
  else dataMin = 0;
  ++aData;
  for(int i = 1;i < aNbValue;++i,++aData)
    {
      if(*aData > dataMax) dataMax = *aData;
      else if(*aData > 0. && (*aData < dataMin || dataMin == 0)) dataMin = *aData;
    }
}
template<class IN> void __attribute__ ((used)) LUT::map(const IN *data,
							unsigned int *anImagePt,
							int column,int line,Palette &aPalette,
							LUT::mapping_meth aMeth,
							IN dataMin,IN dataMax)
{
  unsigned int aCachePalette[0x10000];
  unsigned int *aUsePalette;
  if(sizeof(IN) > sizeof(short))
    aUsePalette = aPalette._dataPalette;
  else
    {
      aUsePalette = aCachePalette;
      int aFmin = int(dataMin),aFmax = int(dataMax);
      if(aFmin < 0)
	{
	  aFmax += -aFmin;
	  aFmin = 0;
	}
      if(aFmax > 0xffff) aFmax = 0xffff;
      aPalette._calcPalette(aUsePalette,aFmin,aFmax,aMeth);
      aMeth = LINEAR;
    }
  _data_map(data,anImagePt,column,line,aMeth,aUsePalette,dataMin,dataMax);
}

template<class IN> static void _data_map(const IN *data,unsigned int *anImagePt,int column,int line,
					 LUT::mapping_meth aMeth,unsigned int *aPalette,
					 IN dataMin,IN dataMax) throw()
{
  static const int mapmin = 0;
  static const int mapmax = 0xffff;

  double A, B;
  double lmin,lmax;
  IN shift = 0;
  if ((dataMax-dataMin) != 0) 
    {
      if (aMeth == LUT::LINEAR)
	{
	  lmin = double(dataMin);
	  lmax = double(dataMax);
	}
      else if(aMeth == LUT::SHIFT_LOG)
	{

	  if(dataMin <= 0)
	    {
	      shift = -dataMin;
	      if(shift < 1e-6) shift += IN(1);
	      dataMax += shift;
	      dataMin += shift;
	    }
	  lmin = log10(dataMin);
	  lmax = log10(dataMax);
	}
      else
	{
	  if(dataMin == 0)
	    dataMin = IN(1);
	  else if(dataMin <= 0)
	    dataMin = IN(1e-6);

	  lmin = log10(dataMin);
	  lmax = log10(dataMax);
	}
      A = (mapmax - mapmin) / (lmax - lmin);
      B = mapmin - ((mapmax - mapmin) * lmin) / (lmax-lmin);
    }
  else 
    {
      A = 1.0;
      B = 0.0;
    }
  if(aMeth == LUT::LINEAR)
    _linear_data_map(data,anImagePt,column,line,aPalette,A,B,dataMin,dataMax);
  else
    {
      if(shift < 1e-6)
	_log_data_map(data,anImagePt,column,line,aPalette,A,B,dataMin,dataMax);
      else
	_log_data_map_shift(data,anImagePt,column,line,aPalette,A,B,dataMin,dataMax,shift);
    }
}

// LINEAR MAPPING FCT

template<class IN> static void _linear_data_map(const IN *data,unsigned int *anImagePt,int column,int line,
						unsigned int *palette,double A,double B,
						IN dataMin,IN dataMax) throw()
{
  int aNbPixel = column * line;
  unsigned int *anImageEnd = anImagePt + aNbPixel;
    for(;anImagePt != anImageEnd;++anImagePt,++data)
    {
       IN val=*data;
       if (val >= dataMax) 
 	*anImagePt = *(palette + 0xffff);
       else if  (val > dataMin)
	 *anImagePt = *(palette + long(A * val + B));
       else  
	 *anImagePt = *palette; 
    }
}

///@brief opti for unsigned short
template<> void _linear_data_map(unsigned short const *data,unsigned int *anImagePt,int column,int line,
					unsigned int *palette,double,double,
					unsigned short dataMin,unsigned short dataMax) throw()
{
  int aNbPixel = column * line;
  unsigned int *anImageEnd = anImagePt + aNbPixel;
  for(;anImagePt != anImageEnd;++anImagePt,++data)
    {
      if(*data >= dataMax)
	*anImagePt = *(palette + dataMax);
      else if(*data > dataMin)
	*anImagePt = *(palette + *data);
      else
	*anImagePt = *palette;
    }
}

///@brief opti for short
template<> void _linear_data_map(const short *data,unsigned int *anImagePt,int column,int line,
					unsigned int *palette,double,double,
					short dataMin,short dataMax) throw()
{
  palette += long(ceil((dataMax - dataMin) / 2.));
  int aNbPixel = column * line;
  unsigned int *anImageEnd = anImagePt + aNbPixel;
  for(;anImagePt != anImageEnd;++anImagePt,++data)
    {
      if(*data >= dataMax)
	*anImagePt = *(palette + dataMax);
      else if(*data > dataMin)
	*anImagePt = *(palette + *data);
      else
	*anImagePt = *palette;
    }
}

///@brief opti for char
template<> void _linear_data_map(const char *data,unsigned int *anImagePt,int column,int line,
					unsigned int *palette,double,double,
					char dataMin,char dataMax) throw()
{
  palette += long(ceil((dataMax - dataMin) / 2.));
  int aNbPixel = column * line;
  unsigned int *anImageEnd = anImagePt + aNbPixel;
  for(;anImagePt != anImageEnd;++anImagePt,++data)
    {
      if(*data >= dataMax)
	*anImagePt = *(palette + dataMax);
      else if(*data > dataMin)
	*anImagePt = *(palette + *data);
      else
	*anImagePt = *palette;
    }
}
///@brief opti for unsigned char
template<> void _linear_data_map(unsigned char const *data,unsigned int *anImagePt,int column,int line,
					unsigned int *palette,double,double,
					unsigned char dataMin,unsigned char dataMax) throw()
{
  int aNbPixel = column * line;
  unsigned int *anImageEnd = anImagePt + aNbPixel;
  for(;anImagePt != anImageEnd;++anImagePt,++data)
    {
      if(*data >= dataMax)
	*anImagePt = *(palette + dataMax);
      else if(*data > dataMin)
	*anImagePt = *(palette + *data);
      else
	*anImagePt = *palette;
    }
}
template<class IN> static void _log_data_map(const IN *data,unsigned int *anImagePt,int column,int line,
					     unsigned int *aPalette,double A,double B,
					     IN dataMin,IN dataMax) throw()
{
  int aNbPixel = column * line;
  register unsigned int *anImageEnd = anImagePt + aNbPixel;
  register unsigned int *palette = aPalette;
  for(;anImagePt != anImageEnd;++anImagePt,++data)
    {
      IN val=*data;
      if (val >= dataMax)
	*anImagePt = *(palette + 0xffff) ;
      else if  (val > dataMin)
	*anImagePt = *(palette + long(A * log10(val) + B));
      else
	*anImagePt = *palette ;
    }
}

template<class IN> static void _log_data_map_shift(const IN *data,unsigned int *anImagePt,int column,int line,
						   unsigned int *aPalette,double A,double B,
						   IN dataMin,IN dataMax,IN shift) throw()
{
  int aNbPixel = column * line;
  register unsigned int *anImageEnd = anImagePt + aNbPixel;
  register unsigned int *palette = aPalette;
  for(;anImagePt != anImageEnd;++anImagePt,++data)
    {
      IN val=*data;
      val += shift;
      if (val >= dataMax)
	*anImagePt = *(palette + 0xffff) ;
      else if  (val > dataMin)
	*anImagePt = *(palette + long(A * log10(val) + B));
      else
	*anImagePt = *palette;
    }
}

static  __attribute__ ((used)) void init_template()
{
#define INIT_MAP(TYPE)							\
  {									\
    TYPE aMin,aMax;							\
    unsigned int *anImagePt = NULL;					\
    LUT::map_on_min_max_val((TYPE*)aBuffer,anImagePt,0,0,palette,LUT::LINEAR,aMin,aMax); \
    LUT::map_on_plus_minus_sigma((TYPE*)aBuffer,anImagePt,0,0,palette,LUT::LINEAR,3.,aMin,aMax); \
  }
  LUT::Palette palette = LUT::Palette();
  char *aBuffer = new char[16];
  INIT_MAP(char);
  INIT_MAP(unsigned char);
  INIT_MAP(short);
  INIT_MAP(unsigned short);
  INIT_MAP(int);
  INIT_MAP(unsigned int);
  INIT_MAP(long);
  INIT_MAP(unsigned long);
  INIT_MAP(float);
  INIT_MAP(double);
  delete [] aBuffer;
}
