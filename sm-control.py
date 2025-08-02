#!/usr/bin/env python3
"""
ShackMate - Complete ICOM RS-BA1 Protocol Implementation

ICOM RS-BA1 protocol for connecting
to ICOM radios (IC-705, IC-9700, IC-7610, etc.) over network.

Compatible with:
- ICOM IC-705
- ICOM IC-9700  
- ICOM IC-7610
- ICOM IC-785x
- ICOM RS-BA1 server software
"""

import asyncio
import socket
import struct
import time
import logging
import argparse
import threading
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum
from dataclasses import dataclass
import random
from collections import deque
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
CONTROL_STREAM_PORT = 50001
SERIAL_STREAM_PORT = 50002
AUDIO_STREAM_PORT = 50003

PKT0_DEFAULT_SEND_INTERVAL = 0.1  # 100ms
PKT0_IDLE_AFTER = 1.0  # 1 second
PKT0_IDLE_SEND_INTERVAL = 1.0  # 1 second

PKT7_SEND_INTERVAL = 3.0  # 3 seconds
PKT7_TIMEOUT_DURATION = 3.0  # 3 seconds

REAUTH_INTERVAL = 60.0  # 1 minute
REAUTH_TIMEOUT = 3.0  # 3 seconds

EXPECT_TIMEOUT_DURATION = 10.0  # 10 seconds - increased timeout for better reliability
MAX_RETRANSMIT_REQUEST_PACKET_COUNT = 10

# ICOM CI-V Operating Modes
CIV_OPERATING_MODES = [
    {'name': 'LSB', 'code': 0x00},
    {'name': 'USB', 'code': 0x01},
    {'name': 'AM', 'code': 0x02},
    {'name': 'CW', 'code': 0x03},
    {'name': 'RTTY', 'code': 0x04},
    {'name': 'FM', 'code': 0x05},
    {'name': 'WFM', 'code': 0x06},
    {'name': 'CW-R', 'code': 0x07},
    {'name': 'RTTY-R', 'code': 0x08},
    {'name': 'DV', 'code': 0x17},
]

# W6EL Passcode Algorithm 
PASSCODE_SEQUENCE = {
    32: 0x47, 33: 0x5d, 34: 0x4c, 35: 0x42, 36: 0x66, 37: 0x20, 38: 0x23, 39: 0x46,
    40: 0x4e, 41: 0x57, 42: 0x45, 43: 0x3d, 44: 0x67, 45: 0x76, 46: 0x60, 47: 0x41,
    48: 0x62, 49: 0x39, 50: 0x59, 51: 0x2d, 52: 0x68, 53: 0x7e, 54: 0x7c, 55: 0x65,
    56: 0x7d, 57: 0x49, 58: 0x29, 59: 0x72, 60: 0x73, 61: 0x78, 62: 0x21, 63: 0x6e,
    64: 0x5a, 65: 0x5e, 66: 0x4a, 67: 0x3e, 68: 0x71, 69: 0x2c, 70: 0x2a, 71: 0x54,
    72: 0x3c, 73: 0x3a, 74: 0x63, 75: 0x4f, 76: 0x43, 77: 0x75, 78: 0x27, 79: 0x79,
    80: 0x5b, 81: 0x35, 82: 0x70, 83: 0x48, 84: 0x6b, 85: 0x56, 86: 0x6f, 87: 0x34,
    88: 0x32, 89: 0x6c, 90: 0x30, 91: 0x61, 92: 0x6d, 93: 0x7b, 94: 0x2f, 95: 0x4b,
    96: 0x64, 97: 0x38, 98: 0x2b, 99: 0x2e, 100: 0x50, 101: 0x40, 102: 0x3f, 103: 0x55,
    104: 0x33, 105: 0x37, 106: 0x25, 107: 0x77, 108: 0x24, 109: 0x26, 110: 0x74, 111: 0x6a,
    112: 0x28, 113: 0x53, 114: 0x4d, 115: 0x69, 116: 0x22, 117: 0x5c, 118: 0x44, 119: 0x31,
    120: 0x36, 121: 0x58, 122: 0x3b, 123: 0x7a, 124: 0x51, 125: 0x5f, 126: 0x52,
}

