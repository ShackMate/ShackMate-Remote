#!/usr/bin/env python3
"""
SM-Control: ICOM IC-9700 Radio Control System
Main control script for connecting to and controlling the ICOM IC-9700 radio over network.

Default UDP Ports:
- 50001: Control Port
- 50002: Data Stream / CI-V Port
- 50003: Audio Stream Port
"""

import asyncio
import logging
from pathlib import Path
from icom_ic9700 import ICOMIC9700Controller

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SMControlApp:
    """Main application class for SM-Control system."""
    
    def __init__(self, radio_ip: str = "n4ldr.ddns.net", 
                 username: str = "n4ldr", password: str = "icom9700"):
        """Initialize the SM-Control application.
        
        Args:
            radio_ip: IP address or hostname of the ICOM IC-9700 radio
            username: RS-BA login username
            password: RS-BA login password
        """
        self.radio_ip = radio_ip
        self.radio_controller = ICOMIC9700Controller(
            radio_ip, username=username, password=password
        )
        self.running = False
        
    async def start(self):
        """Start the SM-Control application."""
        logger.info("Starting SM-Control for ICOM IC-9700")
        logger.info(f"Connecting to radio at {self.radio_ip}")
        
        try:
            # Connect to the radio
            if await self.radio_controller.connect():
                logger.info("Successfully connected to ICOM IC-9700")
                self.running = True
                await self.main_loop()
            else:
                logger.error("Failed to connect to ICOM IC-9700")
                return
            
        except Exception as e:
            logger.error(f"Failed to start SM-Control: {e}")
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the SM-Control application."""
        logger.info("Stopping SM-Control")
        self.running = False
        if self.radio_controller:
            await self.radio_controller.disconnect()
        logger.info("SM-Control stopped")
    
    async def main_loop(self):
        """Main application loop with keep-alive support."""
        logger.info("SM-Control main loop started")
        
        try:
            while self.running:
                # Send keep-alive messages to maintain connection
                await self.radio_controller.send_keep_alive()
                
                # Run comprehensive CI-V command test suite
                logger.info("🔧 Running CI-V command tests...")
                await self.radio_controller.test_civ_commands()
                
                # Log connection state
                state = self.radio_controller.connection_state
                logger.info(f"Connection state: {state.value}")
                
                # Wait before next test cycle
                logger.info("⏱️  Waiting 15 seconds before next test cycle...")
                await asyncio.sleep(15)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            # Try to reconnect on error
            if not self.radio_controller.is_connected:
                logger.info("Attempting to reconnect...")
                await self.radio_controller.connect()

async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SM-Control: ICOM IC-9700 Radio Control")
    parser.add_argument(
        "--radio-ip", 
        default="n4ldr.ddns.net",
        help="IP address or hostname of the ICOM IC-9700 radio (default: n4ldr.ddns.net)"
    )
    parser.add_argument(
        "--username", "-u",
        default="n4ldr",
        help="Login username for RS-BA protocol (default: n4ldr)"
    )
    parser.add_argument(
        "--password", "-p",
        default="icom9700",
        help="Login password for RS-BA protocol (default: icom9700)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and start the application
    app = SMControlApp(args.radio_ip, args.username, args.password)
    
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
