# TO BE IMPLEMENTED SOON

import io
from abc import ABCMeta, abstractmethod
import asyncio
from typing import List, Tuple, Any, Optional, Callable
import binascii
import struct

from util.misc import Logger

class YMSGCtrlBase(metaclass = ABCMeta):
	__slots__ = ('logger', 'decoder', 'encoder', 'peername', 'closed', 'close_callback', 'transport')
	
	logger: Logger
	decoder: 'YMSGDecoder'
	encoder: 'YMSGEncoder'
	peername: Tuple[str, int]
	close_callback: Optional[Callable[[], None]]
	closed: bool
	transport: Optional[asyncio.WriteTransport]
	
	def __init__(self, logger: Logger) -> None:
		self.logger = logger
		self.decoder = YMSGDecoder(logger)
		self.encoder = YMSGEncoder(logger)
		self.peername = ('0.0.0.0', 5050)
		self.closed = False
		self.close_callback = None
	
	def data_received(self, transport: asyncio.BaseTransport, data: bytes) -> None:
		self.peername = transport.get_extra_info('peername')
		y = self.decoder.data_received(data)
		
		# Escargot's MSN and Yahoo functions have similar name structures
		# MSN: "_m_CMD"
		# Yahoo: "_y_[hex version of service; a bit nicer than using the service number]
		
		try:
			f = getattr(self, '_y_{}'.format(binascii.hexlify(struct.pack('!H', y[2])).decode()))
			f(*y[3:])
		except Exception as ex:
			self.logger.error(ex)
	
	def send_reply(self, *y) -> None:
		self.encoder.write(y)
		transport = self.transport
		if transport is not None:
			transport.write(self.flush())
	
	def flush(self) -> bytes:
		return self.encoder.flush()
	
	def close(self) -> None:
		if self.closed: return
		self.closed = True
		
		# Send logout command
		
		if self.close_callback:
			self.close_callback()
		self._on_close()
	
	@abstractmethod
	def _on_close(self) -> None: pass

class YMSGDecoder:
    def __init__(self, logger):
        self.logger = logger
        self._data = b''
    
    def data_received(self, data):
        if self._data:
            self._data += data
        else:
            self._data = data
        while self._data:
            try:
                if self._decode_ymsg(self._data) is None:
                    break
                else:
                    (version, vendor_id, service, status, session_id, kvs) = self._decode_ymsg(self._data)
                
                yield (version, vendor_id, service, status, session_id, kvs)
    
    def _decode_ymsg(self, data):
        assert data[:4] == PRE
        assert len(data) >= 20
        header = data[4:20]
        payload = data[20:]
        (version, vendor_id, pkt_len, service, status, session_id) = struct.unpack('!BxHHHII', header)
        assert len(payload) == pkt_len
        parts = payload.split(SEP)
        kvs = {}
        for i in range(1, len(parts), 2):
            kvs[int(parts[i-1])] = parts[i].decode('utf-8')
        return (version, vendor_id, service, status, session_id, kvs)

class YMSGEncoder:
    def __init__(self, logger):
        self._logger = logger
        self._buf = io.BytesIO()
    
    def encode(self, y):
        y = list(y)
        # y = List[version, vendor_id, service, status, session_id, kvs]
        
        w = self._buf.write
        w(PRE)
        # version number and vendor id are replaced with 0x00000000
        w(b'\x00\x00\x00\x00')
        
        payload_list = []
        kvs = y[5]
        
        if kvs:
            for k, v in kvs.items():
                payload_list.extend([str(k).encode('utf-8'), SEP, str(v).encode('utf-8'), SEP])
        payload = b''.join(payload_list)
        self._logger.info('<<<', struct.pack('!HHII', len(payload), y[2], y[3], y[4]) + payload)
        w(struct.pack('!HHII', len(payload), y[2], y[3], y[4]))
        w(payload)
    
    def flush(self):
        data = self._buf.getvalue()
        if data:
            self._buf = io.BytesIO()
        return data

PRE = b'YMSG'
SEP = b'\xC0\x80'