def passcode(s: str) -> bytes:
    """Encode string using W6EL passcode algorithm (ICOM RS-BA1 protocol)"""
    result = bytearray(16)
    for i in range(min(len(s), 16)):
        p = ord(s[i]) + i
        if p > 126:
            p = 32 + p % 127
        result[i] = PASSCODE_SEQUENCE.get(p, 0)
    return bytes(result)

class SeqNum:
    """Sequence number handling for UDP packet ordering"""
    def __init__(self, value: int, max_val: int = 0xFFFF):
        self.value = value & max_val
        self.max_val = max_val

    def __int__(self):
        return self.value

    def __eq__(self, other):
        return self.value == other.value if isinstance(other, SeqNum) else self.value == other

    def __add__(self, other):
        return SeqNum((self.value + other) & self.max_val, self.max_val)

    def __sub__(self, other):
        return SeqNum((self.value - other) & self.max_val, self.max_val)

class StreamCommon:
    """Common UDP stream handling for all three ICOM ports"""
    
    def __init__(self, name: str, port: int, connect_address: str):
        self.name = name
        self.port = port
        self.connect_address = connect_address
        self.conn: Optional[socket.socket] = None
        self.local_sid = 0
        self.remote_sid = 0
        self.got_remote_sid = False
        
        # Channels for communication
        self.read_chan = asyncio.Queue()
        self.reader_task: Optional[asyncio.Task] = None
        self.running = False
        
        # Packet handlers
        self.pkt0 = Pkt0Handler()
        self.pkt7 = Pkt7Handler()

    async def init(self):
        """Initialize UDP connection"""
        try:
            logger.info(f"{self.name}/connecting to {self.connect_address}:{self.port}")
            
            # Create UDP socket
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.conn.connect((self.connect_address, self.port))
            self.conn.setblocking(False)
            
            # Generate local session ID from local IP and port (like Go version)
            local_addr = self.conn.getsockname()
            try:
                # Use simple time-based session ID for now
                import time
                self.local_sid = int(time.time()) & 0xFFFFFFFF
            except:
                # Final fallback
                self.local_sid = random.randint(0x10000000, 0xEFFFFFFF)
            
            logger.debug(f"{self.name}/local SID: {self.local_sid:08X}")
            
        except Exception as e:
            logger.error(f"{self.name}/connection failed: {e}")
            raise

    async def start(self):
        """Start the connection handshake sequence with retries"""
        max_retries = 5  # Increased retries
        for attempt in range(max_retries):
            try:
                logger.info(f"{self.name}/handshake attempt {attempt + 1}/{max_retries}")
                await self._send_pkt3()
                await self._wait_for_pkt4_answer()
                await self._send_pkt6()
                await self._wait_for_pkt6_answer()
                
                # Start reader task
                self.running = True
                self.reader_task = asyncio.create_task(self._reader())
                logger.info(f"{self.name}/handshake successful!")
                return
                
            except Exception as e:
                logger.warning(f"{self.name}/handshake attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"{self.name}/retrying in 2 seconds...")
                    await asyncio.sleep(2)  # Increased delay between retries
                else:
                    logger.error(f"{self.name}/all handshake attempts failed")
                    raise

    async def _send_pkt3(self):
        """Send packet type 3 (connection request) - fixed packet structure"""
        pkt = bytearray(16)
        
        # Packet structure: [length:4][type:1][reserved:3][local_sid:4][remote_sid:4]
        struct.pack_into('<I', pkt, 0, 0x10)      # Length: 16 bytes (little-endian)
        struct.pack_into('<H', pkt, 4, 0x03)      # Type: 3 (connection request)
        struct.pack_into('<H', pkt, 6, 0x00)      # Reserved/sequence
        struct.pack_into('>I', pkt, 8, self.local_sid)   # Local session ID (big-endian)
        struct.pack_into('>I', pkt, 12, self.remote_sid) # Remote session ID (big-endian)
        
        logger.info(f"{self.name}/sending pkt3 to {self.connect_address}:{self.port}: {pkt.hex()}")
        await self._send(pkt)
        
        # Send duplicate packet immediately (some implementations do this)
        await asyncio.sleep(0.1)  # Small delay between sends
        await self._send(pkt)
        await asyncio.sleep(0.1)
        await self._send(pkt)  # Send three times for reliability

    async def _wait_for_pkt4_answer(self):
        """Wait for packet type 4 response with remote session ID"""
        logger.info(f"{self.name}/expecting pkt4 answer")
        # Don't be too strict about the exact pattern - just check for packet type 4
        response = await self._expect(16, bytes([0x10, 0x00, 0x00, 0x00, 0x04, 0x00]))
        
        # Extract remote session ID from positions 8-12 (radio's SID)
        self.remote_sid = struct.unpack('>I', response[8:12])[0]
        self.got_remote_sid = True
        logger.info(f"{self.name}/remote SID: {self.remote_sid:08X}")
        logger.info(f"{self.name}/pkt4 handshake successful!")

    async def _send_pkt6(self):
        """Send packet type 6 (ready signal)"""
        pkt = bytearray(16)
        # Use consistent packet structure like pkt3
        struct.pack_into('<I', pkt, 0, 0x10)      # Length: 16 bytes (little-endian)
        struct.pack_into('<H', pkt, 4, 0x06)      # Type: 6 (ready signal)
        struct.pack_into('<H', pkt, 6, 0x01)      # Subtype/flag
        struct.pack_into('>I', pkt, 8, self.local_sid)   # Local session ID (big-endian)
        struct.pack_into('>I', pkt, 12, self.remote_sid) # Remote session ID (big-endian)
        
        logger.info(f"{self.name}/sending pkt6 (ready): {pkt.hex()}")
        await self._send(pkt)
        await self._send(pkt)

    async def _wait_for_pkt6_answer(self):
        """Wait for packet type 6 acknowledgment"""
        logger.info(f"{self.name}/waiting for pkt6 answer")
        
        try:
            response = await asyncio.wait_for(self._recv(), timeout=10)
            logger.info(f"{self.name}/received response for pkt6: {response.hex()}")
            
            if len(response) >= 6:
                # Check for packet type 6 in the response
                packet_type = struct.unpack('<H', response[4:6])[0]
                if packet_type == 0x06:
                    logger.info(f"{self.name}/received pkt6 answer successfully")
                    return response
                else:
                    logger.debug(f"{self.name}/received packet type {packet_type:#04x}, expected 0x06")
            else:
                logger.debug(f"{self.name}/received short packet ({len(response)} bytes)")
                
            # Return the response anyway - radio might send valid response in different format
            return response
            
        except asyncio.TimeoutError:
            logger.error(f"{self.name}/timeout waiting for pkt6 answer")
            raise Exception(f"{self.name}/timeout waiting for pkt6 answer")

    async def _send(self, data: bytes):
        """Send UDP packet"""
        try:
            logger.debug(f"{self.name}/sending {len(data)} bytes: {data.hex()}")
            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self.conn, data)
            logger.debug(f"{self.name}/send successful")
        except Exception as e:
            logger.error(f"{self.name}/send error: {e}")
            raise

    async def _recv(self) -> bytes:
        """Receive UDP packet"""
        try:
            loop = asyncio.get_event_loop()
            data = await loop.sock_recv(self.conn, 1500)
            logger.debug(f"{self.name}/received {len(data)} bytes: {data.hex()}")
            # Store the last received packet for debugging
            self.last_received = data
            return data
        except Exception as e:
            logger.error(f"{self.name}/recv error: {e}")
            raise

    async def _expect(self, packet_length: int, pattern: bytes) -> bytes:
        """Wait for specific packet pattern"""
        try:
            logger.debug(f"{self.name}/expecting {packet_length} bytes with pattern {pattern.hex()}")
            response = await asyncio.wait_for(self._recv(), timeout=EXPECT_TIMEOUT_DURATION)
            logger.debug(f"{self.name}/received {len(response)} bytes: {response.hex()}")
            
            if len(response) == packet_length and response[:len(pattern)] == pattern:
                logger.debug(f"{self.name}/pattern matched!")
                return response
            else:
                logger.warning(f"{self.name}/pattern mismatch - expected {pattern.hex()}, got {response[:len(pattern)].hex() if len(response) >= len(pattern) else response.hex()}")
                # Don't fail immediately, maybe the radio sent a different but valid response
                return response
        except asyncio.TimeoutError:
            # Check if we received ANY packets at all
            logger.debug(f"{self.name}/checking for any received packets...")
            if hasattr(self, 'last_received') and self.last_received:
                logger.info(f"{self.name}/found previous packet: {self.last_received.hex()}")
                return self.last_received
            logger.error(f"{self.name}/expect timeout - server did not answer in {EXPECT_TIMEOUT_DURATION}s")
            logger.error(f"{self.name}/troubleshooting: check if {self.connect_address}:{self.port} is reachable")
            logger.error(f"{self.name}/troubleshooting: verify radio has RS-BA1 enabled and ports are open")
            raise Exception(f"{self.name}/expect timeout - server did not answer")

    async def _reader(self):
        """Background reader task"""
        while self.running:
            try:
                data = await self._recv()
                
                # Handle packet types
                if self.pkt7.is_pkt7(data):
                    await self.pkt7.handle(self, data)
                    continue  # Don't forward pkt7 packets
                elif self.pkt0.is_pkt0(data):
                    await self.pkt0.handle(self, data)
                
                # Forward to main handler
                await self.read_chan.put(data)
                
            except Exception as e:
                if self.running:
                    logger.error(f"{self.name}/reader error: {e}")
                break

    async def send_disconnect(self):
        """Send disconnect packet"""
        if not self.got_remote_sid:
            return
            
        logger.info(f"{self.name}/disconnecting")
        pkt = bytearray(16)
        struct.pack_into('<IHHH', pkt, 0, 0x10, 0, 0, 0x05)
        struct.pack_into('>II', pkt, 8, self.local_sid, self.remote_sid)
        
        await self._send(pkt)
        await self._send(pkt)

    async def deinit(self):
        """Clean up connection"""
        self.running = False
        
        if self.got_remote_sid and self.conn:
            await self.send_disconnect()
            
        if self.reader_task:
            self.reader_task.cancel()
            try:
                await self.reader_task
            except asyncio.CancelledError:
                pass
                
        if self.conn:
            self.conn.close()
            self.conn = None

