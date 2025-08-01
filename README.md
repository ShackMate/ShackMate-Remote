# SM-Control: ICOM IC-9700 Radio Control System

A Python-based control system for the ICOM IC-9700 VHF/UHF/SHF amateur radio transceiver. This project enables remote control of the radio over a network connection using the ICOM RS-BA Protocol with embedded CI-V commands over UDP.

## Features

- **ICOM RS-BA Protocol**: Full implementation of ICOM's network protocol with authentication
- **Multi-Phase Connection**: Login, connect, and ready handshake sequence
- **Network Communication**: Communicates via UDP on ports 50001 (control) and 50002 (CI-V serial)
- **Authentication**: Secure login with configurable credentials (default: n4ldr/icom9700)
- **Keep-Alive Support**: Automatic ping and idle messages to maintain connection
- **Frequency Control**: Read and set operating frequency across all bands
- **Mode Control**: Change operating modes (USB, LSB, CW, FM, AM, DV)
- **PTT Control**: Remote push-to-talk functionality
- **Status Monitoring**: Real-time monitoring of radio parameters and connection state
- **Async Operations**: Non-blocking asynchronous communication with automatic reconnection
- **Comprehensive Logging**: Detailed logging for debugging and monitoring

## Requirements

- Python 3.8 or higher
- ICOM IC-9700 transceiver with network interface enabled
- Network connection between computer and radio
- Valid RS-BA credentials (username/password)

## Network Configuration

The IC-9700 uses three UDP ports for network communication:

- **Port 50001**: Control commands and responses (CI-V protocol)
- **Port 50002**: Audio stream data
- **Port 50003**: Additional CI-V data stream

Make sure these ports are configured and accessible on your IC-9700.

## Installation

1. Clone or download this project
2. Navigate to the project directory
3. Install dependencies (currently no external dependencies required):

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Run the main control script with authentication:

```bash
python sm-control.py --radio-ip 192.168.1.100 --username n4ldr --password icom9700
```

### Command Line Options

- `--radio-ip`: IP address of the IC-9700 (default: 192.168.1.100)
- `--username`: RS-BA username for authentication (default: n4ldr)
- `--password`: RS-BA password for authentication (default: icom9700)
- `--verbose`, `-v`: Enable verbose logging

### Example Usage

```bash
# Connect to radio at default IP
python sm-control.py

# Connect to radio at specific IP with verbose logging
python sm-control.py --radio-ip 192.168.1.50 --verbose

# Get help
python sm-control.py --help
```

## Programming Interface

### Basic Controller Usage

```python
import asyncio
from icom_ic9700 import ICOMIC9700Controller, IC9700Mode

async def main():
    # Create controller instance
    controller = ICOMIC9700Controller("192.168.1.100")
    
    # Connect to radio
    if await controller.connect():
        # Get current frequency
        freq = await controller.get_frequency()
        print(f"Current frequency: {freq} Hz")
        
        # Set frequency to 145.500 MHz
        await controller.set_frequency(145500000)
        
        # Set mode to FM
        await controller.set_mode(IC9700Mode.FM)
        
        # Get radio status
        status = controller.get_status()
        print(f"Radio connected: {status.connected}")
        
        # Disconnect
        await controller.disconnect()

# Run the example
asyncio.run(main())
```

### Available Methods

#### Connection Management
- `connect()`: Connect to the radio
- `disconnect()`: Disconnect from the radio
- `is_connected`: Property to check connection status

#### Frequency Control
- `get_frequency()`: Read current frequency in Hz
- `set_frequency(frequency)`: Set frequency in Hz

#### Mode Control
- `get_mode()`: Read current operating mode
- `set_mode(mode)`: Set operating mode

#### PTT Control
- `set_ptt(state)`: Set PTT state (True for transmit, False for receive)

#### Status
- `get_status()`: Get complete radio status

## Project Structure

```
sm-control.py/
├── sm-control.py          # Main application script
├── icom_ic9700.py         # IC-9700 controller module
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── .github/
    └── copilot-instructions.md  # Copilot customization
```

## CI-V Protocol

This project implements the ICOM CI-V (Computer Interface V) protocol for radio communication. CI-V uses a simple packet structure:

```
FE FE [Radio Address] [Controller Address] [Command] [Data] FD
```

### Supported Commands

- **0x25**: Read frequency
- **0x00**: Set frequency  
- **0x26**: Read mode
- **0x01**: Set mode
- **0x1C**: PTT control

## Radio Configuration

To use this software with your IC-9700:

1. **Enable Network Interface**: Configure the radio's network settings
2. **Set IP Address**: Assign a static IP to the radio
3. **Configure Ports**: Ensure UDP ports 50001-50003 are enabled
4. **CI-V Settings**: Enable CI-V operation via network

## Troubleshooting

### Connection Issues

1. **Check IP Address**: Verify the radio's IP address is correct
2. **Network Connectivity**: Ensure the computer can ping the radio
3. **Firewall**: Check firewall settings allow UDP traffic on ports 50001-50003
4. **Radio Settings**: Verify CI-V and network interface are enabled

### Common Error Messages

- `"Connection failed"`: Check network connectivity and radio IP
- `"Command timeout"`: Radio may be busy or not responding
- `"Invalid response format"`: CI-V protocol error, check radio configuration

## Development

### Running in Development Mode

```bash
# Enable verbose logging
python sm-control.py --verbose

# Run with debugger
python -m pdb sm-control.py
```

### Testing

The project includes comprehensive error handling and logging. Monitor the logs for debugging information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

1. Follow PEP 8 coding standards
2. Add type hints to all functions
3. Include comprehensive error handling
4. Update documentation for new features
5. Test with actual IC-9700 hardware when possible

## License

This project is provided as-is for amateur radio operators. Please ensure compliance with your local amateur radio regulations when using this software.

## Disclaimer

This software is provided without warranty. Users are responsible for ensuring proper operation and compliance with applicable regulations. Always maintain manual control capability of your radio equipment.

## References

- [ICOM IC-9700 Manual](https://www.icom.co.jp/world/support/download/manual/)
- [CI-V Protocol Documentation](https://www.icom.co.jp/world/support/download/manual/)
- [Amateur Radio Bands](https://www.arrl.org/band-plan)
