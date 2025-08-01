<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# SM-Control Project Instructions

This is a Python project for controlling the ICOM IC-9700 amateur radio transceiver over network using UDP communication.

## Project Context

- **Primary Goal**: Control ICOM IC-9700 radio remotely via network connection
- **Communication Protocol**: ICOM RS-BA Protocol over UDP with embedded CI-V commands
- **Network Ports**:
  - 50001: UDP Control Port (non-CI-V login, connect, ping messages)
  - 50002: UDP Data Stream / CI-V Port (CI-V commands after successful connection)
  - 50003: UDP Audio Stream Port (audio samples and control messages)
- **Target Hardware**: ICOM IC-9700 VHF/UHF/SHF transceiver
- **Authentication**: Username: n4ldr, Password: icom9700

## Code Style Guidelines

- Use Python 3.8+ features and type hints
- Follow PEP 8 style guidelines
- Use async/await for network operations
- Implement proper error handling and logging
- Document all public methods and classes

## Domain-Specific Knowledge

- **ICOM RS-BA Protocol**: Multi-phase connection protocol with login, connect, and ready phases
- **UDP Control Port (50001)**: Handles login credentials, connection establishment, and ping/idle messages
- **UDP Data Stream / CI-V Port (50002)**: Carries CI-V commands after successful connection establishment
- **UDP Audio Stream Port (50003)**: Handles audio samples and "are-you-ready"/"I-am-ready" negotiations
- **CI-V Format**: FE FE [to] [from] [command] [parameters] FD embedded in UDP frames
- **Connection Phases**:
  1. Login with credentials on port 50001
  2. Connect negotiation on all ports
  3. Ready handshake before CI-V polling begins
- **Keep-Alive**: Idle and Ping messages required on all ports to maintain connection
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