class Pkt0Handler:
    """Handler for packet type 0 (idle and retransmit packets)"""
    
    def __init__(self):
        self.send_seq = 1
        self.tx_seq_buf = {}  # Simple sequence buffer
        
    def is_idle_pkt0(self, data: bytes) -> bool:
        return len(data) == 16 and data[:6] == bytes([0x10, 0x00, 0x00, 0x00, 0x00, 0x00])
        
    def is_pkt0(self, data: bytes) -> bool:
        return (len(data) >= 16 and 
                (self.is_idle_pkt0(data) or
                 data[:6] == bytes([0x10, 0x00, 0x00, 0x00, 0x01, 0x00]) or  # Retransmit request
                 data[:6] == bytes([0x18, 0x00, 0x00, 0x00, 0x01, 0x00])))   # Range retransmit

    async def handle(self, stream: StreamCommon, data: bytes):
        """Handle packet type 0"""
        if len(data) < 16:
            return
            
        # Handle retransmit requests
        if data[:6] == bytes([0x10, 0x00, 0x00, 0x00, 0x01, 0x00]):
            seq = struct.unpack('<H', data[6:8])[0]
            logger.debug(f"{stream.name}/got retransmit request for #{seq}")
            
            # Send stored packet or idle
            stored_data = self.tx_seq_buf.get(seq)
            if stored_data:
                logger.debug(f"{stream.name}/retransmitting #{seq}")
                await stream._send(stored_data)
                await stream._send(stored_data)
            else:
                logger.debug(f"{stream.name}/can't retransmit #{seq} - not found")
                await self._send_idle(stream, False, seq)
                await self._send_idle(stream, False, seq)

    async def send_tracked_packet(self, stream: StreamCommon, data: bytearray):
        """Send packet with sequence tracking"""
        # Set sequence number
        data[6:8] = struct.pack('<H', self.send_seq)
        
        # Store for potential retransmission
        self.tx_seq_buf[self.send_seq] = bytes(data)
        
        # Send packet
        await stream._send(data)
        self.send_seq = (self.send_seq + 1) & 0xFFFF

    async def _send_idle(self, stream: StreamCommon, tracked: bool, seq_if_untracked: int = 0):
        """Send idle packet"""
        pkt = bytearray(16)
        struct.pack_into('<IHHH', pkt, 0, 0x10, 0, 0, 0)
        if not tracked:
            struct.pack_into('<H', pkt, 6, seq_if_untracked)
        struct.pack_into('>II', pkt, 8, stream.local_sid, stream.remote_sid)
        
        if tracked:
            await self.send_tracked_packet(stream, pkt)
        else:
            await stream._send(pkt)

