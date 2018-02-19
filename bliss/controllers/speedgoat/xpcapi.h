/* File:     xpcapi.h
 * Abstract: Definitions for the xPC Target C API
 */
/* Copyright 1996-2016 The MathWorks, Inc. */

#define MAX_ERR_MSG_LENGTH 50
#define MAX_SCOPES         30
#define MAX_SIGNALS        10

/* Communication definitions */
#define COMMTYP_RS232       1
#define COMMTYP_TCPIP       2

/* Scope Definitions */
#define SCTYPE_NONE        0
#define SCTYPE_HOST        1
#define SCTYPE_TARGET      2
#define SCTYPE_FILE        3
//hide this definition
#define SCTYPE_HIDDEN      4

#define TRIGMD_FREERUN     0
#define TRIGMD_SOFTWARE    1
#define TRIGMD_SIGNAL      2
#define TRIGMD_SCOPE       3
#define TRIGMD_SCEND       4

#define TRIGSLOPE_EITHER   0
#define TRIGSLOPE_RISING   1
#define TRIGSLOPE_FALLING  2

#define SCMODE_NUMERICAL   0
#define SCMODE_REDRAW      1
#define SCMODE_SLIDING     2
#define SCMODE_ROLLING     3

#define SCST_WAITTOSTART   0
#define SCST_WAITFORTRIG   1
#define SCST_ACQUIRING     2
#define SCST_FINISHED      3
#define SCST_INTERRUPTED   4
#define SCST_PREACQUIRING  5

/* Data Logging Definitions */
#define LGMOD_TIME         0
#define LGMOD_VALUE        1

/****************************************************************************/
/* ExtStruct:   lgmode =======================================================
 * Description: The structure that holds the values for data logging options.
 *              <vbl>mode is an integer which is 0 for time-equidistant
 *              logging or 1 for value-equidistant logging. These can also
 *              be set using the constants <vbl>LGMOD_TIME and
 *              <vbl>LGMOD_VALUE in xpcapiconst.h. For value-equidistant data,
 *              the incremental value between logged data points is set in
 *              <vbl>incrementvalue (this value is ignored for
 *              time-equidistant logging).
 * SeeAlso:     xPCGetLogMode, xPCSetLogMode
 */
/****************************************************************************/
typedef struct {
    int    mode;
    double incrementvalue;
} lgmode;

/****************************************************************************/
/* ExtStruct:   scopedata ====================================================
 * Description: This structure holds all the data about the scope, used in the
 *              functions <xref>xPCGetScope and <xref>xPCSetScope. In the
 *              structure, <vbl>number refers to the scope number. The
 *              remaining fields are as in the various xPCGetSc* functions
 *              (e.g. <vbl>state is as in <xref>xPCScGetState, <vbl>signals
 *              is as in <xref>xPCScGetSignals, etc.).
 * SeeAlso:     xPCGetScope, xPCSetScope, xPCScGetType, xPCScGetState,
 *              xPCScGetSignals, xPCScGetNumSamples, xPCScGetDecimation,
 *              xPCScGetTriggerMode, xPCScGetNumPrePostSamples,
 *              xPCScGetTriggerSignal, xPCScGetTriggerScope,
 *              xPCScGetTriggerLevel, xPCScGetTriggerSlope.
 */
/****************************************************************************/
typedef struct {
    int    number;
    int    type;
    int    state;
    int    signals[20];
    int    numsamples;
    int    decimation;
    int    triggermode;
    int    numprepostsamples;
    int    triggersignal;
    int    triggerscope;
    int    triggerscopesample;
    double triggerlevel;
    int    triggerslope;
} scopedata;

