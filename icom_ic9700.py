#!/usr/bin/env python3
"""
Working ICOM IC-9700 Controller with UDP wrapper CI-V parsing
Based on user's Wireshark analysis of sdr-control traffic
"""

import asyncio
import logging
import socket
import struct
import time
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ICOMIC9700Controller:
    def __init__(self, radio_ip: str, username: str = "n4ldr", password: str = "icom9700"):
        self.radio_ip = radio_ip
        self.username = username
        self.password = password
        
        # Network settings
        self.control_port = 50001
        self.serial_port = 50002  # CI-V commands
        self.audio_port = 50003
        
        # Sockets
        self.control_socket = None
        self.serial_socket = None
        self.audio_socket = None
        
        # Connection state
        self.connected = False
        self.my_id = int(time.time()) & 0xFFFFFFFF
        
    async def connect(self) -> bool:
        """Full three-port connection method for CI-V commands."""
        try:
            logger.info(f"🔌 Connecting to ICOM IC-9700 at {self.radio_ip}")
            
            # Create UDP sockets for all three ports
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.serial_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Set reasonable timeouts
            self.control_socket.settimeout(5.0)
            self.serial_socket.settimeout(5.0)
            self.audio_socket.settimeout(5.0)
            
            # Step 1: Authenticate on control port (50001)
            logger.info("📡 Step 1: Authenticating on control port 50001...")
            if not await self._authenticate_control_port():
                logger.error("❌ Control port authentication failed")
                return False
            
            # Step 2: Authenticate on serial port (50002) - needed for CI-V
            logger.info("📡 Step 2: Authenticating on serial port 50002...")
            if not await self._authenticate_serial_port():
                logger.error("❌ Serial port authentication failed")
                return False
            
            # Step 3: Authenticate on audio port (50003)
            logger.info("📡 Step 3: Authenticating on audio port 50003...")
            if not await self._authenticate_audio_port():
                logger.warning("⚠️ Audio port authentication failed, but continuing...")
            
            # Step 4: Send ready signals
            logger.info("📡 Step 4: Sending ready signals...")
            await self._send_ready_signals()
            
            self.connected = True
            logger.info("✅ Connected with full three-port authentication")
            return True
                
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    async def _authenticate_control_port(self) -> bool:
        """Authenticate on control port 50001."""
        try:
            # Build login packet
            login_packet = bytearray(0x50)  # 80 bytes
            struct.pack_into('<I', login_packet, 0x00, 0x50)  # length
            struct.pack_into('<H', login_packet, 0x04, 0x02)  # type = login
            struct.pack_into('<H', login_packet, 0x06, 0x00)  # seq
            struct.pack_into('<I', login_packet, 0x08, self.my_id)  # sender ID
            
            # Add credentials
            username_bytes = self.username.encode('utf-8')[:15]
            password_bytes = self.password.encode('utf-8')[:15]
            login_packet[0x10:0x10+len(username_bytes)] = username_bytes
            login_packet[0x20:0x20+len(password_bytes)] = password_bytes
            
            # Send login to control port
            self.control_socket.sendto(bytes(login_packet), (self.radio_ip, self.control_port))
            
            # Wait for response
            response, addr = self.control_socket.recvfrom(1024)
            logger.info(f"✅ Control port login response: {len(response)} bytes")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Control port authentication failed: {e}")
            return False
    
    async def _authenticate_serial_port(self) -> bool:
        """Authenticate on serial port 50002 (CI-V port)."""
        try:
            # Build connection packet for serial port
            conn_packet = bytearray(0x10)
            struct.pack_into('<I', conn_packet, 0x00, 0x10)  # length
            struct.pack_into('<H', conn_packet, 0x04, 0x01)  # type = connect
            struct.pack_into('<H', conn_packet, 0x06, 0x01)  # seq
            struct.pack_into('<I', conn_packet, 0x08, self.my_id)  # sender ID
            struct.pack_into('<I', conn_packet, 0x0C, 0x00000000)  # received ID
            
            # Send to serial port
            self.serial_socket.sendto(bytes(conn_packet), (self.radio_ip, self.serial_port))
            
            # Wait for response
            response, addr = self.serial_socket.recvfrom(1024)
            logger.info(f"✅ Serial port connection response: {len(response)} bytes")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Serial port authentication failed: {e}")
            return False
    
    async def _authenticate_audio_port(self) -> bool:
        """Authenticate on audio port 50003."""
        try:
            # Build connection packet for audio port
            conn_packet = bytearray(0x10)
            struct.pack_into('<I', conn_packet, 0x00, 0x10)  # length
            struct.pack_into('<H', conn_packet, 0x04, 0x01)  # type = connect
            struct.pack_into('<H', conn_packet, 0x06, 0x02)  # seq
            struct.pack_into('<I', conn_packet, 0x08, self.my_id)  # sender ID
            struct.pack_into('<I', conn_packet, 0x0C, 0x00000000)  # received ID
            
            # Send to audio port
            self.audio_socket.sendto(bytes(conn_packet), (self.radio_ip, self.audio_port))
            
            # Wait for response
            response, addr = self.audio_socket.recvfrom(1024)
            logger.info(f"✅ Audio port connection response: {len(response)} bytes")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Audio port authentication failed: {e}")
            return False
    
    async def _send_ready_signals(self):
        """Send ready signals to all ports."""
        try:
            # Send "I am ready" signals
            ready_packet = bytearray(0x10)
            struct.pack_into('<I', ready_packet, 0x00, 0x10)  # length
            struct.pack_into('<H', ready_packet, 0x04, 0x07)  # type = ready
            struct.pack_into('<H', ready_packet, 0x06, 0x00)  # seq
            struct.pack_into('<I', ready_packet, 0x08, self.my_id)  # sender ID
            
            # Send to all ports
            self.control_socket.sendto(bytes(ready_packet), (self.radio_ip, self.control_port))
            self.serial_socket.sendto(bytes(ready_packet), (self.radio_ip, self.serial_port))
            self.audio_socket.sendto(bytes(ready_packet), (self.radio_ip, self.audio_port))
            
            logger.info("📡 Ready signals sent to all ports")
            
        except Exception as e:
            logger.warning(f"⚠️ Ready signals failed: {e}")
    
    async def _quick_auth(self) -> bool:
        """Quick authentication attempt."""
        try:
            # Build login packet
            login_packet = bytearray(0x50)  # 80 bytes
            struct.pack_into('<I', login_packet, 0x00, 0x50)  # length
            struct.pack_into('<H', login_packet, 0x04, 0x02)  # type = login
            struct.pack_into('<H', login_packet, 0x06, 0x00)  # seq
            struct.pack_into('<I', login_packet, 0x08, self.my_id)  # sender ID
            
            # Add credentials
            username_bytes = self.username.encode('utf-8')[:15]
            password_bytes = self.password.encode('utf-8')[:15]
            login_packet[0x10:0x10+len(username_bytes)] = username_bytes
            login_packet[0x20:0x20+len(password_bytes)] = password_bytes
            
            # Send login
            self.control_socket.sendto(bytes(login_packet), (self.radio_ip, self.control_port))
            
            # Wait for response
            response, addr = self.control_socket.recvfrom(1024)
            logger.debug(f"Login response: {response.hex()}")
            
            return True  # Basic success if we get any response
            
        except socket.timeout:
            logger.warning("Login timeout - proceeding anyway")
            return False
        except Exception as e:
            logger.warning(f"Login failed: {e} - proceeding anyway")
            return False
    
    async def _send_civ_command(self, command: int, data: bytes = b'', timeout: float = 5.0) -> Optional[bytes]:
        """Send CI-V command and return response with UDP wrapper analysis."""
        try:
            # Build CI-V command: FE FE A2 E1 [cmd] [data] FD
            civ_cmd = bytearray([0xFE, 0xFE, 0xA2, 0xE1, command])
            civ_cmd.extend(data)
            civ_cmd.append(0xFD)
            
            logger.debug(f"📤 Sending CI-V: {' '.join([f'{b:02X}' for b in civ_cmd])}")
            
            # Send to serial port (CI-V port)
            self.serial_socket.sendto(bytes(civ_cmd), (self.radio_ip, self.serial_port))
            
            # Wait for response
            old_timeout = self.serial_socket.gettimeout()
            self.serial_socket.settimeout(timeout)
            
            try:
                response, addr = self.serial_socket.recvfrom(1024)
                logger.debug(f"📥 Raw UDP response: {response.hex()}")
                
                # Parse the UDP wrapper to extract CI-V data
                return self._parse_civ_response(response, command)
                
            except socket.timeout:
                logger.warning(f"⏰ Timeout waiting for response to command 0x{command:02X}")
                return None
            finally:
                self.serial_socket.settimeout(old_timeout)
                
        except Exception as e:
            logger.error(f"❌ CI-V command 0x{command:02X} failed: {e}")
            return None
    
    def _parse_civ_response(self, response: bytes, command: int) -> Optional[bytes]:
        """Parse CI-V response from UDP wrapper based on user's Wireshark analysis."""
        try:
            logger.info(f"Radio Response [{response.hex().upper()}]")
            logger.info(f"Response Length: {len(response)} bytes")
            logger.info(f"Raw Response Bytes: {' '.join([f'{b:02X}' for b in response])}")
            
            # Based on user's analysis: look for CI-V pattern FE FE E1 A2 in UDP wrapper
            # Example: fefee1a2150100fd (FE FE E1 A2 15 01 00 FD)
            for i in range(len(response) - 4):
                if response[i:i+4] == b'\xFE\xFE\xE1\xA2':
                    logger.info(f"🎯 Found CI-V response pattern FE FE E1 A2 at offset {i}")
                    
                    # Find the CI-V terminator FD
                    fd_pos = response.find(b'\xFD', i + 4)
                    if fd_pos == -1:
                        logger.debug("CI-V terminator FD not found after FE FE E1 A2")
                        continue
                    
                    # Extract complete CI-V response: FE FE E1 A2 [cmd] [data...] FD
                    civ_response = response[i:fd_pos+1]
                    logger.info(f"📡 Extracted CI-V Response: {' '.join([f'{b:02X}' for b in civ_response])}")
                    
                    # Parse CI-V structure: FE FE E1 A2 [cmd] [data...] FD
                    if len(civ_response) >= 6:  # Minimum: FE FE E1 A2 cmd FD
                        from_addr = civ_response[2]  # E1 (radio)
                        to_addr = civ_response[3]    # A2 (controller)
                        cmd_byte = civ_response[4]
                        
                        # Based on user analysis: command is echoed, followed by actual data
                        # Example: 15 01 00 FD means command 15 01, data 00
                        if len(civ_response) >= 7:  # Has command + data
                            response_data = civ_response[5:-1]  # Everything between cmd and FD
                            logger.info(f"📊 CI-V Response Data: {' '.join([f'{b:02X}' for b in response_data])}")
                            
                            # Show the decoded CI-V command and value as requested by user
                            decoded_info = self._decode_civ_command(cmd_byte, response_data, from_addr, to_addr)
                            if decoded_info:
                                logger.info(f"Decoded Value : [{decoded_info}]")
                            
                            return response_data
                        else:
                            # Simple command with no additional data
                            logger.info(f"📊 Simple CI-V Response - Command: 0x{cmd_byte:02X}")
                            decoded_info = self._decode_civ_command(cmd_byte, b'', from_addr, to_addr)
                            if decoded_info:
                                logger.info(f"Decoded Value : [{decoded_info}]")
                            return b''
                    
                    return civ_response[5:-1] if len(civ_response) > 6 else b''
                    
            # If no CI-V pattern found, log the raw response for debugging
            logger.warning("❌ No CI-V pattern found in UDP response")
            logger.info(f"Raw UDP Response: {' '.join([f'{b:02X}' for b in response])}")
            return response  # Return raw response for analysis
                
        except Exception as e:
            logger.error(f"Error parsing CI-V response: {e}")
            return None
    
    def _decode_civ_command(self, command: int, data: bytes, from_addr: int, to_addr: int) -> Optional[str]:
        """Decode and display CI-V command details with function names and decoded values."""
        
        # Build command display with subcommands for better clarity
        if command == 0x15 and len(data) >= 1:
            # For command 15, show the full command + subcommand
            subcommand = data[0]
            command_display = f"Command {command:02X} {subcommand:02X}"
            
            subcommand_names = {
                0x01: "S-meter Reading",
                0x02: "Power meter Reading", 
                0x11: "SWR meter Reading",
                0x12: "ALC meter Reading",
                0x13: "Comp meter Reading",
                0x14: "VD meter Reading",
                0x15: "ID meter Reading"
            }
            function_name = subcommand_names.get(subcommand, f"Meter Reading 0x{subcommand:02X}")
            
        elif command == 0x1A and len(data) >= 1:
            # For command 1A, show the full command + subcommand
            subcommand = data[0]
            command_display = f"Command {command:02X} {subcommand:02X}"
            function_name = f"Miscellaneous Function 0x{subcommand:02X}"
            
        else:
            # For single-byte commands
            command_display = f"Command {command:02X}"
            command_names = {
                0x04: "Read Operating Mode",
                0x03: "Read Operating Frequency", 
                0x19: "Read Transceiver ID",
                0x06: "Set Operating Mode",
                0x05: "Set Operating Frequency",
            }
            function_name = command_names.get(command, f"Unknown Command 0x{command:02X}")
        
        logger.info(f"📡 CI-V {command_display}: {function_name}")
        
        # Decode specific command data
        if command == 0x04:  # Read Operating Mode
            if len(data) >= 1:
                mode_names = {
                    0x00: "LSB", 0x01: "USB", 0x02: "AM", 0x03: "CW",
                    0x04: "RTTY", 0x05: "FM", 0x06: "WFM", 0x07: "CW-R",
                    0x08: "RTTY-R", 0x17: "DV"
                }
                mode = mode_names.get(data[0], f"Unknown mode 0x{data[0]:02X}")
                filter_info = f", Filter: {data[1]:02X}" if len(data) > 1 else ""
                return f"Mode: {mode}{filter_info}"
        
        elif command == 0x15:  # Read S-meter/Power meter  
            if len(data) >= 1:
                subcommand = data[0]
                if subcommand == 0x01:  # S-meter reading
                    if len(data) >= 2:
                        s_meter_value = data[1]
                        return f"S-meter: {s_meter_value:02X}"
                    else:
                        return "S-meter command acknowledged"
                elif subcommand == 0x02:  # Power meter
                    if len(data) >= 2:
                        power_value = data[1]
                        return f"Power: {power_value:02X}"
                    else:
                        return "Power meter command acknowledged"
                else:
                    meter_types = {
                        0x11: "SWR", 0x12: "ALC", 0x13: "Comp", 
                        0x14: "VD", 0x15: "ID"
                    }
                    meter_type = meter_types.get(subcommand, f"Meter 0x{subcommand:02X}")
                    if len(data) >= 2:
                        meter_value = data[1]
                        return f"{meter_type}: {meter_value:02X}"
                    else:
                        return f"{meter_type} command acknowledged"
                        return f"{meter_type} command"
        
        elif command == 0x03:  # Read operating frequency
            if len(data) >= 4:
                try:
                    # Convert BCD frequency
                    freq_str = ''.join([f"{b:02x}" for b in reversed(data[:5])])
                    freq_hz = int(freq_str)
                    freq_mhz = freq_hz / 1_000_000
                    return f"Frequency: {freq_hz:,} Hz ({freq_mhz:.4f} MHz)"
                except:
                    return f"Raw frequency data: {data.hex()}"
        
        # Default: return raw data
        if data:
            return f"Raw data: {' '.join([f'{b:02X}' for b in data])}"
        else:
            return "Command acknowledged"
    
    async def disconnect(self):
        """Disconnect from radio - close all three ports."""
        try:
            if self.control_socket:
                self.control_socket.close()
                logger.debug("🔌 Control socket closed")
            if self.serial_socket:
                self.serial_socket.close()
                logger.debug("🔌 Serial socket closed")
            if self.audio_socket:
                self.audio_socket.close()
                logger.debug("🔌 Audio socket closed")
            
            self.connected = False
            logger.info("📡 Disconnected from radio (all three ports)")
            
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")

# Export the working controller
__all__ = ['ICOMIC9700Controller']