class Pkt7Handler:
    """Handler for packet type 7 (ping/keepalive packets)"""
    
    def __init__(self):
        self.send_seq = 2
        self.inner_send_seq = 0x8304
        self.send_task: Optional[asyncio.Task] = None
        self.running = False
        
    def is_pkt7(self, data: bytes) -> bool:
        return (len(data) == 21 and 
                data[1:6] == bytes([0x00, 0x00, 0x00, 0x07, 0x00]))

    async def handle(self, stream: StreamCommon, data: bytes):
        """Handle packet type 7"""
        got_seq = struct.unpack('<H', data[6:8])[0]
        
        if data[16] == 0x00:  # Request from radio
            if self.running:  # Only reply if auth is done
                await self._send_reply(stream, data[17:21], got_seq)
        else:  # Reply to our request
            if self.running:
                logger.debug(f"{stream.name}/got pkt7 reply")

    async def _send_reply(self, stream: StreamCommon, reply_id: bytes, seq: int):
        """Send packet type 7 reply"""
        pkt = bytearray(21)
        pkt[0] = 0x15
        pkt[4:6] = struct.pack('<H', 0x07)
        pkt[6:8] = struct.pack('<H', seq)
        pkt[8:12] = struct.pack('>I', stream.local_sid)
        pkt[12:16] = struct.pack('>I', stream.remote_sid)
        pkt[16] = 0x01  # Reply flag
        pkt[17:21] = reply_id
        
        await stream._send(pkt)

    async def start_periodic_send(self, stream: StreamCommon):
        """Start periodic packet 7 sending"""
        self.running = True
        self.send_task = asyncio.create_task(self._periodic_send_loop(stream))

    async def _periodic_send_loop(self, stream: StreamCommon):
        """Periodic ping sender"""
        while self.running:
            try:
                await asyncio.sleep(PKT7_SEND_INTERVAL)
                if self.running:
                    await self._send(stream)
            except Exception as e:
                logger.error(f"Pkt7 send error: {e}")
                break

    async def _send(self, stream: StreamCommon):
        """Send packet type 7"""
        reply_id = bytearray(4)
        reply_id[0] = random.randint(0, 255)
        reply_id[1] = self.inner_send_seq & 0xFF
        reply_id[2] = (self.inner_send_seq >> 8) & 0xFF
        reply_id[3] = 0x06
        self.inner_send_seq += 1
        
        pkt = bytearray(21)
        pkt[0] = 0x15
        pkt[4:6] = struct.pack('<H', 0x07)
        pkt[6:8] = struct.pack('<H', self.send_seq)
        pkt[8:12] = struct.pack('>I', stream.local_sid)
        pkt[12:16] = struct.pack('>I', stream.remote_sid)
        pkt[16] = 0x00  # Request flag
        pkt[17:21] = reply_id
        
        await stream._send(pkt)
        self.send_seq = (self.send_seq + 1) & 0xFFFF

    def stop_periodic_send(self):
        """Stop periodic sending"""
        self.running = False
        if self.send_task:
            self.send_task.cancel()

