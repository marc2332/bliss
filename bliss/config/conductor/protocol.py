import struct

DEFAULT_UDP_CLIENT_PORT = 8021
DEFAULT_UDP_SERVER_PORT = 8020

HEADER_SIZE = struct.calcsize('<ii')

UNKNOW_MESSAGE = -1

CONFIG = 1

(LOCK,UNLOCK,LOCK_OK_REPLY,LOCK_RETRY,LOCK_STOLEN) = (20,21,22,23,24)

(REDIS_QUERY,REDIS_QUERY_ANSWER) = (30,31)

(POSIX_MQ_QUERY,POSIX_MQ_OK,POSIX_MQ_FAILED,POSIX_MQ_OPENED) = (40,41,42,43)

(CONFIG_GET_FILE,CONFIG_GET_FILE_FAILED,CONFIG_GET_FILE_OK) = (50,51,52)

(CONFIG_GET_DB_BASE_PATH,CONFIG_DB_FILE_RX,CONFIG_DB_END) = (60,61,62)

(CONFIG_SET_DB_FILE,CONFIG_SET_DB_FILE_FAILED,CONFIG_SET_DB_FILE_OK) = (70,71,72)

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
