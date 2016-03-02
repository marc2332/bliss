#ifndef __PIXMAPTOOLS_HISTO
#define __PIXMAPTOOLS_HISTO
#include <vector>
#include <algorithm>

class Stat
{
public:
  /**
   * @brief get a full histogram
   * @param data the imput data
   * @param nbElem the number of element of the input data
   * @param Y result array data of histogram
   * @param X result array data of histogram 
   */
  template<class IN>
  static void histo_full(const IN *data,int nbElem,std::vector<int> &Y,std::vector<IN> &X)
  {
    std::vector<IN> __data(data,data + nbElem);
    std::sort(__data.begin(),__data.end());
    typename std::vector<IN>::iterator i(__data.begin());
    IN aLastValue = *i;
    Y.push_back(1);
    X.push_back(aLastValue);
    ++i;
    for(;i != __data.end();++i)
      {
	if(*i == aLastValue) 
	  ++(Y.back());
	else
	  {
	    Y.push_back(1);
	    X.push_back(*i);
	    aLastValue = *i;
	  }
      }
  }
  template<class IN>
  static void _find_min_max(const IN *aData,int aNbValue,IN &dataMin,IN &dataMax)
  {
    dataMax = dataMin = *aData;++aData;
    for(int i = 1;i < aNbValue;++i,++aData)
      {
	if(*aData > dataMax) dataMax = *aData;
	else if(*aData < dataMin) dataMin = *aData;
      }
  }

  template<class IN>
  static void histo(const IN *data,int nbElem,std::vector<int> &Y,std::vector<IN> &X,
		    int binsNumber = 10,IN lower = 0,IN upper = 0)
  {
    if(lower == upper && lower == 0)
	_find_min_max(data,nbElem,lower,upper);

    double step = double(upper - lower) / binsNumber;
    double firstValue = lower;
    for(int i = binsNumber + 1;i;--i)
      {
	X.push_back(IN(firstValue));
	firstValue += step;
      }
    double invStep = 0.;
    if(step > 1e-6)
      invStep = 1. / step;
    Y = std::vector<int>(binsNumber + 1,0);
    const IN *aEndData = data + nbElem;
    IN maxVal = upper,minVal = lower;
    for(;data != aEndData;++data)
      {
	IN val = *data;
	if(val > maxVal || val < minVal) continue;
	else ++(Y[int((val - minVal) * invStep)]);
      }
  }

};
#endif