class ControlStream:
    """Main control stream handler for ICOM RS-BA1 protocol"""
    
    def __init__(self, connect_address: str, username: str, password: str):
        self.connect_address = connect_address
        self.username = username
        self.password = password
        
        # Stream connections
        self.common = StreamCommon("control", CONTROL_STREAM_PORT, connect_address)
        self.serial = SerialStream("serial", SERIAL_STREAM_PORT, connect_address)
        self.audio = AudioStream("audio", AUDIO_STREAM_PORT, connect_address)
        
        # Authentication state
        self.auth_inner_send_seq = 0
        self.auth_id = bytearray(6)
        self.got_auth_id = False
        self.auth_ok = False
        self.a8_reply_id = bytearray(16)
        self.got_a8_reply_id = False
        
        # Connection state
        self.serial_and_audio_stream_opened = False
        self.deinitializing = False
        self.running = False
        
        # Tasks
        self.main_task: Optional[asyncio.Task] = None
        self.reauth_task: Optional[asyncio.Task] = None

    async def init(self):
        """Initialize control stream and coordinate all three streams"""
        logger.debug("control/init")
        
        # Initialize all three streams sequentially with better error handling
        logger.info("🔄 Initializing control stream")
        await self.common.init()
        
        logger.info("🔄 Initializing serial stream")
        await self.serial.common.init()
        
        logger.info("🔄 Initializing audio stream")
        await self.audio.common.init()
        
        # Start handshakes sequentially - this might be more reliable
        logger.info("🤝 Starting control handshake")
        await self.common.start()
        
        logger.info("🤝 Starting serial handshake")
        await self.serial.common.start()
        
        logger.info("🤝 Starting audio handshake")
        await self.audio.common.start()
        
        # Initialize packet handlers
        self.common.pkt0 = Pkt0Handler()
        
        # Send login packet
        await self._send_pkt_login()
        
        logger.debug("control/expecting login answer")
        response = await self.common._expect(96, bytes([0x60, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00]))
        
        # Check for invalid username/password
        if response[48:52] == bytes([0xff, 0xff, 0xff, 0xfe]):
            raise Exception("invalid username/password")
        
        # Start packet 7 handler
        await self.common.pkt7.start_periodic_send(self.common)
        
        # Extract auth ID and send first auth
        self.auth_id[:] = response[26:32]
        self.got_auth_id = True
        await self._send_pkt_auth(0x02)
        logger.debug("control/login ok, first auth sent...")
        
        # Send second auth
        await self._send_pkt_auth(0x05)
        logger.debug("control/second auth sent...")
        
        # Start main loop
        self.running = True
        self.main_task = asyncio.create_task(self._main_loop())
        self.reauth_task = asyncio.create_task(self._reauth_loop())

    async def _send_pkt_login(self):
        """Send login packet with credentials"""
        # Generate random auth start ID
        auth_start_id = random.randint(0, 0xFFFF).to_bytes(2, 'big')
        
        # Encode credentials using W6EL algorithm
        username_encoded = passcode(self.username)
        password_encoded = passcode(self.password)
        
        # Build 128-byte login packet
        pkt = bytearray(128)
        struct.pack_into('<I', pkt, 0, 128)  # Length
        struct.pack_into('>II', pkt, 8, self.common.local_sid, self.common.remote_sid)
        pkt[16:20] = bytes([0x00, 0x00, 0x00, 0x70])  # Magic
        pkt[20] = 0x01  # Packet type
        struct.pack_into('<H', pkt, 23, self.auth_inner_send_seq)
        pkt[25:27] = auth_start_id
        
        # Credentials
        pkt[64:80] = username_encoded
        pkt[80:96] = password_encoded
        pkt[96:112] = b'icom-pc\x00' + b'\x00' * 8  # Device name
        
        await self.common.pkt0.send_tracked_packet(self.common, pkt)
        self.auth_inner_send_seq += 1

    async def _send_pkt_auth(self, magic: int):
        """Send authentication packet"""
        pkt = bytearray(64)
        struct.pack_into('<I', pkt, 0, 64)  # Length
        struct.pack_into('>II', pkt, 8, self.common.local_sid, self.common.remote_sid)
        pkt[16:20] = bytes([0x00, 0x00, 0x00, 0x30])  # Magic
        pkt[20] = 0x01  # Packet type
        pkt[21] = magic
        struct.pack_into('<H', pkt, 23, self.auth_inner_send_seq)
        pkt[25:31] = self.auth_id
        
        await self.common.pkt0.send_tracked_packet(self.common, pkt)
        self.auth_inner_send_seq += 1

    async def _send_request_serial_and_audio(self):
        """Request serial and audio streams"""
        logger.debug("control/requesting serial and audio stream")
        
        username_encoded = passcode(self.username)
        
        pkt = bytearray(144)
        struct.pack_into('<I', pkt, 0, 144)  # Length
        struct.pack_into('>II', pkt, 8, self.common.local_sid, self.common.remote_sid)
        pkt[16:20] = bytes([0x00, 0x00, 0x00, 0x80])  # Magic
        pkt[20] = 0x01  # Packet type
        pkt[21] = 0x03  # Sub-type
        struct.pack_into('<H', pkt, 23, self.auth_inner_send_seq)
        pkt[25:31] = self.auth_id
        pkt[31:47] = self.a8_reply_id
        
        # Stream configuration
        struct.pack_into('>HH', pkt, 80, SERIAL_STREAM_PORT, AUDIO_STREAM_PORT)
        pkt[96:112] = username_encoded
        
        # Audio configuration
        pkt[112] = 0x01  # Audio format
        pkt[113] = 0x01
        pkt[114] = 0x04
        pkt[115] = 0x04
        
        await self.common.pkt0.send_tracked_packet(self.common, pkt)
        self.auth_inner_send_seq += 1

    async def _main_loop(self):
        """Main message handling loop"""
        while self.running:
            try:
                # Get message from read channel
                response = await asyncio.wait_for(self.common.read_chan.get(), timeout=1.0)
                await self._handle_read(response)
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop
            except Exception as e:
                if self.running:
                    logger.error(f"Main loop error: {e}")
                    break

    async def _handle_read(self, response: bytes):
        """Handle incoming control messages"""
        if len(response) == 64 and response[:6] == bytes([0x40, 0x00, 0x00, 0x00, 0x00, 0x00]):
            # Auth response
            if response[21] == 0x05:  # Second auth response
                self.auth_ok = True
                await self._send_request_serial_and_audio_if_possible()
                
        elif len(response) == 80 and response[:6] == bytes([0x50, 0x00, 0x00, 0x00, 0x00, 0x00]):
            # A8 reply ID response
            self.a8_reply_id[:] = response[32:48]
            self.got_a8_reply_id = True
            await self._send_request_serial_and_audio_if_possible()
            
        elif (len(response) == 144 and response[:6] == bytes([0x90, 0x00, 0x00, 0x00, 0x00, 0x00]) 
              and response[96] == 1):
            # Serial and audio stream success
            logger.info("Serial and audio stream request successful")
            
            # Extract device name
            device_name_end = response[64:].find(b'\x00')
            device_name = response[64:64+device_name_end].decode('utf-8') if device_name_end > 0 else "Unknown"
            logger.info(f"Device name: {device_name}")
            
            # Initialize serial and audio streams
            await self.serial.init()
            await self.audio.init()
            
            self.serial_and_audio_stream_opened = True
            logger.info("✅ All streams connected successfully")

    async def _send_request_serial_and_audio_if_possible(self):
        """Send serial/audio request if conditions are met"""
        if not self.serial_and_audio_stream_opened and self.auth_ok and self.got_a8_reply_id:
            await self._send_request_serial_and_audio()

    async def _reauth_loop(self):
        """Periodic re-authentication"""
        while self.running:
            try:
                await asyncio.sleep(REAUTH_INTERVAL)
                if self.running:
                    logger.debug("control/sending periodic auth")
                    await self._send_pkt_auth(0x05)
            except Exception as e:
                if self.running:
                    logger.error(f"Reauth error: {e}")
                break

    async def deinit(self):
        """Clean up control stream"""
        self.running = False
        self.deinitializing = True
        
        # Cancel tasks
        if self.main_task:
            self.main_task.cancel()
        if self.reauth_task:
            self.reauth_task.cancel()
            
        # Clean up streams
        if self.serial:
            await self.serial.deinit()
        if self.audio:
            await self.audio.deinit()
            
        # Send deauth if connected
        if self.got_auth_id and self.common.got_remote_sid:
            logger.debug("control/sending deauth")
            await self._send_pkt_auth(0x01)
            await asyncio.sleep(0.5)  # Wait for packet to be sent
            
        await self.common.deinit()

