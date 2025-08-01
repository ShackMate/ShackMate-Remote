"""
ICOM IC-9700 Radio Controller Module

This module provides communication interface for the ICOM IC-9700 transceiver
over network using the ICOM RS-BA Protocol over UDP ports 50001, 50002, and 50003.

ICOM RS-BA Protocol Structure:
- Port 50001: UDP Control Port (login, connect, ping/idle messages)
- Port 50002: UDP Data Stream / CI-V Port (CI-V commands after connection)
- Port 50003: UDP Audio Stream Port (audio samples and ready handshake)

Connection Process:
1. Login phase with credentials (n4ldr/icom9700) on port 50001
2. Connect negotiation on all ports
3. Ready handshake on audio port
4. Normal CI-V operation on serial port with keep-alive messages
"""

import asyncio
import socket
import struct
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import time

logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    """Connection states for RS-BA protocol."""
    DISCONNECTED = "disconnected"
    LOGGING_IN = "logging_in"
    CONNECTING = "connecting"
    READY_HANDSHAKE = "ready_handshake"
    CONNECTED = "connected"

class RSBAMessageType(Enum):
    """ICOM RS-BA message types."""
    LOGIN = 0x00
    CONNECT = 0x01
    PING = 0x02
    IDLE = 0x03
    READY = 0x04
    CIV_DATA = 0x05

class IC9700Mode(Enum):
    """Operating modes supported by IC-9700."""
    LSB = 0x00
    USB = 0x01
    AM = 0x02
    CW = 0x03
    RTTY = 0x04
    FM = 0x05
    WFM = 0x06
    CW_R = 0x07
    RTTY_R = 0x08
    DV = 0x17

@dataclass
class RadioStatus:
    """Current radio status information."""
    frequency: int = 0
    mode: IC9700Mode = IC9700Mode.USB
    power_level: int = 0
    s_meter: int = 0
    connected: bool = False
    connection_state: ConnectionState = ConnectionState.DISCONNECTED

@dataclass
class RSBACredentials:
    """ICOM RS-BA authentication credentials."""
    username: str = "n4ldr"
    password: str = "icom9700"