typedef struct {
    char          Label[12];
    char          DriveLetter;
    char          Reserved[3];
    unsigned int  SerialNumber;
    unsigned int  FirstPhysicalSector;
    unsigned int  FATType;            // 12 or 16
    unsigned int  FATCount;
    unsigned int  MaxDirEntries;
    unsigned int  BytesPerSector;
    unsigned int  SectorsPerCluster;
    unsigned int  TotalClusters;
    unsigned int  BadClusters;
    unsigned int  FreeClusters;
    unsigned int  Files;
    unsigned int  FileChains;
    unsigned int  FreeChains;
    unsigned int  LargestFreeChain;
    unsigned int  DriveType;
} diskinfo;

typedef struct {
    char	    Name[8];
    char	    Ext[3];
    int		    Day;
    int             Month;
    int             Year;
    int             Hour;
    int             Min;
    int             isDir;
    unsigned long   Size;
} dirStruct;

typedef struct {
    int            FilePos;
    int            AllocatedSize;
    int            ClusterChains;
    int            VolumeSerialNumber;
    char           FullName[255];
} fileinfo;

typedef enum ErrorValues_tag {
    ENOERR               =   0,
    EINVPORT             =   1,
    ENOFREEPORT          =   2,
    EPORTCLOSED          =   3,
    EINVCOMMTYP          =   4,

    EINVCOMPORT          =   5,
    ECOMPORTISOPEN       =   6,
    ECOMPORTACCFAIL      =   7,
    ECOMPORTWRITE        =   8,
    ECOMPORTREAD         =   9,
    ECOMTIMEOUT          =  10,
    EINVBAUDRATE         =  11,

    EWSNOTREADY          =  12,
    EINVWSVER            =  13,
    EWSINIT              =  14,

    ESOCKOPEN            =  15,
    ETCPCONNECT          =  16,
    EINVADDR             =  17,

    EFILEOPEN            =  18,
    EWRITEFILE           =  19,

    ETCPREAD             =  20,
    ETCPWRITE            =  21,
    ETCPTIMEOUT          =  22,

    EPINGPORTOPEN        =  23,
    EPINGSOCKET          =  24,
    EPINGCONNECT         =  25,

    EINVTFIN             =  26,
    EINVTS               =  27,
    EINVARGUMENT         =  28,

    ELOGGINGDISABLED     =  29,
    ETETLOGDISABLED      =  30,
    EINVLGMODE           =  31,
    EINVLGINCR           =  32,
    EINVLGDATA           =  33,
    ENODATALOGGED        =  34,

    EINVSTARTVAL         =  35,
    EINVNUMSAMP          =  36,
    EINVDECIMATION       =  37,
    ETOOMANYSAMPLES      =  38,
    EINVLOGID            =  39,

    ESTOPSIMFIRST        =  40,
    ESTARTSIMFIRST       =  41,
    ERUNSIMFIRST         =  42,
    EUSEDYNSCOPE         =  43,

    ETOOMANYSCOPES       =  44,
    EINVSCTYPE           =  45,
    ESCTYPENOTTGT        =  46,
    EINVSCIDX            =  47,
    ESTOPSCFIRST         =  48,

    EINVSIGIDX           =  49,
    EINVPARIDX           =  50,
    ENOMORECHANNELS      =  51,

    EINVTRIGMODE         =  52,
    EINVTRIGSLOPE        =  53,

    EINVTRSCIDX          =  54,

    EINVNUMSIGNALS       =  55,
    EPARNOTFOUND         =  56,
    ESIGNOTFOUND         =  57,

    ENOSPACE             =  58,
    EMEMALLOC            =  59,
    ETGTMEMALLOC         =  60,
    EPARSIZMISMATCH      =  61,

    ESIGLABELNOTUNIQUE   =  62,
    ESIGLABELNOTFOUND    =  63,
    ETOOMANYSIGNALS      =  64,
    ETIMELOGDISABLED     =  65,
    ESTATELOGDISABLED    =  66,
    EOUTPUTLOGDISABLED   =  67,

    ESCFINVALIDFNAME     =  68,
    ESCFISNOTAUTO        =  69,
    ESCFNUMISNOTMULT     =  70,


    ELOADAPPFIRST        = 101,
    EUNLOADAPPFIRST      = 102,

    EINVALIDMODEL        = 151,
    EINVNUMPARAMS        = 152,

    EINVFILENAME         = 201,
    EMAXPATHALLOWED      = 202,
    EFILEREAD            = 211,
    EFILEWRITE           = 212,
    EFILERENAME          = 213,

    EINVALIDOP           = 220,
    EINVALIDARG          = 221,

    EINVXPCVERSION       = 801,
    EINVINSTANDALONE     = 802,
    EMALFORMED           = 900,

    EINTERNAL            = 999,
} xPCErrorValue;

