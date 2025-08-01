"""
Example configuration and usage scripts for SM-Control
"""

import asyncio
import logging
from icom_ic9700 import ICOMIC9700Controller, IC9700Mode

# Configure logging for examples
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def basic_example():
    """Basic usage example."""
    logger.info("Starting basic example")
    
    # Create controller with authentication
    controller = ICOMIC9700Controller("n4ldr.ddns.net", username="n4ldr", password="icom9700")
    
    try:
        # Connect to radio
        if await controller.connect():
            logger.info("Connected successfully!")
            
            # Read current settings
            frequency = await controller.get_frequency()
            mode = await controller.get_mode()
            
            logger.info(f"Current frequency: {frequency:,} Hz")
            logger.info(f"Current mode: {mode}")
            
            # Example: Set frequency to 2m band
            await controller.set_frequency(145000000)  # 145.000 MHz
            logger.info("Set frequency to 145.000 MHz")
            
            # Example: Set mode to FM
            await controller.set_mode(IC9700Mode.FM)
            logger.info("Set mode to FM")
            
        else:
            logger.error("Failed to connect to radio")
            
    except Exception as e:
        logger.error(f"Example failed: {e}")
    finally:
        await controller.disconnect()

async def frequency_scan_example():
    """Example of scanning through frequencies."""
    logger.info("Starting frequency scan example")
    
    controller = ICOMIC9700Controller("n4ldr.ddns.net", username="n4ldr", password="icom9700")
    
    try:
        if await controller.connect():
            # Scan 2m band repeater frequencies
            frequencies = [
                145150000,  # 145.150 MHz
                145250000,  # 145.250 MHz  
                145350000,  # 145.350 MHz
                145450000,  # 145.450 MHz
                145550000,  # 145.550 MHz
            ]
            
            for freq in frequencies:
                await controller.set_frequency(freq)
                logger.info(f"Tuned to {freq/1000000:.3f} MHz")
                await asyncio.sleep(2)  # Stay on frequency for 2 seconds
                
    except Exception as e:
        logger.error(f"Scan example failed: {e}")
    finally:
        await controller.disconnect()

async def mode_test_example():
    """Example of testing different operating modes."""
    logger.info("Starting mode test example")
    
    controller = ICOMIC9700Controller("n4ldr.ddns.net", username="n4ldr", password="icom9700")
    
    try:
        if await controller.connect():
            # Set frequency to 2m band
            await controller.set_frequency(145500000)  # 145.500 MHz
            
            # Test different modes
            modes = [IC9700Mode.FM, IC9700Mode.USB, IC9700Mode.CW]
            
            for mode in modes:
                await controller.set_mode(mode)
                current_mode = await controller.get_mode()
                logger.info(f"Set mode to {mode.name}, confirmed: {current_mode}")
                await asyncio.sleep(1)
                
    except Exception as e:
        logger.error(f"Mode test failed: {e}")
    finally:
        await controller.disconnect()

if __name__ == "__main__":
    print("SM-Control Examples")
    print("1. Basic Example")
    print("2. Frequency Scan")
    print("3. Mode Test")
    
    choice = input("Select example (1-3): ").strip()
    
    if choice == "1":
        asyncio.run(basic_example())
    elif choice == "2":
        asyncio.run(frequency_scan_example())
    elif choice == "3":
        asyncio.run(mode_test_example())
    else:
        print("Invalid choice")