class ICOMIC9700Controller:
    """Controller for ICOM IC-9700 radio over network."""
    
    # CI-V command constants
    CMD_READ_FREQ = 0x25
    CMD_SET_FREQ = 0x00
    CMD_READ_MODE = 0x26
    CMD_SET_MODE = 0x01
    CMD_PTT_ON = 0x1C
    CMD_PTT_OFF = 0x1C
    
    # Default radio address
    RADIO_ADDRESS = 0xA2
    CONTROLLER_ADDRESS = 0xE0
    
    def __init__(self, radio_ip: str, control_port: int = 50001, 
                 serial_port: int = 50002, audio_port: int = 50003,
                 username: str = "n4ldr", password: str = "icom9700"):
        """Initialize the IC-9700 controller.
        
        Args:
            radio_ip: IP address of the IC-9700
            control_port: UDP port for control/login (default: 50001)
            serial_port: UDP port for Data Stream/CI-V commands (default: 50002)
            audio_port: UDP port for Audio Stream (default: 50003)
            username: Login username (default: n4ldr)
            password: Login password (default: icom9700)
        """
        self.radio_ip = radio_ip
        self.control_port = control_port
        self.serial_port = serial_port
        self.audio_port = audio_port
        self.credentials = RSBACredentials(username, password)
        
        # Socket management
        self.control_socket: Optional[socket.socket] = None
        self.serial_socket: Optional[socket.socket] = None
        self.audio_socket: Optional[socket.socket] = None
        
        # Connection state
        self.status = RadioStatus()
        self._connection_state = ConnectionState.DISCONNECTED
        self._session_id = None
        self._sequence_counter = 0
        self._last_ping_time = 0
        self._last_idle_time = 0
        self._ping_interval = 5.0  # seconds
        self._idle_interval = 1.0  # seconds
        
    async def connect(self) -> bool:
        """Connect to the IC-9700 using ICOM RS-BA protocol.
        
        Implements the full connection sequence:
        1. Login with credentials on control port
        2. Connect negotiation on all ports  
        3. Ready handshake on audio port
        4. Start keep-alive messaging
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Starting RS-BA connection to IC-9700 at {self.radio_ip}")
            
            # Phase 1: Create sockets
            await self._create_sockets()
            
            # Phase 2: Login with credentials
            self._connection_state = ConnectionState.LOGGING_IN
            if not await self._login():
                logger.error("Login failed")
                await self.disconnect()
                return False
            
            # Phase 3: Connect negotiation
            self._connection_state = ConnectionState.CONNECTING
            if not await self._connect_negotiation():
                logger.error("Connect negotiation failed")
                await self.disconnect()
                return False
            
            # Phase 4: Ready handshake
            self._connection_state = ConnectionState.READY_HANDSHAKE
            if not await self._ready_handshake():
                logger.error("Ready handshake failed")
                await self.disconnect()
                return False
            
            # Phase 5: Connection established
            self._connection_state = ConnectionState.CONNECTED
            self.status.connected = True
            self.status.connection_state = self._connection_state
            self._last_ping_time = time.time()
            self._last_idle_time = time.time()
            
            logger.info("Successfully connected to IC-9700 via RS-BA protocol")
            
            # Test CI-V communication
            frequency = await self.get_frequency()
            if frequency is not None:
                logger.info(f"CI-V communication confirmed - frequency: {frequency} Hz")
                return True
            else:
                logger.warning("CI-V communication test failed, but connection established")
                return True
                
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self):
        """Disconnect from the IC-9700 radio."""
        logger.info("Disconnecting from IC-9700")
        
        self._connection_state = ConnectionState.DISCONNECTED
        self.status.connected = False
        self.status.connection_state = self._connection_state
        
        if self.control_socket:
            self.control_socket.close()
            self.control_socket = None
            
        if self.serial_socket:
            self.serial_socket.close()
            self.serial_socket = None
            
        if self.audio_socket:
            self.audio_socket.close()
            self.audio_socket = None
    
    async def _create_sockets(self):
        """Create UDP sockets for RS-BA communication."""
        try:
            # Control socket (login, ping, idle)
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_socket.settimeout(2.0)
            
            # Serial socket (CI-V commands)
            self.serial_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.serial_socket.settimeout(2.0)
            
            # Audio socket (audio + ready handshake)
            self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.audio_socket.settimeout(2.0)
            
            logger.debug("RS-BA UDP sockets created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create sockets: {e}")
            raise
    
    async def _login(self) -> bool:
        """Phase 1: Send login credentials to control port."""
        try:
            logger.info(f"Logging in as {self.credentials.username}")
            logger.debug(f"Sending login to {self.radio_ip}:{self.control_port}")
            
            # Build login message
            login_data = self._build_login_message()
            logger.debug(f"Login message size: {len(login_data)} bytes")
            
            # Send login to control port
            bytes_sent = self.control_socket.sendto(login_data, (self.radio_ip, self.control_port))
            logger.debug(f"Sent {bytes_sent} bytes to control port")
            
            # Wait for login response
            logger.debug("Waiting for login response...")
            response, addr = self.control_socket.recvfrom(1024)
            logger.debug(f"Received {len(response)} bytes from {addr}")
            
            if self._validate_login_response(response):
                logger.info("Login successful")
                return True
            else:
                logger.error("Login failed - invalid credentials or response")
                return False
                
        except socket.timeout:
            logger.error("Login timeout - no response from radio")
            logger.debug(f"Timeout occurred after {self.control_socket.gettimeout()} seconds")
            return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    async def _connect_negotiation(self) -> bool:
        """Phase 2: Connect negotiation on all ports."""
        try:
            logger.info("Starting connect negotiation")
            
            # Send connect messages to all ports
            connect_data = self._build_connect_message()
            
            # Control port connect
            self.control_socket.sendto(connect_data, (self.radio_ip, self.control_port))
            # Serial port connect  
            self.serial_socket.sendto(connect_data, (self.radio_ip, self.serial_port))
            # Audio port connect
            self.audio_socket.sendto(connect_data, (self.radio_ip, self.audio_port))
            
            # Wait for connect responses (simplified - should wait for all)
            response, addr = self.control_socket.recvfrom(1024)
            
            if self._validate_connect_response(response):
                logger.info("Connect negotiation successful")
                return True
            else:
                logger.error("Connect negotiation failed")
                return False
                
        except socket.timeout:
            logger.error("Connect negotiation timeout")
            return False
        except Exception as e:
            logger.error(f"Connect negotiation error: {e}")
            return False
    
    async def _ready_handshake(self) -> bool:
        """Phase 3: Ready handshake on audio port."""
        try:
            logger.info("Starting ready handshake")
            
            # Send "are-you-ready" to audio port
            ready_query = self._build_ready_query()
            self.audio_socket.sendto(ready_query, (self.radio_ip, self.audio_port))
            
            # Wait for "I-am-ready" response
            response, addr = self.audio_socket.recvfrom(1024)
            
            if self._validate_ready_response(response):
                logger.info("Ready handshake successful")
                return True
            else:
                logger.error("Ready handshake failed")
                return False
                
        except socket.timeout:
            logger.error("Ready handshake timeout")
            return False
        except Exception as e:
            logger.error(f"Ready handshake error: {e}")
            return False
    
    def _build_login_message(self) -> bytes:
        """Build RS-BA login message based on actual protocol capture.
        
        First packet from working SDR-CONTROL capture:
        10 00 00 00 04 00 00 00 db 5b 28 bc 2f c9 fe 0f
        """
        login_msg = bytearray()
        
        # Packet length (4 bytes, little endian) - 0x10 = 16 bytes
        login_msg.extend(b'\x10\x00\x00\x00')
        
        # Command type (4 bytes, little endian) - 0x04 = login request
        login_msg.extend(b'\x04\x00\x00\x00')
        
        # Session ID (8 bytes) - use the exact same one from capture
        session_id = b'\xdb\x5b\x28\xbc\x2f\xc9\xfe\x0f'
        login_msg.extend(session_id)
        
        # Store session ID for later use
        self._session_id = session_id
        
        logger.debug(f"Built login message: {login_msg.hex()}")
        return bytes(login_msg)
    
    def _build_connect_message(self) -> bytes:
        """Build RS-BA connect message."""
        # Simplified connect message format
        connect_msg = bytearray()
        connect_msg.extend(b'\x00\x02')  # Connect message type
        connect_msg.extend(b'\x00\x00\x00\x00')  # Additional parameters
        return bytes(connect_msg)
    
    def _build_ready_query(self) -> bytes:
        """Build 'are-you-ready' message for audio port."""
        ready_msg = bytearray()
        ready_msg.extend(b'\x00\x03')  # Ready query type
        ready_msg.extend(b'ARE-YOU-READY?')
        return bytes(ready_msg)
    
    def _build_ping_message(self) -> bytes:
        """Build ping message for keep-alive."""
        ping_msg = bytearray()
        ping_msg.extend(b'\x00\x04')  # Ping message type
        ping_msg.extend(int(time.time()).to_bytes(4, 'big'))  # Timestamp
        return bytes(ping_msg)
    
    def _build_idle_message(self) -> bytes:
        """Build idle message for keep-alive."""
        idle_msg = bytearray()
        idle_msg.extend(b'\x00\x05')  # Idle message type
        return bytes(idle_msg)
    
    def _validate_login_response(self, response: bytes) -> bool:
        """Validate login response from radio.
        
        Based on packet capture analysis, responses should follow the
        same structure as requests with different command types.
        """
        logger.debug(f"Login response received: {response.hex()}")
        
        # Check minimum packet length (at least 16 bytes for header)
        if len(response) < 16:
            logger.debug("Response too short")
            return False
            
        # Extract packet length (first 4 bytes, little endian)
        packet_length = int.from_bytes(response[0:4], 'little')
        logger.debug(f"Response packet length: {packet_length}")
        
        # Extract command type (bytes 4-8, little endian)
        command_type = int.from_bytes(response[4:8], 'little')
        logger.debug(f"Response command type: {command_type:08x}")
        
        # Extract session ID (bytes 8-16)
        response_session = response[8:16]
        logger.debug(f"Response session ID: {response_session.hex()}")
        
        # For login response, we expect specific command types
        # Based on packet capture, successful login might have command type 0x01 or 0x06
        if command_type in [0x01, 0x06]:
            logger.debug("Login response appears successful")
            return True
        else:
            logger.debug(f"Unexpected response command type: {command_type:08x}")
            return False
        """Validate login response from radio."""
        # Simplified validation - actual format needs reverse engineering
        if len(response) >= 4:
            # Check for successful login indicator
            return response[0:2] == b'\x00\x01' and response[2] == 0x00
        return False
    
    def _validate_connect_response(self, response: bytes) -> bool:
        """Validate connect response from radio."""
        if len(response) >= 4:
            return response[0:2] == b'\x00\x02' and response[2] == 0x00
        return False
    
    def _validate_ready_response(self, response: bytes) -> bool:
        """Validate ready response from radio."""
        if len(response) >= 10:
            return b'I-AM-READY' in response
        return False
    
    def _build_civ_command(self, command: int, data: bytes = b'') -> bytes:
        """Build a CI-V command packet embedded in UDP frame.
        
        Args:
            command: CI-V command byte
            data: Command data bytes
            
        Returns:
            Complete CI-V command packet for UDP transmission
        """
        # CI-V packet format: FE FE [radio_addr] [controller_addr] [command] [data] FD
        civ_packet = bytearray()
        civ_packet.extend([0xFE, 0xFE])  # CI-V preamble
        civ_packet.append(self.RADIO_ADDRESS)  # Radio address
        civ_packet.append(self.CONTROLLER_ADDRESS)  # Controller address
        civ_packet.append(command)  # Command
        civ_packet.extend(data)  # Data
        civ_packet.append(0xFD)  # CI-V postamble
        
        # Wrap in UDP frame (simplified - actual format may include additional headers)
        udp_frame = bytearray()
        udp_frame.extend(b'\x00\x06')  # CI-V data message type
        udp_frame.extend(len(civ_packet).to_bytes(2, 'big'))  # Length
        udp_frame.extend(civ_packet)  # CI-V payload
        
        return bytes(udp_frame)
    
    async def _send_civ_command(self, command: int, data: bytes = b'') -> Optional[bytes]:
        """Send a CI-V command via UDP serial port and receive response.
        
        Args:
            command: CI-V command byte
            data: Command data bytes
            
        Returns:
            Response data or None if failed
        """
        if not self.serial_socket or self._connection_state != ConnectionState.CONNECTED:
            logger.error("CI-V not available - not connected or serial socket unavailable")
            return None
        
        try:
            # Build and send CI-V command via serial port
            packet = self._build_civ_command(command, data)
            self.serial_socket.sendto(packet, (self.radio_ip, self.serial_port))
            
            # Receive response
            response, addr = self.serial_socket.recvfrom(1024)
            
            # Extract CI-V payload from UDP frame
            if len(response) >= 6 and response[0:2] == b'\x00\x06':
                payload_length = int.from_bytes(response[2:4], 'big')
                civ_response = response[4:4+payload_length]
                
                # Validate CI-V response format
                if len(civ_response) >= 6 and civ_response[0:2] == b'\xFE\xFE':
                    # Extract data portion (skip header and end marker)
                    return civ_response[5:-1]
                else:
                    logger.warning(f"Invalid CI-V response format: {civ_response.hex()}")
                    return None
            else:
                logger.warning(f"Invalid UDP frame format: {response.hex()}")
                return None
                
        except socket.timeout:
            logger.warning("CI-V command timeout")
            return None
        except Exception as e:
            logger.error(f"CI-V command failed: {e}")
            return None
            return None
        
        try:
            # Build and send command
            packet = self._build_civ_command(command, data)
            self.control_socket.sendto(packet, (self.radio_ip, self.control_port))
            
            # Receive response
            response, addr = self.control_socket.recvfrom(1024)
            
            # Validate response
            if len(response) >= 6 and response[0:2] == b'\xFE\xFE':
                # Extract data portion (skip header and end marker)
                return response[5:-1]
            else:
                logger.warning(f"Invalid response format: {response.hex()}")
                return None
                
        except socket.timeout:
            logger.warning("Command timeout")
            return None
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return None
    
    async def get_frequency(self) -> Optional[int]:
        """Get current operating frequency.
        
        Returns:
            Frequency in Hz or None if failed
        """
        response = await self._send_civ_command(self.CMD_READ_FREQ)
        if response and len(response) >= 5:
            # IC-9700 returns frequency in BCD format
            freq_bcd = response[:5]
            frequency = self._bcd_to_int(freq_bcd)
            self.status.frequency = frequency
            return frequency
        return None
    
    async def set_frequency(self, frequency: int) -> bool:
        """Set operating frequency.
        
        Args:
            frequency: Frequency in Hz
            
        Returns:
            True if successful
        """
        freq_bcd = self._int_to_bcd(frequency, 5)
        response = await self._send_civ_command(self.CMD_SET_FREQ, freq_bcd)
        
        if response == b'\xFB':  # ACK
            self.status.frequency = frequency
            return True
        return False
    
    async def get_mode(self) -> Optional[IC9700Mode]:
        """Get current operating mode.
        
        Returns:
            Current mode or None if failed
        """
        response = await self._send_civ_command(self.CMD_READ_MODE)
        if response and len(response) >= 1:
            mode_value = response[0]
            try:
                mode = IC9700Mode(mode_value)
                self.status.mode = mode
                return mode
            except ValueError:
                logger.warning(f"Unknown mode value: {mode_value}")
        return None
    
    async def set_mode(self, mode: IC9700Mode) -> bool:
        """Set operating mode.
        
        Args:
            mode: Desired operating mode
            
        Returns:
            True if successful
        """
        mode_data = bytes([mode.value, 0x01])  # Mode + filter
        response = await self._send_civ_command(self.CMD_SET_MODE, mode_data)
        
        if response == b'\xFB':  # ACK
            self.status.mode = mode
            return True
        return False
    
    async def set_ptt(self, state: bool) -> bool:
        """Set PTT (Push-to-Talk) state.
        
        Args:
            state: True for transmit, False for receive
            
        Returns:
            True if successful
        """
        ptt_data = bytes([0x00, 0x01 if state else 0x00])
        response = await self._send_civ_command(self.CMD_PTT_ON, ptt_data)
        
        return response == b'\xFB'  # ACK
    
    def _bcd_to_int(self, bcd_bytes: bytes) -> int:
        """Convert BCD bytes to integer."""
        result = 0
        for byte in reversed(bcd_bytes):
            result = result * 100 + (byte >> 4) * 10 + (byte & 0x0F)
        return result
    
    def _int_to_bcd(self, value: int, length: int) -> bytes:
        """Convert integer to BCD bytes."""
        result = bytearray(length)
        for i in range(length):
            digit1 = value % 10
            value //= 10
            digit2 = value % 10
            value //= 10
            result[i] = (digit2 << 4) | digit1
        return bytes(result)
    
    async def send_keep_alive(self):
        """Send keep-alive messages (ping and idle) to maintain connection."""
        if self._connection_state != ConnectionState.CONNECTED:
            return
        
        current_time = time.time()
        
        # Send ping messages
        if current_time - self._last_ping_time >= self._ping_interval:
            try:
                ping_msg = self._build_ping_message()
                # Send ping to all ports
                if self.control_socket:
                    self.control_socket.sendto(ping_msg, (self.radio_ip, self.control_port))
                if self.serial_socket:
                    self.serial_socket.sendto(ping_msg, (self.radio_ip, self.serial_port))
                if self.audio_socket:
                    self.audio_socket.sendto(ping_msg, (self.radio_ip, self.audio_port))
                
                self._last_ping_time = current_time
                logger.debug("Ping messages sent")
            except Exception as e:
                logger.error(f"Failed to send ping: {e}")
        
        # Send idle messages
        if current_time - self._last_idle_time >= self._idle_interval:
            try:
                idle_msg = self._build_idle_message()
                # Send idle to all ports when no other traffic
                if self.control_socket:
                    self.control_socket.sendto(idle_msg, (self.radio_ip, self.control_port))
                if self.serial_socket:
                    self.serial_socket.sendto(idle_msg, (self.radio_ip, self.serial_port))
                if self.audio_socket:
                    self.audio_socket.sendto(idle_msg, (self.radio_ip, self.audio_port))
                
                self._last_idle_time = current_time
                logger.debug("Idle messages sent")
            except Exception as e:
                logger.error(f"Failed to send idle: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to radio via RS-BA protocol."""
        return self._connection_state == ConnectionState.CONNECTED
    
    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state."""
        return self._connection_state
    
    def get_status(self) -> RadioStatus:
        """Get current radio status."""
        return self.status
