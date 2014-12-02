import struct

DEFAULT_UDP_CLIENT_PORT = 8021
DEFAULT_UDP_SERVER_PORT = 8020

DEFAULT_TCP_START = 5555
DEFAULT_TCP_END = 7000

HEADER_SIZE = struct.calcsize('<ii')

UNKNOW_MESSAGE = -1

CONFIG = 1

(LOCK,UNLOCK,LOCK_OK_REPLY,LOCK_RETRY,LOCK_STOLLEN) = (20,21,22,23,24)

(REDIS_QUERY,REDIS_QUERY_ANSWER) = (30,31)

(POSIX_MQ_QUERY,POSIX_MQ_OK,POSIX_MQ_FAILED,POSIX_MQ_OPENED) = (40,41,42,43)

(CONFIG_GET_FILE,CONFIG_GET_FILE_FAILED,CONFIG_GET_FILE_OK) = (50,51,52)

def message(cmd, contents = ''):
  return '%s%s' % (struct.pack('<ii', cmd, len(contents)),contents)

def unpack_header(header) :
    return  struct.unpack('<ii',header)

def unpack_message(s):
  if(len(s) < HEADER_SIZE):
      raise ValueError

  messageType, messageLen = struct.unpack('<ii', s[:HEADER_SIZE])
  if len(s)<HEADER_SIZE+messageLen:
    raise ValueError
  message = s[HEADER_SIZE:HEADER_SIZE+messageLen]
  remaining = s[HEADER_SIZE+messageLen:]
  return messageType, message, remaining  