/* Connection ------------------------------------------------------------- */
int xPCReOpenPort(int port);
void xPCClosePort(int port);
int xPCOpenSerialPort(int comport, int baudRate);
int xPCOpenTcpIpPort(const char* address, const char* port);
void xPCOpenConnection(int port);
void xPCCloseConnection(int port);

/* Reboot ----------------------------------------------------------------- */
void xPCReboot(int port);

/* Error handling --------------------------------------------------------- */
int xPCGetLastError(void);
void xPCSetLastError(int error);
const char * xPCErrorMsg(int errorno, char *errmsg);

/* Global configuration --------------------------------------------------- */
const char * xPCGetAPIVersion(void);
void xPCGetTargetVersion(int port, char *ver);

double xPCGetExecTime(int port);
int xPCGetSimMode(int port);
void xPCGetPCIInfo(int port, char *buf);
double xPCGetSessionTime(int port);

double xPCGetStopTime(int port);
void xPCSetStopTime(int port, double tfinal);
void xPCSetDefaultStopTime(int port);

int xPCGetLoadTimeOut(int port);
void xPCSetLoadTimeOut(int port, int timeOut);

double xPCGetSampleTime(int port);
void xPCSetSampleTime(int port, double ts);

int xPCGetEcho(int port);
void xPCSetEcho(int port, int mode);

int xPCGetHiddenScopeEcho(int port);
void xPCSetHiddenScopeEcho(int port, int mode);

/* Application ------------------------------------------------------------ */
char * xPCGetAppName(int port, char *modelname);
void xPCStartApp(int port);
void xPCStopApp(int port);
int xPCIsAppRunning(int port);
int xPCIsOverloaded(int port);

void xPCLoadApp(int port, const char* pathstr, const char* filename);
void xPCUnloadApp(int port);

/* Parameters ------------------------------------------------------------- */
int xPCGetNumParams(int port);
void xPCGetParamName(int port, int parIdx, char *block, char *param);
void xPCGetParamSourceName(int port, int amiIdx, int parIdx, char *block, char *param);
int xPCGetParamIdx(int port, const char *block, const char *parameter);
void xPCGetParamType(int port, int parIdx, char *paramType);
void xPCGetParamDims(int port, int parIdx, int *dims);
int xPCGetParamDimsSize(int port, int parIdx);

void xPCGetParam(int port, int parIdx, double *paramValue);
void xPCSetParam(int port, int parIdx, const double *paramValue);

/* Logging ---------------------------------------------------------------- */
lgmode xPCGetLogMode(int port);
void xPCSetLogMode(int port, lgmode lgdata);
void xPCGetLogStatus(int port, int *logArray);
int xPCNumLogSamples(int port);
int xPCMaxLogSamples(int port);
int xPCNumLogWraps(int port);
int xPCGetNumOutputs(int port);
void xPCGetOutputLog(int port, int start, int numsamples,
                                  int decimation, int output_id, double *data);
                                  int xPCGetNumStates(int port);
void xPCGetStateLog(int port, int start, int numsamples,
                                 int decimation, int state_id, double *data);
void xPCGetTimeLog(int port, int start, int numsamples,
                                int decimation, double *data);
void xPCGetTETLog(int port, int start, int numsamples,
                               int decimation, double *data);

/* TET -------------------------------------------------------------------- */
double xPCAverageTET(int port);
void xPCMinimumTET(int port, double *data);
void xPCMaximumTET(int port, double *data);

