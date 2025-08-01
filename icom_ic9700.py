"""
ICOM IC-9700 Radio Controller Module

This module provides communication interface for the ICOM IC-9700 transceiver
over network using UDP ports 50001, 50002, and 50003.

UDP Port Usage:
- 50001: Control commands and responses
- 50002: Audio stream data
- 50003: CI-V data stream
"""

import asyncio
import socket
import struct
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

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
                 audio_port: int = 50002, data_port: int = 50003):
        """Initialize the IC-9700 controller.
        
        Args:
            radio_ip: IP address of the IC-9700
            control_port: UDP port for control commands (default: 50001)
            audio_port: UDP port for audio stream (default: 50002)
            data_port: UDP port for data stream (default: 50003)
        """
        self.radio_ip = radio_ip
        self.control_port = control_port
        self.audio_port = audio_port
        self.data_port = data_port
        
        self.control_socket: Optional[socket.socket] = None
        self.audio_socket: Optional[socket.socket] = None
        self.data_socket: Optional[socket.socket] = None
        
        self.status = RadioStatus()
        self._connected = False
        
    async def connect(self) -> bool:
        """Connect to the IC-9700 radio.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to IC-9700 at {self.radio_ip}")
            
            # Create UDP sockets for each port
            await self._create_sockets()
            
            # Test connection by reading frequency
            frequency = await self.get_frequency()
            if frequency is not None:
                self._connected = True
                self.status.connected = True
                logger.info("Successfully connected to IC-9700")
                return True
            else:
                logger.error("Failed to communicate with IC-9700")
                await self.disconnect()
                return False
                
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self):
        """Disconnect from the IC-9700 radio."""
        logger.info("Disconnecting from IC-9700")
        
        self._connected = False
        self.status.connected = False
        
        if self.control_socket:
            self.control_socket.close()
            self.control_socket = None
            
        if self.audio_socket:
            self.audio_socket.close()
            self.audio_socket = None
            
        if self.data_socket:
            self.data_socket.close()
            self.data_socket = None
    
    async def _create_sockets(self):
        """Create UDP sockets for communication."""
        try:
            # Control socket
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_socket.settimeout(2.0)
            
            # Audio socket  
            self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.audio_socket.settimeout(2.0)
            
            # Data socket
            self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.data_socket.settimeout(2.0)
            
            logger.debug("UDP sockets created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create sockets: {e}")
            raise
    
    def _build_civ_command(self, command: int, data: bytes = b'') -> bytes:
        """Build a CI-V command packet.
        
        Args:
            command: CI-V command byte
            data: Command data bytes
            
        Returns:
            Complete CI-V command packet
        """
        # CI-V packet format: FE FE [radio_addr] [controller_addr] [command] [data] FD
        packet = bytearray()
        packet.extend([0xFE, 0xFE])  # Preamble
        packet.append(self.RADIO_ADDRESS)  # Radio address
        packet.append(self.CONTROLLER_ADDRESS)  # Controller address
        packet.append(command)  # Command
        packet.extend(data)  # Data
        packet.append(0xFD)  # End marker
        
        return bytes(packet)
    
    async def _send_civ_command(self, command: int, data: bytes = b'') -> Optional[bytes]:
        """Send a CI-V command and receive response.
        
        Args:
            command: CI-V command byte
            data: Command data bytes
            
        Returns:
            Response data or None if failed
        """
        if not self.control_socket:
            logger.error("Control socket not available")
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
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to radio."""
        return self._connected
    
    def get_status(self) -> RadioStatus:
        """Get current radio status."""
        return self.status
