#include "pixmaptools_lut.h"
#include <cmath>
#include <iostream>

template<class IN> static void _find_min_max(const IN *aData,int aNbValue,IN &dataMin,IN &dataMax);
template<class IN> static void _find_minpos_max(const IN *aData,int aNbValue,IN &dataMin,IN &dataMax);
template<class IN,class MIN_MAX_TYPE> 
static void _get_average_std(const IN *aData,int aNbValue,
    MIN_MAX_TYPE &anAverage,MIN_MAX_TYPE &aStd);

template<class IN> static void _linear_data_map(const IN *data,
    unsigned int *anImagePt,int column,int line,
    unsigned int *palette,double A,double B,
    IN dataMin,IN dataMax) throw();
template<> void _linear_data_map(unsigned short const *data,
    unsigned int *anImagePt,int column,int line,
    unsigned int *palette,double,double,
    unsigned short dataMin,unsigned short dataMax) throw();
template<> void _linear_data_map(const short *data,
    unsigned int *anImagePt,int column,int line,
    unsigned int *palette,double,double,
    short dataMin,short dataMax) throw();
template<> void _linear_data_map(const char *data,
    unsigned int *anImagePt,int column,int line,
    unsigned int *palette,double,double,
    char dataMin,char dataMax) throw();
template<> void _linear_data_map(unsigned char const *data,
    unsigned int *anImagePt,int column,int line,
    unsigned int *palette,double,double,
    unsigned char dataMin,unsigned char dataMax) throw();
template<class IN> static void _log_data_map(const IN *data,
    unsigned int *anImagePt,int column,int line,
    unsigned int *aPalette,double A,double B,
    IN dataMin,IN dataMax) throw();
template<class IN> static void _log_data_map_shift(const IN *data,
    unsigned int *anImagePt,int column,int line,
    unsigned int *aPalette,double A,double B,
    IN dataMin,IN dataMax,IN shift) throw();

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
    LUT::XServer_Info *Xservinfo = &_config[LUT::Palette::RGBX];
    Xservinfo->pixel_size = 4;
    short aVal = 1;
    Xservinfo->byte_order = *((char*)&aVal) ? LUT::Palette::LSB : LUT::Palette::MSB;
    Xservinfo->rshift = 0,Xservinfo->rbit = 8;

    Xservinfo->gshift = 8,Xservinfo->gbit = 8;

    Xservinfo->bshift = 16,Xservinfo->bbit = 8;

    Xservinfo->ashift = 24,Xservinfo->abit = 8;

    Xservinfo = &_config[LUT::Palette::BGRX];
    Xservinfo->pixel_size = 4;
    Xservinfo->byte_order = *((char*)&aVal) ? LUT::Palette::LSB : LUT::Palette::MSB;

    Xservinfo->ashift = 24,Xservinfo->abit = 8;

    Xservinfo->rshift = 16,Xservinfo->rbit = 8;

    Xservinfo->gshift = 8,Xservinfo->gbit = 8;

    Xservinfo->bshift = 0,Xservinfo->bbit = 8;

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
  double anAverage,aStd;
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
template<class IN,class MIN_MAX_TYPE> 
static void _get_average_std(const IN *aData,int aNbValue,
			     MIN_MAX_TYPE &anAverage,MIN_MAX_TYPE &aStd) 
{
  const IN *aTmpPt = aData;
  double aSum = 0.;
  for(int i = 0;i < aNbValue;++i,++aTmpPt)
    aSum += *aTmpPt;
  double localAverage = aSum / aNbValue;
  anAverage = (MIN_MAX_TYPE)localAverage;
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
  aStd = (MIN_MAX_TYPE) sqrt(aSum);
}

/** @brief calculate the average and the standard deviation
 */