/* Global signals --------------------------------------------------------- */
int xPCGetNumSignals(int port);
int xPCGetSignalIdx(int port, const char *sigName );
char * xPCGetSignalName(int port, int sigIdx, char *sigName);
char * xPCGetSignalLabel(int port, int sigIdx, char *sigLabel);
int xPCGetSigLabelWidth(int port, const char *sigName);
int xPCGetSigIdxfromLabel(int port, const char *sigName, int *sigIds);
double xPCGetSignal(int port,  int sigNum);
int xPCGetSignals(int port, int numSignals, const int *signals,
                               double *values);
int xPCGetSignalWidth(int port, int sigIdx);

/* Scopes ----------------------------------------------------------------- */
int  xPCGetNumScopes(int port);
int  xPCGetNumHiddenScopes(int port);
void xPCGetScopes(int port, int *data);
void xPCGetScopeList(int port, int *data);  /* what is the difference with xPCGetScopes ??? */
void xPCGetHiddenList(int port, int *data);
void xPCGetHiddenScopes(int port, int *data);
int xPCScGetType(int port, int scNum);

void xPCAddScope(int port, int type, int scNum);
void xPCRemScope(int port, int scNum);

scopedata xPCGetScope(int port, int scNum);
void xPCSetScope(int port, scopedata state);

void xPCScAddSignal(int port, int scNum, int sigNum);
void xPCScRemSignal(int port, int scNum, int sigNum);

int xPCScGetNumSignals(int port, int scNum);
void xPCScGetSignals(int port, int scNum, int *data);
void xPCScGetSignalList(int port, int scNum, int *data); /* what is the difference with xPCScGetSignals ??? */

double xPCScGetStartTime(int port, int scNum);

int xPCScGetState(int port, int scNum);
void xPCScSoftwareTrigger(int port, int scNum);
void xPCScStart(int port, int scNum);
void xPCScStop(int port, int scNum);
int xPCIsScFinished(int port, int scNum);

void xPCScGetData(int port, int scNum , int signal_id, int start,
                  int numsamples, int decimation, double *data);

int  xPCScGetAutoRestart(int port, int scNum);
void xPCScSetAutoRestart(int port, int scNum, int autorestart);

int xPCScGetDecimation(int port, int scNum);
void xPCScSetDecimation(int port, int scNum, int decimation);

int xPCScGetNumSamples(int port, int scNum);
void xPCScSetNumSamples(int port, int scNum, int samples);

double xPCScGetTriggerLevel(int port, int scNum);
void xPCScSetTriggerLevel(int port, int scNum, double level);

int xPCScGetTriggerMode(int port, int scNum);
void xPCScSetTriggerMode(int port, int scNum, int mode);

int xPCScGetTriggerScope(int port, int scNum);
void xPCScSetTriggerScope(int port, int scNum, int trigMode);

int xPCScGetTriggerScopeSample(int port, int scNum);
void xPCScSetTriggerScopeSample(int port, int scNum, int trigScSamp);

int xPCScGetTriggerSignal(int port, int scNum);
void xPCScSetTriggerSignal(int port, int scNum, int trigSig);

int xPCScGetTriggerSlope(int port, int scNum);
void xPCScSetTriggerSlope(int port, int scNum, int trigSlope);

int xPCScGetNumPrePostSamples(int port, int scNum);
void xPCScSetNumPrePostSamples(int port, int scNum, int prepost);

/* Target scope */
int xPCTgScGetGrid(int port, int scNum);
void xPCTgScSetGrid(int port, int scNum, int flag);

int xPCTgScGetMode(int port, int scNum);
void xPCTgScSetMode(int port, int scNum, int flag);

int xPCTgScGetViewMode(int port);
void xPCTgScSetViewMode(int port, int scNum);

void xPCTgScGetYLimits(int port, int scNum, double *limits);
void xPCTgScSetYLimits(int port, int scNum, const double *limits);

