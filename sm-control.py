#!/usr/bin/env python3
"""
SM-Control: ICOM IC-9700 Radio Control System
Main control script for connecting to and controlling the ICOM IC-9700 radio over network.

Default UDP Ports:
- 50001: Control Port
- 50002: Audio Stream Port  
- 50003: Data Stream Port
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
    
    def __init__(self, radio_ip: str = "192.168.1.100"):
        """Initialize the SM-Control application.
        
        Args:
            radio_ip: IP address of the ICOM IC-9700 radio
        """
        self.radio_ip = radio_ip
        self.radio_controller = ICOMIC9700Controller(radio_ip)
        self.running = False
        
    async def start(self):
        """Start the SM-Control application."""
        logger.info("Starting SM-Control for ICOM IC-9700")
        logger.info(f"Connecting to radio at {self.radio_ip}")
        
        try:
            # Connect to the radio
            await self.radio_controller.connect()
            logger.info("Successfully connected to ICOM IC-9700")
            
            self.running = True
            await self.main_loop()
            
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
        """Main application loop."""
        logger.info("SM-Control main loop started")
        
        try:
            while self.running:
                # Example: Get current frequency
                frequency = await self.radio_controller.get_frequency()
                if frequency:
                    logger.info(f"Current frequency: {frequency} Hz")
                
                # Example: Get current mode
                mode = await self.radio_controller.get_mode()
                if mode:
                    logger.info(f"Current mode: {mode}")
                
                # Wait before next update
                await asyncio.sleep(5)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")

async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SM-Control: ICOM IC-9700 Radio Control")
    parser.add_argument(
        "--radio-ip", 
        default="192.168.1.100",
        help="IP address of the ICOM IC-9700 radio (default: 192.168.1.100)"
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
    app = SMControlApp(args.radio_ip)
    
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