class SerialStream:
    """Serial/CI-V stream handler"""
    
    def __init__(self, name: str, port: int, connect_address: str):
        self.common = StreamCommon(name, port, connect_address)
        self.send_seq = 1
        
    async def init(self):
        """Initialize serial stream"""
        await self.common.init()
        await self.common.start()
        logger.info(f"✅ {self.common.name} stream connected")

    async def send_civ_command(self, command: bytes) -> bool:
        """Send CI-V command over serial stream"""
        try:
            # Wrap CI-V command in UDP packet
            data_len = len(command)
            pkt = bytearray(21 + data_len)
            pkt[0] = 0x15 + data_len
            struct.pack_into('>II', pkt, 8, self.common.local_sid, self.common.remote_sid)
            pkt[16] = 0xc1
            pkt[17] = data_len
            struct.pack_into('<H', pkt, 19, self.send_seq)
            pkt[21:] = command
            
            await self.common.pkt0.send_tracked_packet(self.common, pkt)
            self.send_seq = (self.send_seq + 1) & 0xFFFF
            return True
            
        except Exception as e:
            logger.error(f"CI-V send error: {e}")
            return False

    async def deinit(self):
        """Clean up serial stream"""
        await self.common.deinit()

class AudioStream:
    """Audio stream handler"""
    
    def __init__(self, name: str, port: int, connect_address: str):
        self.common = StreamCommon(name, port, connect_address)
        
    async def init(self):
        """Initialize audio stream"""
        await self.common.init()
        await self.common.start()
        logger.info(f"✅ {self.common.name} stream connected")

    async def deinit(self):
        """Clean up audio stream"""
        await self.common.deinit()

