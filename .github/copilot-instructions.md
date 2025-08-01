<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# SM-Control Project Instructions

This is a Python project for controlling the ICOM IC-9700 amateur radio transceiver over network using UDP communication.

## Project Context
- **Primary Goal**: Control ICOM IC-9700 radio remotely via network connection
- **Communication Protocol**: CI-V (Computer Interface V) over UDP
- **Network Ports**: 
  - 50001: Control commands and responses
  - 50002: Audio stream data  
  - 50003: CI-V data stream
- **Target Hardware**: ICOM IC-9700 VHF/UHF/SHF transceiver

## Code Style Guidelines
- Use Python 3.8+ features and type hints
- Follow PEP 8 style guidelines
- Use async/await for network operations
- Implement proper error handling and logging
- Document all public methods and classes

## Domain-Specific Knowledge
- **CI-V Protocol**: ICOM's Computer Interface V protocol for radio control
- **BCD Encoding**: Binary Coded Decimal used for frequency representation
- **Amateur Radio Bands**: VHF (144MHz), UHF (430MHz), SHF (1.2GHz)
- **Operating Modes**: USB, LSB, CW, FM, AM, DV (Digital Voice)

## Architecture Patterns
- Use dataclasses for radio status and configuration
- Implement controller pattern for radio communication
- Use enums for radio modes and constants
- Separate networking logic from business logic

## Testing Considerations
- Mock UDP sockets for unit testing
- Test CI-V command building and parsing
- Validate BCD conversion functions
- Test error handling for network timeouts
