"""CFFI binding."""

import cffi

ffi = cffi.FFI()

ffi.cdef(
    """
typedef unsigned char  byte_t;
typedef unsigned char  boolean_t;
typedef unsigned short parameter_t;
typedef unsigned short flag_t;
int xiaInit(char *iniFile);
int xiaInitHandel(void);
int xiaGetDetectorItem(char *alias, char *name, void *value);
int xiaGetNumDetectors(unsigned int *numDet);
int xiaGetDetectors(char *detectors[]);
int xiaGetDetectors_VB(unsigned int index, char *alias);
int xiaDetectorFromDetChan(int detChan, char *alias);
int xiaGetFirmwareItem(char *alias, unsigned short decimation, char *name, void *value);
int xiaGetNumFirmwareSets(unsigned int *numFirmware);
int xiaGetFirmwareSets(char *firmware[]);
int xiaGetFirmwareSets_VB(unsigned int index, char *alias);
int xiaGetNumPTRRs(char *alias, unsigned int *numPTRR);
int xiaGetModuleItem(char *alias, char *name, void *value);
int xiaGetNumModules(unsigned int *numModules);
int xiaGetModules(char *modules[]);
int xiaGetModules_VB(unsigned int index, char *alias);
int xiaModuleFromDetChan(int detChan, char *alias);
int xiaStartSystem(void);
int xiaSetAcquisitionValues(int detChan, char *name, void *value);
int xiaGetAcquisitionValues(int detChan, char *name, void *value);
int xiaRemoveAcquisitionValues(int detChan, char *name);
int xiaGainOperation(int detChan, char *name, void *value);
int xiaGainCalibrate(int detChan, double deltaGain);
int xiaStartRun(int detChan, unsigned short resume);
int xiaStopRun(int detChan);
int xiaGetRunData(int detChan, char *name, void *value);
int xiaDoSpecialRun(int detChan, char *name, void *info);
int xiaGetSpecialRunData(int detChan, char *name, void *value);
int xiaLoadSystem(char *type, char *filename);
int xiaSaveSystem(char *type, char *filename);
int xiaGetParameter(int detChan, const char *name, unsigned short *value);
int xiaSetParameter(int detChan, const char *name, unsigned short value);
int xiaGetNumParams(int detChan, unsigned short *numParams);
int xiaGetParamData(int detChan, char *name, void *value);
int xiaGetParamName(int detChan, unsigned short index, char *name);
int xiaBoardOperation(int detChan, char *name, void *value);
int xiaMemoryOperation(int detChan, char *name, void *value);
int xiaCommandOperation(int detChan, byte_t cmd, unsigned int lenS, byte_t *send, unsigned int lenR, byte_t *recv);
int xiaExit(void);
int xiaEnableLogOutput(void);
int xiaSuppressLogOutput(void);
int xiaSetLogLevel(int level);
int xiaSetLogOutput(char *fileName);
int xiaCloseLog(void);
int xiaSetIOPriority(int pri);
void xiaGetVersionInfo(int *rel, int *min, int *maj, char *pretty);
"""
)

handel = ffi.dlopen("handel.dll")