template<class IN,class MIN_MAX_TYPE> 
static void _get_average_std_min_max(const IN *aData,int aNbValue,
				     MIN_MAX_TYPE &anAverage,MIN_MAX_TYPE &aStd,
				     IN &minVal,IN &maxVal) 
{
  const IN *aTmpPt = aData;
  minVal = maxVal = *aData;

  double aSum = 0.;
  for(int i = 0;i < aNbValue;++i,++aTmpPt)
    {
      aSum += *aTmpPt;
      if(*aTmpPt > maxVal)
	maxVal = *aTmpPt;
      else if(*aTmpPt < minVal)
	minVal = *aTmpPt;
    }
  double localAverage = aSum / aNbValue;
  anAverage = (MIN_MAX_TYPE)localAverage;
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
  aStd = (MIN_MAX_TYPE) sqrt(aSum);
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

#define INIT_TEMPLATE(TYPE) \
    template void LUT::map_on_min_max_val(const TYPE *, unsigned int *, int, int, \
                                          LUT::Palette &, LUT::mapping_meth, TYPE &, TYPE &); \
    template void LUT::map_on_plus_minus_sigma(const TYPE *,unsigned int *, int, int, LUT::Palette &, \
					       LUT::mapping_meth, double, TYPE &, TYPE &);

INIT_TEMPLATE(char)
INIT_TEMPLATE(unsigned char)

INIT_TEMPLATE(short)
INIT_TEMPLATE(unsigned short)

INIT_TEMPLATE(int)
INIT_TEMPLATE(unsigned int)

INIT_TEMPLATE(long)
INIT_TEMPLATE(unsigned long)

INIT_TEMPLATE(float)
INIT_TEMPLATE(double)

//inline function for video scaling
inline void _alloc(unsigned char* &lumaPt,int column,int line,int depth)
{
  int aSize = column * line * depth;
  if(posix_memalign((void**)(&lumaPt),16,aSize))
    std::cerr << "Can't allocate memory" << std::endl;
}

inline void _get_linear_factor(float mValue,float MValue,
			       float mapmin,float mapmax,
			       float &A,float &B)
{
  int minValue = int(mValue),maxValue = int(MValue);
  if(maxValue - minValue)
    {
      A = (mapmax - mapmin) / (MValue - mValue);
      B = mapmin - ((mapmax - mapmin) * mValue) / (MValue-mValue);
    }
  else
    {
      A = 1.;
      B = 0.;
    }
}
inline void _rgb555_2_luma(const unsigned char *data,unsigned char *luma,
			   int column,int row)
{
  for(int aSize = column * row;aSize;--aSize,data += 2,++luma)
    {
      unsigned char red = (data[0] & 0x7c) >> 2;
      unsigned char green = ((data[0] & 0x03) << 3)  + ((data[1] & 0xe0) >> 5);
      unsigned char blue = data[1] & 0x1f;
      *luma = ((66 * red + 129 * green + 25 * blue) + 128) >> 8;
    }
}
inline void _rgb555_2_image(const unsigned char *data,
			    unsigned int *anImagePt,
			    int column,int row,
			    float minValue,float maxValue,
			    bool scalingFlag)
{
  if(scalingFlag)
    {
      float A, B;
      _get_linear_factor(minValue,maxValue,0.,219.,A,B);
  
      for(int aSize = column * row;aSize;--aSize,data += 2,++anImagePt)
	{
	  int red = int(((data[0] & 0x7c) >> 2) * A + B);
	  int green = int((((data[0] & 0x03) << 3)  + ((data[1] & 0xe0) >> 5)) * A + B);
	  int blue = int((data[1] & 0x1f) * A + B);

	  if(red > 255) red = 255;
	  else if(red < 0) red = 0;

	  if(green > 255) green = 255;
	  else if(green < 0) green = 0;

	  if(blue > 255) blue = 255;
	  else if(blue < 0) blue = 0;

	  *anImagePt = 0xff000000 | (red << 16) | (green << 8) | blue;
	}
    }
  else
    {
      for(int aSize = column * row;aSize;--aSize,data += 2,++anImagePt)
	{
	  unsigned int red = (data[0] & 0x7c) >> 2;
	  unsigned int green = ((data[0] & 0x03) << 3)  + ((data[1] & 0xe0) >> 5);
	  unsigned int blue = data[1] & 0x1f;
	  
	  *anImagePt = 0xff000000 | (red << 16) | (green << 8) | blue;
	}
    }
}

inline void _rgb565_2_luma(const unsigned char *data,unsigned char *luma,
			   int column,int row)
{
  for(int aSize = column * row;aSize;--aSize,data += 2,++luma)
    {
      unsigned char red = (data[0] & 0xf8) >> 3;
      unsigned char green = ((data[0] & 0x07) << 3)  + ((data[1] & 0xe0) >> 5);
      unsigned char blue = data[1] & 0x1f;
      *luma = ((66 * red + 129 * green + 25 * blue) + 128) >> 8;
    }
}
inline void _rgb565_2_image(const unsigned char *data,
			    unsigned int *anImagePt,
			    int column,int row,
			    float minValue,float maxValue,
			    bool scalingFlag)
{
  if(scalingFlag)
    {
      float A, B;
      _get_linear_factor(minValue,maxValue,0.,219.,A,B);
  
      for(int aSize = column * row;aSize;--aSize,data += 2,++anImagePt)
	{
	  int red = int(((data[0] & 0xf8) >> 3) * A + B);
	  int green = int((((data[0] & 0x07) << 3)  + ((data[1] & 0xe0) >> 5)) * A + B);
	  int blue = int((data[1] & 0x1f) * A + B);

	  if(red > 255) red = 255;
	  else if(red < 0) red = 0;

	  if(green > 255) green = 255;
	  else if(green < 0) green = 0;

	  if(blue > 255) blue = 255;
	  else if(blue < 0) blue = 0;

	  *anImagePt = 0xff000000 | (red << 16) | (green << 8) | blue;
	}
    }
  else
    {
      for(int aSize = column * row;aSize;--aSize,data += 2,++anImagePt)
	{
	  unsigned int red = (data[0] & 0xf8) >> 3;
	  unsigned int green = ((data[0] & 0x07) << 3)  + ((data[1] & 0xe0) >> 5);
	  unsigned int blue = data[1] & 0x1f;
	  
	  *anImagePt = 0xff000000 | (red << 16) | (green << 8) | blue;
	}
    }
}
inline void _rgb_2_luma(const unsigned char *data,unsigned char *luma,
			int column,int row,int bandes)
{
  for(int aSize = column * row;aSize;--aSize,data += bandes,++luma)
    *luma = ((66 * data[0] + 129 * data[1] + 25 * data[2]) + 128) >> 8;
}

inline void _rgb_2_image(const unsigned char *data,
			 unsigned int *anImagePt,
			 int column,int row,
			 float mValue,float MValue,
			 int bandes,
			 bool scalingFlag)
{
  if(scalingFlag)
    {
      float A,B;
      _get_linear_factor(mValue,MValue,0.,219.,A,B);
      for(int aSize = column * row;aSize;--aSize,data += bandes,++anImagePt)
	{
	  int red = int(data[0] * A + B);
	  int green = int(data[1] * A + B);
	  int blue = int(data[2] * A + B);

	  if(red > 255) red = 255;
	  else if(red < 0) red = 0;

	  if(green > 255) green = 255;
	  else if(green < 0) green = 0;

	  if(blue > 255) blue = 255;
	  else if(blue < 0) blue = 0;

	  *anImagePt = 0xff000000 | (red << 16) | (green << 8) | blue;
	}
    }
  else
    {
      for(int aSize = column * row;aSize;--aSize,data += bandes,++anImagePt)
	*anImagePt = 0xff000000 | (data[0] << 16) | (data[1] << 16) | data[2] << 8;
    }
}
inline void _bgr_2_luma(const unsigned char *data,unsigned char *luma,
			int column,int row,int bandes)
{
  for(int aSize = column * row;aSize;--aSize,data += bandes,++luma)
    *luma = ((25 * data[0] + 129 * data[1] + 66 * data[2]) + 128) >> 8;
}

inline void _bgr_2_image(const unsigned char *data,
			 unsigned int *anImagePt,
			 int column,int row,
			 float mValue,float MValue,
			 int bandes,
			 bool scalingFlag)
{
  if(scalingFlag)
    {
      float A,B;
      _get_linear_factor(mValue,MValue,0.,219.,A,B);
      for(int aSize = column * row;aSize;--aSize,data += bandes,++anImagePt)
	{
	  int red = int(data[0] * A + B);
	  int green = int(data[1] * A + B);
	  int blue = int(data[2] * A + B);

	  if(red > 255) red = 255;
	  else if(red < 0) red = 0;

	  if(green > 255) green = 255;
	  else if(green < 0) green = 0;

	  if(blue > 255) blue = 255;
	  else if(blue < 0) blue = 0;

	  *anImagePt = 0xff000000 | (red << 16) | (green << 8) | blue;
	}
    }
  else
    {
      for(int aSize = column * row;aSize;--aSize,data += bandes,++anImagePt)
	*anImagePt = 0xff000000 | (data[3] << 16) | (data[1] << 8) | data[0];
    }
}

template<class IN>
inline void _bayer_2_luma(const IN* bayer0,IN* luma,
			  int column,int row,int blue,int start_with_green)
{
  int luma_step = column * sizeof(IN);
  int bayer_step = column;
  IN *luma0 = (IN*)luma;
  memset( luma0, 0, luma_step);
  memset( luma0 + (row - 1)*column, 0, luma_step);
  luma0 += column + 1;
  row -= 2;
  column -= 2;

  for( ; row > 0;--row,bayer0 += bayer_step, luma0 += bayer_step )
    {
      int t0, t1;
      const IN* bayer = bayer0;
      IN* dst = luma0;
      const IN* bayer_end = bayer + column;

      dst[-1] = 0;
      if(column <= 0 )
	continue;
      dst[column] = 0;

      if( start_with_green )
        {
	  t0 = (bayer[1] + bayer[bayer_step*2+1] + 1) >> 1;
	  t1 = (bayer[bayer_step] + bayer[bayer_step+2] + 1) >> 1;
	  if(blue < -1)
	    *dst = (bayer[bayer_step+1] * 150 + t0 * 29 + t1 * 76) >> 8;
	  else
	    *dst = (bayer[bayer_step+1] * 150 + t1 * 29 + t0 * 76) >> 8;
	  ++bayer;
	  ++dst;
        }

      if( blue > 0 )
        {
	  for( ; bayer <= bayer_end - 2; bayer += 2)
            {
	      t0 = (bayer[0] + bayer[2] + bayer[bayer_step*2] +
		    bayer[bayer_step*2+2] + 2) >> 2;
	      t1 = (bayer[1] + bayer[bayer_step] +
		    bayer[bayer_step+2] + bayer[bayer_step*2+1]+2) >> 2;
	      *dst = (t0 * 76 + t1 * 150 + bayer[bayer_step+1] * 29) >> 8;
	      ++dst;

	      t0 = (bayer[2] + bayer[bayer_step*2+2] + 1) >> 1;
	      t1 = (bayer[bayer_step+1] + bayer[bayer_step+3] + 1) >> 1;
	      *dst = (t0 * 76 + bayer[bayer_step+2] * 150 + t1 * 29) >> 8;
	      ++dst;
            }
        }
      else
        {
	  for( ; bayer <= bayer_end - 2; bayer += 2)
            {
	      t0 = (bayer[0] + bayer[2] + bayer[bayer_step*2] +
		    bayer[bayer_step*2+2] + 2) >> 2;
	      t1 = (bayer[1] + bayer[bayer_step] +
		    bayer[bayer_step+2] + bayer[bayer_step*2+1]+2) >> 2;
	      *dst = (t0 * 29 + t1 * 150 + bayer[bayer_step+1] * 76) >> 8;
	      ++dst;

	      t0 = (bayer[2] + bayer[bayer_step*2+2] + 1) >> 1;
	      t1 = (bayer[bayer_step+1] + bayer[bayer_step+3] + 1) >> 1;
	      *dst = (t0 * 29 + bayer[bayer_step+2] * 150 + t1 * 76) >> 8;
	      ++dst;
            }
        }

      if( bayer < bayer_end )
        {
	  t0 = (bayer[0] + bayer[2] + bayer[bayer_step*2] +
		bayer[bayer_step*2+2] + 2) >> 2;
	  t1 = (bayer[1] + bayer[bayer_step] +
		bayer[bayer_step+2] + bayer[bayer_step*2+1]+2) >> 2;
	  if(blue > 0)
	    *dst = (t0 * 76 + t1 * 150 +  bayer[bayer_step+1] * 29) >> 8;
	  else
	    *dst = (t0 * 29 + t1 * 150 +  bayer[bayer_step+1] * 76) >> 8;
	  ++bayer;
	  ++dst;
        }

      blue = -blue;
      start_with_green = !start_with_green;
    }
}

template<class IN>
inline void _bayer_rg_2_luma(const IN* bayer0,IN* luma,
			     int column,int row)
{
  _bayer_2_luma(bayer0,luma,column,row,1,0);
}

template<class IN>
inline void _bayer_bg_2_luma(const IN* bayer0,IN* luma,
			     int column,int row)
{
  _bayer_2_luma(bayer0,luma,column,row,-1,0);
}

#define SCALE()					\
  if(active)					\
    {						\
      int T0,T1,T2;				\
      T0 = t0 * A + B;				\
      T1 = t1 * A + B;				\
      T2 = t2 * A + B;				\
      if(T0 > 255 || T1 > 255 || T2 > 255)	\
	{					\
	  if(T0 > T1 && T0 > T2)		\
	    {					\
	      double nA = (255. - B) / t0;	\
	      T0 = 255;				\
	      T1 = t1 * nA + B;			\
	      T2 = t2 * nA + B;			\
	    }					\
	  else if(T1 > T2)			\
	    {					\
	      double nA = (255. - B) / t1;	\
	      T1 = 255;				\
	      T0 = t0 * nA + B;			\
	      T2 = t2 * nA + B;			\
	    }					\
	  else					\
	    {					\
	      double nA = (255. - B) / t2;	\
	      T2 = 255;				\
	      T0 = t0 * nA + B;			\
	      T1 = t1 * nA + B;			\
	    }					\
	}					\
      if(T0 < 0) T0 = 0;			\
      if(T1 < 0) T1 = 0;			\
      if(T2 < 0) T2 = 0;			\
      t0 = T0,t1 = T1,t2 = T2;			\
    }

/** @brief interpolation taken from opencv (icvBayer2BGR_8u_C1C3R in cvcolor.cpp)
 */
template<class IN>
 void _bayer_quick_interpol(const IN *bayer0,
			    void *anImagePt,int column,int row,
			    bool active,int blue,int start_with_green,
			    float A = -1.,float B = -.1)
{
  unsigned char ALPHA = 255;
  int dst_step = 4 * column;
  int bayer_step = column;
  unsigned char *dst0 = (unsigned char*)anImagePt;
  memset( dst0, 0, dst_step);
  memset( dst0 + (row - 1)*dst_step, 0, dst_step);
  dst0 += dst_step + 4 + 1;
  row -= 2;
  column -= 2;

  for( ; row > 0;--row,bayer0 += bayer_step, dst0 += dst_step )
    {
      int t0, t1, t2;
      const IN* bayer = bayer0;
      unsigned char* dst = dst0;
      const IN* bayer_end = bayer + column;

      dst[2] = ALPHA;
      dst[-5] = dst[-4] = dst[-3] = dst[dst_step-1] =
	dst[dst_step] = dst[dst_step+1] = 0;
      dst[dst_step+2] = ALPHA;

      if(column <= 0 )
	continue;

      if( start_with_green )
        {
	  t0 = (bayer[1] + bayer[bayer_step*2+1] + 1) >> 1;
	  t1 = (bayer[bayer_step] + bayer[bayer_step+2] + 1) >> 1;
	  t2 = bayer[bayer_step+1];
	  SCALE();

	  dst[blue] = uchar(t0);
	  dst[0] = uchar(t2);
	  dst[-blue] = uchar(t1);
	  dst[2] = ALPHA;
	  bayer++;
	  dst += 4;
        }

      if( blue > 0 )
        {
	  for( ; bayer <= bayer_end - 2; bayer += 2, dst += 8 )
            {
	      t0 = (bayer[0] + bayer[2] + bayer[bayer_step*2] +
		    bayer[bayer_step*2+2] + 2) >> 2;
	      t1 = (bayer[1] + bayer[bayer_step] +
		    bayer[bayer_step+2] + bayer[bayer_step*2+1]+2) >> 2;
	      t2 = uchar(bayer[bayer_step+1]);
	      SCALE();

	      dst[-1] = uchar(t2); //blue
	      dst[0] = uchar(t1); //green
	      dst[1] = uchar(t0); //red
	      dst[2] = ALPHA;

	      t0 = (bayer[2] + bayer[bayer_step*2+2] + 1) >> 1;
	      t1 = (bayer[bayer_step+1] + bayer[bayer_step+3] + 1) >> 1;
	      t2 = bayer[bayer_step+2];
	      SCALE();

	      dst[3] = uchar(t1);
	      dst[4] = uchar(t2);
	      dst[5] = uchar(t0);
	      dst[6] = ALPHA;
            }
        }
      else
        {
	  for( ; bayer <= bayer_end - 2; bayer += 2, dst += 8 )
            {
	      t0 = (bayer[0] + bayer[2] + bayer[bayer_step*2] +
		    bayer[bayer_step*2+2] + 2) >> 2;
	      t1 = (bayer[1] + bayer[bayer_step] +
		    bayer[bayer_step+2] + bayer[bayer_step*2+1]+2) >> 2;
	      t2 = bayer[bayer_step+1];
	      SCALE();

	      dst[-1] = uchar(t0);
	      dst[0] = uchar(t1);
	      dst[1] = uchar(t2);
	      dst[2] = ALPHA;

	      t0 = (bayer[2] + bayer[bayer_step*2+2] + 1) >> 1;
	      t1 = (bayer[bayer_step+1] + bayer[bayer_step+3] + 1) >> 1;
	      t2 = bayer[bayer_step+2];
	      SCALE();

	      dst[3] = uchar(t0);
	      dst[4] = uchar(t2);
	      dst[5] = uchar(t1);
	      dst[6] = ALPHA;
            }
        }

      if( bayer < bayer_end )
        {
	  t0 = (bayer[0] + bayer[2] + bayer[bayer_step*2] +
		bayer[bayer_step*2+2] + 2) >> 2;
	  t1 = (bayer[1] + bayer[bayer_step] +
		bayer[bayer_step+2] + bayer[bayer_step*2+1]+2) >> 2;
	  t2 = bayer[bayer_step+1];
	  SCALE();

	  dst[blue] = uchar(t0);
	  dst[0] = uchar(t1);
	  dst[-blue] = uchar(t2);
	  dst[2] = ALPHA;
	  bayer++;
	  dst += 4;
        }

      blue = -blue;
      start_with_green = !start_with_green;
    }
}
template<class IN>
inline void _bayer_rg_quick_interpol(const IN *bayer0,
				     void *anImagePt,int column,int row,
				     bool active,float A = -1.,float B = -.1)
{
  _bayer_quick_interpol(bayer0,anImagePt,column,row,active,1,0,A,B);
}

template<class IN>
inline void _bayer_bg_quick_interpol(const IN *bayer0,
				     void *anImagePt,int column,int row,
				     bool active,float A = -1.,float B = -.1)
{
  _bayer_quick_interpol(bayer0,anImagePt,column,row,active,-1,0,A,B);
}


template<class IN>
inline void _bayer_rg_2_image(const IN *bayer0,
			      unsigned int *anImagePt,int column,int row,
			      float minValue,float maxValue,
			      LUT::Scaling::mode aMode)

{
  if(aMode == LUT::Scaling::UNACTIVE)
    {
      /* when need to shrink data
	 shitty fallback should be changed */
      if(sizeof(IN) > 1)
	{
	  IN mValue,MValue;
	  _find_min_max(bayer0,column * row,mValue,MValue);
	  int n,nbshift;
	  for(n = 1,nbshift = 0;n < MValue;n <<= 1,++nbshift);
	  nbshift -= 8;
	  uchar *bayer;
	  _alloc(bayer,column,row,1);
	  uchar *endbayer = bayer + (column * row);
	  for(uchar *pt = bayer;pt != endbayer;++pt,++bayer0)
	    *pt = uchar(*bayer0 >> nbshift);
	  _bayer_rg_quick_interpol((uchar*)bayer,anImagePt,column,row,false);
	  free(bayer);
	}
      else
	_bayer_rg_quick_interpol(bayer0,anImagePt,column,row,false);
    }
  else
    {
      float A,B;
      _get_linear_factor(minValue,maxValue,0.,255.,A,B);
      if(aMode == LUT::Scaling::QUICK)
	_bayer_rg_quick_interpol(bayer0,anImagePt,column,row,true,A,B);
      else			// @todo should be change to an other algo!!!!
	_bayer_rg_quick_interpol(bayer0,anImagePt,column,row,true,A,B);
    }
}

template<class IN>
inline void _bayer_bg_2_image(const IN *bayer0,
			      unsigned int *anImagePt,int column,int row,
			      float minValue,float maxValue,
			      LUT::Scaling::mode aMode)

{
  if(aMode == LUT::Scaling::UNACTIVE)
    {
      /* when need to shrink data
	 shitty fallback should be changed */
      if(sizeof(IN) > 1)
	{
	  IN mValue,MValue;
	  _find_min_max(bayer0,column * row,mValue,MValue);
	  int n,nbshift;
	  for(n = 1,nbshift = 0;n < MValue;n <<= 1,++nbshift);
	  nbshift -= 8;
	  uchar *bayer;
	  _alloc(bayer,column,row,1);
	  uchar *endbayer = bayer + (column * row);
	  for(uchar *pt = bayer;pt != endbayer;++pt,++bayer0)
	    *pt = uchar(*bayer0 >> nbshift);
	  _bayer_bg_quick_interpol((uchar*)bayer,anImagePt,column,row,false);
	  free(bayer);
	}
      else
	_bayer_bg_quick_interpol(bayer0,anImagePt,column,row,false);
    }
  else
    {
      float A,B;
      _get_linear_factor(minValue,maxValue,0.,255.,A,B);
      if(aMode == LUT::Scaling::QUICK)
	_bayer_bg_quick_interpol(bayer0,anImagePt,column,row,true,A,B);
      else			// @todo should be change to an other algo!!!!
	_bayer_bg_quick_interpol(bayer0,anImagePt,column,row,true,A,B);
    }
}

inline void _i420_2_image(const unsigned char* data,
			 unsigned int *anImagePt,
			 int column,int row,
			 float minValue,float maxValue,
			 bool scalingFlag)
{
#define _I420_YUV_SCALING_BRGA(yPt,imagePt)		\
  y = A * *yPt + B;					\
  if(y > 255) y = 255;					\
  else if(y < 0) y = 0;					\
							\
  red = y + redChro;					\
  if(red > 255) red = 255;				\
  else if(red < 0) red = 0;				\
							\
  green = y + greenChro;				\
  if(green  > 255) green = 255;				\
  else if(green < 0) green = 0;				\
							\
  blue = y + blueChro;					\
  if(blue > 255) blue = 255;				\
  else if(blue < 0) blue = 0;				     \
							     \
  *imagePt = 0xff000000 | (red << 16) | (green << 8) | blue; \
  ++imagePt,++yPt; 
  
#define _I420_YUV_BRGA(yPt,imagePt)			\
  red = *yPt + redChro;					\
  if(red > 255) red = 255;				\
  else if(red < 0) red = 0;				\
							\
  green = *yPt + greenChro;				\
  if(green  > 255) green = 255;				\
  else if(green < 0) green = 0;				\
							\
  blue = *yPt + blueChro;				\
  if(blue > 255) blue = 255;				\
  else if(blue < 0) blue = 0;				     \
							     \
  *imagePt = 0xff000000 | (red << 16) | (green << 8) | blue; \
  ++imagePt,++yPt; 

  
  int aNbPixel = column * row;
  const unsigned char *U = data + aNbPixel;
  const unsigned char *V = U + (aNbPixel >> 2);
  const unsigned char *Yline1 = data;
  const unsigned char *Yline2 = data + column;
  unsigned int *anImageLine2Pt = anImagePt + column;
  if(scalingFlag)
    {
      float A, B;
      if(maxValue - minValue)
	{
	  A = (235 - 16) / (maxValue - minValue);
	  B = 16 - ((235 - 16) * minValue) / (maxValue - minValue);
	}
      else
	{
	  A = 1.;
	  B = 0.;
	}
      for(int rowid = 0;rowid < row;rowid += 2)
	{
	  for(int columnid = 0;columnid < column;
	      columnid += 2,++V,++U)
	    {
	      int redChro = 1.403f * (*V -128);
	      int greenChro = -0.714f * (*V - 128) -0.344f * (*U - 128);
	      int blueChro = 1.773f * (*U - 128);
	      int y,red,green,blue;
	      _I420_YUV_SCALING_BRGA(Yline1,anImagePt);
	      _I420_YUV_SCALING_BRGA(Yline1,anImagePt);
	      _I420_YUV_SCALING_BRGA(Yline2,anImageLine2Pt);
	      _I420_YUV_SCALING_BRGA(Yline2,anImageLine2Pt);
	    }
	  Yline1 = Yline2; Yline2 = Yline1 + column;
	  anImagePt = anImageLine2Pt; anImageLine2Pt = anImagePt + column;
	}
    }
  else
    {
      for(int rowid = 0;rowid < row;rowid += 2)
	{
	  for(int columnid = 0;columnid < column;
	      columnid += 2,++V,++U)
	    {
	      int redChro = 1.403f * (*V -128);
	      int greenChro = -0.714f * (*V - 128) -0.344f * (*U - 128);
	      int blueChro = 1.773f * (*U - 128);
	      int red,green,blue;
	      _I420_YUV_BRGA(Yline1,anImagePt);
	      _I420_YUV_BRGA(Yline1,anImagePt);
	      _I420_YUV_BRGA(Yline2,anImageLine2Pt);
	      _I420_YUV_BRGA(Yline2,anImageLine2Pt);
	    }
	  Yline1 = Yline2; Yline2 = Yline1 + column;
	  anImagePt = anImageLine2Pt; anImageLine2Pt = anImagePt + column;
	}
    }
}


inline void _yuv422_packed_2_image(const unsigned char* data,
                                   unsigned int *anImagePt,
                                   int column,int row,
                                   float minValue,float maxValue,
                                   bool scalingFlag)
{
#define _YUV422_PACKED_BRGA(y, imagePt)                         \
    red = y + redChro;                                          \
    if(red > 255) red = 255;                                    \
    else if(red < 0) red = 0;                                   \
                                                                \
    green = y + greenChro;                                      \
    if(green  > 255) green = 255;                               \
    else if(green < 0) green = 0;                               \
                                                                \
    blue = y + blueChro;                                        \
    if(blue > 255) blue = 255;                                  \
    else if(blue < 0) blue = 0;                                 \
                                                                \
    *imagePt = 0xff000000 | (red << 16) | (green << 8) | blue;

    if(scalingFlag){
        std::cout << "TODO : _yuv422_packed_2_image scalingFlag=1  minValue=" << minValue << "maxValue=" << maxValue;
    }
    else{
        long nb_iter = column * row / 2;
        if(nb_iter > 0)
            --nb_iter;

        for(const unsigned char *src = data ; nb_iter ; --nb_iter,src += 4) {
            unsigned char U  = src[0];
            unsigned char y0 = src[1];
            unsigned char V  = src[2];
            unsigned char y1 = src[3];

            int redChro   =  1.403f * (V-128);
            int greenChro = -0.714f * (V-128) -0.344f * (U-128);
            int blueChro  =  1.773f * (U-128);

            int red, green, blue;
            _YUV422_PACKED_BRGA(y0, anImagePt); ++anImagePt;
            _YUV422_PACKED_BRGA(y1, anImagePt); ++anImagePt;
        }
    }
}

inline unsigned char* _calculate_luma(const unsigned char *data,
                                      int column,int row,LUT::Scaling::image_type aType)
{
  unsigned char *lumaPt = NULL;
  //creation of luma data if need
  switch(aType)
    {
    case LUT::Scaling::RGB555:
      _alloc(lumaPt,column,row,1);
      _rgb555_2_luma(data,lumaPt,column,row);
      break;
    case LUT::Scaling::RGB565:
      _alloc(lumaPt,column,row,1);
      _rgb565_2_luma(data,lumaPt,column,row);
      break;
    case LUT::Scaling::RGB24:
      _alloc(lumaPt,column,row,1);
      _rgb_2_luma(data,lumaPt,column,row,3);
      break;
    case LUT::Scaling::RGB32:
      _alloc(lumaPt,column,row,1);
      _rgb_2_luma(data,lumaPt,column,row,4);
      break;
    case LUT::Scaling::BGR24:
      _alloc(lumaPt,column,row,1);
      _bgr_2_luma(data,lumaPt,column,row,3);
      break;
    case LUT::Scaling::BGR32:
      _alloc(lumaPt,column,row,1);
      _bgr_2_luma(data,lumaPt,column,row,4);
      break;
    case LUT::Scaling::BAYER_RG8:
      _alloc(lumaPt,column,row,1);
      _bayer_rg_2_luma(data,lumaPt,column,row);
      break;
    case LUT::Scaling::BAYER_RG16:
      _alloc(lumaPt,column,row,2);
      _bayer_rg_2_luma((unsigned short*)data,(unsigned short*)lumaPt,column,row);
      break;
    case LUT::Scaling::BAYER_BG8:
      _alloc(lumaPt,column,row,1);
      _bayer_bg_2_luma(data,lumaPt,column,row);
      break;
    case LUT::Scaling::BAYER_BG16:
      _alloc(lumaPt,column,row,2);
      _bayer_bg_2_luma((unsigned short*)data,(unsigned short*)lumaPt,column,row);
      break;
    default:
      break;
    }
  return lumaPt;
}
  //Local lock
class _Lock
{
public:
  _Lock(pthread_mutex_t *aMutex,bool lockFlag = true) :
    _mutex(aMutex),_locked(false)
  {
    if(lockFlag)
      lock();
  }
  ~_Lock() {unlock();}

  inline void lock() 
  {
    if(!_locked)
      while(pthread_mutex_lock(_mutex));
    _locked = true;
  }
  
  inline void unlock()
  {
    if(_locked)
      {
	_locked = false;
	pthread_mutex_unlock(_mutex);
      }
  }
private:
  pthread_mutex_t *_mutex;
  bool		  _locked;
};
  //Luma class
struct LUT::Scaling::luma
{
  luma() : 
    _type(LUT::Scaling::UNDEF),
    _palette(LUT::Palette::GREYSCALE)
  {
    _palette_mapping_meth = LUT::LINEAR;
  }

  ~luma()
  {
   
  }
  
	       
  LUT::Scaling::image_type _type;

  LUT::mapping_meth	   _palette_mapping_meth;
  LUT::Palette		   _palette;
};


  //Scaling class
LUT::Scaling::Scaling() : 
  _minValue(-1.),_maxValue(-1.),
  _mode(UNACTIVE)
{
  pthread_mutex_init(&_lock,NULL);
  _Luma = new LUT::Scaling::luma();
}

LUT::Scaling::~Scaling()
{
  pthread_mutex_destroy(&_lock);
}

void LUT::Scaling::current_type(Scaling::image_type &aType) const
{ 
  _Lock aLock(&_lock);
  aType = _Luma->_type;
}

void LUT::Scaling::min_max_mapping(double &minVal,double &maxVal) const
{
  _Lock aLock(&_lock);
  minVal = _minValue, maxVal = _maxValue;
}

void LUT::Scaling::set_custom_mapping(double minVal,double maxVal)
{
  _Lock aLock(&_lock);
  _minValue = minVal,_maxValue = maxVal;
  _Luma->_type = UNDEF;
  if(_mode == UNACTIVE) _mode = QUICK;
}

void LUT::Scaling::get_mode(LUT::Scaling::mode &aMode) const
{
  _Lock aLock(&_lock);
  aMode = _mode;
}

void LUT::Scaling::set_mode(LUT::Scaling::mode aMode)
{
  _Lock aLock(&_lock);
  _mode = aMode;
}

void LUT::Scaling::fill_palette(LUT::Palette::palette_type aType)
{
  _Luma->_palette.fillPalette(aType);
}

void LUT::Scaling::set_palette_mapping_meth(LUT::mapping_meth meth)
{
  _Luma->_palette_mapping_meth = meth;
}

void LUT::Scaling::autoscale_min_max(const unsigned char *data,
				     int column,int row,image_type aType)
{
  unsigned char *lumaPt = _calculate_luma(data,column,row,aType);
  //find min max
  int minVal = -1,maxVal = -1;
  switch(aType)
    {
    case LUT::Scaling::YUV411:
    case LUT::Scaling::YUV422:
    case LUT::Scaling::YUV444:
    case LUT::Scaling::I420: 
    case LUT::Scaling::Y8:
      {
	unsigned char localCharMin,localCharMax;
	_find_min_max(data,column * row,localCharMin,localCharMax);
	minVal = localCharMin,maxVal = localCharMax;
      }
      break;
    case LUT::Scaling::Y16:
      {
	unsigned short localShortMin,localShortMax;
	_find_min_max((unsigned short*)data,column * row,localShortMin,localShortMax);
	minVal = localShortMin,maxVal = localShortMax;
      }
      break;
    case LUT::Scaling::Y32:
      {
	unsigned int localIntMin,localIntMax;
	_find_min_max((unsigned int*)data,column * row,localIntMin,localIntMax);
	minVal = localIntMin,maxVal = localIntMax;
      }
      break;
    case LUT::Scaling::Y64:
      {
	unsigned long long localLongLongMin,localLongLongMax;
	_find_min_max((unsigned long long*)data,column * row,localLongLongMin,localLongLongMax);
	minVal = localLongLongMin,maxVal = localLongLongMax;
      }
      break;
    case LUT::Scaling::RGB555:
    case LUT::Scaling::RGB565:
    case LUT::Scaling::RGB24:
    case LUT::Scaling::RGB32:
    case LUT::Scaling::BGR24:
    case LUT::Scaling::BGR32:
    case LUT::Scaling::BAYER_RG8:
    case LUT::Scaling::BAYER_BG8:
      {
	unsigned char localCharMin,localCharMax;
	_find_min_max(lumaPt,column * row,localCharMin,localCharMax);
	minVal = localCharMin,maxVal = localCharMax;
      }
      break;
    case LUT::Scaling::BAYER_RG16:
    case LUT::Scaling::BAYER_BG16:
      {
	unsigned short localMin,localMax;
	_find_min_max((unsigned short*)lumaPt,column * row,localMin,localMax);
	minVal = int(localMin),maxVal = int(localMax);
      }
      break;
    default:
      break;
    }

  if(lumaPt) free(lumaPt);

  _Lock aLock(&_lock);
  _minValue = minVal,_maxValue = maxVal;
  if(_mode == LUT::Scaling::UNACTIVE)
    _mode = LUT::Scaling::QUICK;
}

void LUT::Scaling::autoscale_plus_minus_sigma(const unsigned char *data,int column,int row,
					      image_type aType,
					      double aSigmaFactor)
{
  unsigned char *lumaPt = _calculate_luma(data,column,row,aType);
  double meanValue = -1.,std = 1.;
  double minVal = 0.,maxVal = 0.;
  switch(aType)
    {
    case LUT::Scaling::YUV411:
    case LUT::Scaling::YUV422:
    case LUT::Scaling::YUV444:
    case LUT::Scaling::I420: 
    case LUT::Scaling::Y8:
      {
	uchar localMin,localMax;
	_get_average_std_min_max(data,column * row,meanValue,std,localMin,localMax);
	minVal = localMin,maxVal = localMax;
      }
      break;
    case LUT::Scaling::Y16:
      {
	unsigned short localMin,localMax;
	_get_average_std_min_max((unsigned short*)data,column * row,meanValue,std,localMin,localMax);
	minVal = localMin,maxVal = localMax;
      }
      break;

    case LUT::Scaling::RGB555:
    case LUT::Scaling::RGB565:
    case LUT::Scaling::RGB24:
    case LUT::Scaling::RGB32:
    case LUT::Scaling::BGR24:
    case LUT::Scaling::BGR32:
    case LUT::Scaling::BAYER_RG8:
    case LUT::Scaling::BAYER_BG8:
      {
	uchar localMin,localMax;
	_get_average_std_min_max(lumaPt,column * row,meanValue,std,localMin,localMax);
	minVal = localMin,maxVal = localMax;
      }
      break;
    case LUT::Scaling::BAYER_RG16:
    case LUT::Scaling::BAYER_BG16:
      {
	unsigned short localMin,localMax;
	_get_average_std_min_max((unsigned short*)lumaPt,column * row,meanValue,std,localMin,localMax);
	minVal = localMin,maxVal = localMax;
      }
      break;
    default:
      break;
    }
  if(lumaPt) free(lumaPt);
    
  _Lock aLock(&_lock);
  _minValue = meanValue - aSigmaFactor * std,_maxValue = meanValue + aSigmaFactor * std;
  if(_minValue < minVal) _minValue = minVal;
  if(_maxValue > maxVal) _maxValue = maxVal;
  if(_mode == LUT::Scaling::UNACTIVE)
    _mode = LUT::Scaling::QUICK;
}

void LUT::Scaling::_get_minmax_and_mode(double &minVal,double &maxVal,
					mode &aMode)
{
  _Lock aLock(&_lock);
  minVal = _minValue,maxVal = _maxValue;
  aMode = _mode;
}
/** @brief tranform raw video image to BGRA image.
 *  Scaling instance has to be set with the same type of data.
 *  @see Scaling::autoscale_min_max
 *  @see Scaling::autoscale_plus_minus_sigma
 *  @see Scaling::set_custom_mapping
 */
bool LUT::raw_video_2_image(const unsigned char *data,unsigned int *anImagePt,
			    int column,int row,
			    LUT::Scaling::image_type anImageType,Scaling &aScaling)
{
  double minValue,maxValue;
  LUT::Scaling::mode aMode;
  aScaling._get_minmax_and_mode(minValue,maxValue,aMode);
  if(minValue < 0) minValue = 0;

  switch(anImageType)
    {
    case LUT::Scaling::Y8:
      if(aMode == LUT::Scaling::UNACTIVE)
	{
	  for(int aNbPixel = column * row;aNbPixel;--aNbPixel,++data,++anImagePt)
	    *anImagePt = 0xff000000 | (*data << 16) | (*data << 8) | *data;
	}
      else
	LUT::map(data,anImagePt,column,row,aScaling._Luma->_palette,
		 aScaling._Luma->_palette_mapping_meth,uchar(minValue),uchar(maxValue));
      break;
    case LUT::Scaling::Y16:
      if(aMode == LUT::Scaling::UNACTIVE)
	{
	  const unsigned short *pixelPt = (const unsigned short*)data;
	  for(int aNbPixel = column * row;aNbPixel;--aNbPixel,++pixelPt,++anImagePt)
	    {
	      int aValue = *pixelPt >> 8;
	      *anImagePt = 0xff000000 | (aValue << 16) | (aValue << 8) | aValue;
	    }
	}
      else
	LUT::map((unsigned short*)data,anImagePt,column,row,aScaling._Luma->_palette,
		 aScaling._Luma->_palette_mapping_meth,(unsigned short)minValue,(unsigned short)maxValue);
      break;
    case LUT::Scaling::I420:
      if(aMode == LUT::Scaling::COLOR_MAPPED)
	LUT::map(data,anImagePt,column,row,aScaling._Luma->_palette,
		 aScaling._Luma->_palette_mapping_meth,uchar(minValue),uchar(maxValue));
      else
	_i420_2_image(data,anImagePt,column,row,minValue,maxValue,
		      aMode != LUT::Scaling::UNACTIVE);
      break;
    case LUT::Scaling::YUV422PACKED:
      if(aMode == LUT::Scaling::COLOR_MAPPED)
	{
	  unsigned char* data_y = new unsigned char[column * row];
	  const unsigned char* src = data + 1;
	  for(int i = 0;i < column * row;++i,src += 2,++data_y){
              *data_y = *src;
          }
	  LUT::map(data_y,anImagePt,column,row,aScaling._Luma->_palette,
		   aScaling._Luma->_palette_mapping_meth,uchar(minValue),uchar(maxValue));
	  delete data_y;
	}
      else
	_yuv422_packed_2_image(data, anImagePt, column, row, minValue, maxValue,
		      aMode != LUT::Scaling::UNACTIVE);
      break;
    case LUT::Scaling::RGB555:
      _rgb555_2_image(data,
		      anImagePt,column,row,minValue,maxValue,
		      aMode != LUT::Scaling::UNACTIVE);
      break;
    case LUT::Scaling::RGB565: 
      _rgb565_2_image(data,anImagePt,column,row,minValue,maxValue,
		      aMode != LUT::Scaling::UNACTIVE);
      break;
    case LUT::Scaling::RGB24:
      _rgb_2_image(data,anImagePt,column,row,minValue,maxValue,3,
		   aMode != LUT::Scaling::UNACTIVE);
      break;
    case LUT::Scaling::RGB32:
      _rgb_2_image(data,anImagePt,column,row,minValue,maxValue,4,
		   aMode != LUT::Scaling::UNACTIVE);
      break;
    case LUT::Scaling::BGR24:
      _bgr_2_image(data,anImagePt,column,row,minValue,maxValue,3,
		   aMode != LUT::Scaling::UNACTIVE);
      break;
    case LUT::Scaling::BGR32: 
      _bgr_2_image(data,anImagePt,column,row,minValue,maxValue,4,
		   aMode != LUT::Scaling::UNACTIVE);
      break;
    case LUT::Scaling::BAYER_RG8:
      if(aMode == LUT::Scaling::COLOR_MAPPED)
	{
	  unsigned char* luma = _calculate_luma(data,column,row,anImageType);
	  if(minValue < 0) 
	    minValue = 0;
	  LUT::map(luma,anImagePt,column,row,aScaling._Luma->_palette,
		   aScaling._Luma->_palette_mapping_meth,uchar(minValue),uchar(maxValue));
	  free(luma);
	}
      else
	_bayer_rg_2_image(data,
			  anImagePt,column,row,minValue,maxValue,
			  aMode);
      break;
    case LUT::Scaling::BAYER_BG8:
      if(aMode == LUT::Scaling::COLOR_MAPPED)
	{
	  unsigned char* luma = _calculate_luma(data,column,row,anImageType);
	  if(minValue < 0) 
	    minValue = 0;
	  LUT::map(luma,anImagePt,column,row,aScaling._Luma->_palette,
		   aScaling._Luma->_palette_mapping_meth,uchar(minValue),uchar(maxValue));
	  free(luma);
	}
      else
	_bayer_bg_2_image(data,
			  anImagePt,column,row,minValue,maxValue,
			  aMode);
      break;
    case LUT::Scaling::BAYER_RG16:
      if(aMode == LUT::Scaling::COLOR_MAPPED)
	{
	  unsigned char* luma = _calculate_luma(data,column,row,anImageType);
	  LUT::map((unsigned short*)luma,anImagePt,column,row,aScaling._Luma->_palette,
		   aScaling._Luma->_palette_mapping_meth,
		   (unsigned short)minValue,(unsigned short)maxValue);
	  free(luma);
	}
      else
	_bayer_rg_2_image((const unsigned short*)data,
			  anImagePt,column,row,minValue,maxValue,
			  aMode);
      break;
    case LUT::Scaling::BAYER_BG16:
      if(aMode == LUT::Scaling::COLOR_MAPPED)
	{
	  unsigned char* luma = _calculate_luma(data,column,row,anImageType);
	  LUT::map((unsigned short*)luma,anImagePt,column,row,aScaling._Luma->_palette,
		   aScaling._Luma->_palette_mapping_meth,
		   (unsigned short)minValue,(unsigned short)maxValue);
	  free(luma);
	}
      else
	_bayer_bg_2_image((const unsigned short*)data,
			  anImagePt,column,row,minValue,maxValue,
			  aMode);
      break;
    default:
      return false;
    }
  
  return true;
}

unsigned char* LUT::raw_video_2_luma(const unsigned char *data,
				     int column,int row,
				     LUT::Scaling::image_type anImageType)
{
  unsigned char *lumaPt = NULL;
  switch(anImageType)
    {
    case LUT::Scaling::YUV411:
    case LUT::Scaling::YUV422:
    case LUT::Scaling::YUV444:
    case LUT::Scaling::I420: 
    case LUT::Scaling::Y8:
      {
	int aSize = column * row;
	_alloc(lumaPt,column,row,1);
	memcpy(lumaPt,data,aSize);
      }
      break;
    case LUT::Scaling::Y16:
      {
	int aSize = column * row << 1;
	_alloc(lumaPt,column,row,2);
	memcpy(lumaPt,data,aSize);
      }
      break;

    case LUT::Scaling::RGB555:
    case LUT::Scaling::RGB565:
    case LUT::Scaling::RGB24:
    case LUT::Scaling::RGB32:
    case LUT::Scaling::BGR24:
    case LUT::Scaling::BGR32:
    case LUT::Scaling::BAYER_RG8:
    case LUT::Scaling::BAYER_RG16:
    case LUT::Scaling::BAYER_BG8:
    case LUT::Scaling::BAYER_BG16:
      lumaPt = _calculate_luma(data,column,row,anImageType);
      break;
    default:
      break;
    }
  return lumaPt;
}