char * xPCTgScGetSignalFormat(int port,int scNum, int signalNo, char *signalFormat);
void xPCTgScSetSignalFormat(int port, int scNum, int signalNo, const char *signalFormat);

int xPCRegisterTarget(int commType, const char *ipAddress,
                                   const char *ipPort,
                                   int comPort, int baudRate);
void xPCDeRegisterTarget(int port);

int xPCTargetPing(int port);

int xPCIsTargetScope(int port);
void xPCSetTargetScopeUpdate(int port,int value);

/* File system ------------------------------------------------------------ */
void xPCFSReadFile(int port, int fileHandle, unsigned int start,
                               unsigned int numsamples, unsigned char *data);
unsigned int xPCFSRead(int port, int fileHandle, unsigned int start,
                           unsigned int numsamples, unsigned char *data);
void xPCFSWriteFile(int port, int fileHandle, int numbytes,
                                 const unsigned char *data);
//void xPCFSBufferInfo(int port, char *data);
unsigned int xPCFSGetFileSize(int port, int fileHandle);
int xPCFSOpenFile(int port, const char *filename,
                               const char *attrib);
void xPCFSCloseFile(int port, int fileHandle);
void xPCFSGetPWD(int port, char *data);
void xPCFTPGet(int port, int fileHandle, unsigned int numbytes, char *filename);
void xPCFTPPut(int port, int fileHandle, char *filename);
void xPCFSRemoveFile(int port, char *filename);
void xPCFSCD(int port, char *filename);
void xPCFSMKDIR(int port, const char *dirname);
void xPCFSRMDIR(int port, const char *dirname);
void xPCFSDir(int port, const char *path, char *listing, int numbytes);
int xPCFSDirSize(int port, const char *path);
void xPCFSGetError(int            port,
                                unsigned int   errCode,
                                unsigned char *message);

void xPCFSScSetFilename(int port, int scopeId,
                                     const char *filename);
const char * xPCFSScGetFilename(int port, int scopeId,
                                             char *filename);
void xPCFSScSetWriteMode(int port, int scopeId,
                                      int writeMode);
int xPCFSScGetWriteMode(int port, int scopeId);

void xPCFSScSetWriteSize(int port, int scopeId,
                                     unsigned int writeSize);
unsigned int xPCFSScGetWriteSize(int port, int scopeId);
void xPCReadXML(int port, int numbytes, unsigned char *data);
diskinfo xPCFSDiskInfo(int port, const char *driveLetter);
//diskinfo xPCFSBasicDiskInfo(int port, const char *driveLetter);
const char * xPCFSFileTable(int port, char *tableBuffer);
void xPCFSDirItems(int port, const char *path, dirStruct *dirs, int numDirItems);
int xPCFSDirStructSize(int port, const char *path);
fileinfo xPCFSFileInfo(int port, int fileHandle);
void xPCFSReNameFile(int port, const char *fsName, const char *newName);
void xPCFSScSetDynamicMode(int port, int scopeId, int onoff);
int xPCFSScGetDynamicMode(int port, int scopeId);
void xPCFSScSetMaxWriteFileSize(int port, int scopeId,
  unsigned int maxWriteFileSize);
  unsigned int xPCFSScGetMaxWriteFileSize(int port, int scopeId);
int xPCGetXMLSize(int port);
void xPCSaveParamSet(int port, const char *filename);
void xPCLoadParamSet(int port, const char *filename);

/* Params ??? */
int xPCGetParamsCount(int port);
void xPCGetParameterMap(int port, const char *blockName,const char *paramName, int* mapinfo);
int xPCGetParameterRecLength(int port, int* mapinfo);
char * xPCGetParameterXMLInfo(int port, int* mapinfo, char *xmlRec);
void xPCGetParameterStructureMember(int port, int* mapinfo, char* membername, double *values);
void xPCGetParameterValue(int port, int* mapinfo, int offset, char* membername, char* cPartName, double *values);
void xPCSetParameterValue(int port, int* mapinfo, int offset, char* membername, char *cPartName, int size, const double *paramValue);