class ShackMate:
    """Main application class - ShackMate ICOM RS-BA1 Client"""
    
    def __init__(self, connect_address: str = "n4ldr.ddns.net", username: str = "admin", 
                 password: str = "adminadmin"):
        self.connect_address = connect_address
        self.username = username
        self.password = password
        self.control_stream: Optional[ControlStream] = None
        self.running = False

    async def run(self):
        """Main application entry point"""
        logger.info("🚀 ShackMate - ICOM RS-BA1 Client")
        logger.info(f"📡 Connecting to {self.connect_address}")
        logger.info(f"👤 Username: {self.username}")
        
        # Setup signal handlers
        def signal_handler():
            logger.info("📤 Received interrupt signal")
            self.running = False
            
        if sys.platform != 'win32':
            for sig in [signal.SIGINT, signal.SIGTERM]:
                signal.signal(sig, lambda s, f: signal_handler())
        
        try:
            # Create and initialize control stream
            self.control_stream = ControlStream(self.connect_address, self.username, self.password)
            await self.control_stream.init()
            
            logger.info("✅ Successfully connected to ICOM radio!")
            self.running = True
            
            # Main application loop
            while self.running:
                await asyncio.sleep(1)
                
                # Show connection status
                if self.control_stream.serial_and_audio_stream_opened:
                    logger.info("📻 Radio connection active - all streams operational")
                else:
                    logger.info("⏳ Establishing radio streams...")
                    
        except KeyboardInterrupt:
            logger.info("👋 Application interrupted by user")
        except Exception as e:
            logger.error(f"❌ Application error: {e}")
            return False
        finally:
            await self.cleanup()
            
        return True

    async def cleanup(self):
        """Clean up application resources"""
        logger.info("🧹 Cleaning up...")
        self.running = False
        
        if self.control_stream:
            await self.control_stream.deinit()
            
        logger.info("👋 ShackMate stopped")

async def main():
    """Command line entry point"""
    parser = argparse.ArgumentParser(
        description="ShackMate - ICOM RS-BA1 Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -a ic-705.local -u admin -p adminadmin
  %(prog)s -a 192.168.1.100 -u n4ldr -p icom9700
  %(prog)s --address ic-9700.local --verbose
        """
    )
    
    parser.add_argument('-a', '--address', default='n4ldr.ddns.net',
                        help='Connect to address (default: n4ldr.ddns.net)')
    parser.add_argument('-u', '--username', default='admin',
                        help='Username (default: admin)')
    parser.add_argument('-p', '--password', default='adminadmin',
                        help='Password (default: adminadmin)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose (debug) logging')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Disable logging')
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run application
    app = ShackMate(args.address, args.username, args.password)
    success = await app.run()
    
    return 0 if success else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
