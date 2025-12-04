#!/usr/bin/env python3
"""
Thermal Navigation Coordinator
Coordinates thermal tracking and obstacle avoidance for autonomous navigation.

This script orchestrates the rescue pupper's behavior:
1. Use thermal camera to orient/center pupper towards the hottest region
2. Once centered, attempt to move forward using sensor monitoring
3. If obstacle detected, move left until clear, then forward
4. After moving forward, return to step 1 (re-orient using thermal)
5. Loop continues until interrupted

The coordinator manages two subsystems:
- ThermalTracker: Centers the robot on the hottest thermal signature
- SensorMonitor: Navigates forward while avoiding obstacles
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path

# Add modules to path
sys.path.append(os.path.dirname(__file__))
from pupper_llm.karel.karel import KarelPupper
from thermal_tracker import ThermalTracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("thermal_nav_coordinator")

# Configuration
SAVED_IMAGES_DIR = os.path.join(os.path.dirname(__file__), 'saved_images')
CENTERING_TIMEOUT = 10.0  # Max time to spend centering (seconds)
FORWARD_MOVE_DURATION = 2.0  # How long to move forward before re-centering (seconds)
CENTER_THRESHOLD = 0.20  # Same as thermal_tracker
MIN_ROTATION_OFFSET = 0.02  # Same as thermal_tracker


class ThermalNavigationCoordinator:
    """Coordinates thermal tracking and obstacle avoidance for navigation."""
    
    def __init__(self):
        """Initialize the coordinator and Pupper connection."""
        logger.info("Initializing Thermal Navigation Coordinator...")
        self.pupper = KarelPupper()
        self.thermal_tracker = ThermalTracker()
        self.running = False
        logger.info("Coordinator initialized")
    
    def is_centered(self, image_path: str) -> tuple:
        """
        Check if the hottest region is centered in the thermal image.
        
        Args:
            image_path: Path to the thermal image
            
        Returns:
            tuple: (is_centered: bool, offset: float)
        """
        # Find hottest pixel
        hot_x, hot_y = self.thermal_tracker.find_hottest_pixel(image_path)
        
        if hot_x is None or hot_y is None:
            logger.warning("Could not find hottest pixel")
            return (False, 0.0)
        
        # Calculate horizontal offset
        offset = self.thermal_tracker.calculate_horizontal_offset(image_path, hot_x)
        
        # Check if centered (within threshold)
        centered = abs(offset) < CENTER_THRESHOLD
        
        return (centered, offset)
    
    def center_on_thermal_target(self) -> bool:
        """
        Rotate pupper to center on the hottest thermal region.
        
        Returns:
            bool: True if successfully centered, False if timeout or error
        """
        logger.info("=" * 60)
        logger.info("PHASE 1: CENTERING ON THERMAL TARGET")
        logger.info("=" * 60)
        
        start_time = time.time()
        last_log_time = start_time
        
        while time.time() - start_time < CENTERING_TIMEOUT:
            # Get latest thermal image
            latest_image = self.thermal_tracker.get_latest_image()
            
            if latest_image is None:
                logger.warning("No thermal images found, waiting...")
                time.sleep(0.5)
                continue
            
            # Check if centered
            centered, offset = self.is_centered(latest_image)
            
            # Log status every 2 seconds
            current_time = time.time()
            if current_time - last_log_time > 2.0:
                logger.info(f"Centering... offset: {offset:.3f}, centered: {centered}")
                last_log_time = current_time
            
            if centered:
                logger.info(f"🎯 Target CENTERED! (offset: {offset:.3f})")
                self.pupper.bark()
                self.pupper.stop()
                return True
            
            # Not centered - rotate to center
            if abs(offset) >= MIN_ROTATION_OFFSET:
                if offset < 0:
                    # Hot region is LEFT, rotate RIGHT
                    logger.debug(f"Rotating right (offset: {offset:.3f})")
                    self.pupper.turn_right()
                else:
                    # Hot region is RIGHT, rotate LEFT
                    logger.debug(f"Rotating left (offset: {offset:.3f})")
                    self.pupper.turn_left()
            else:
                # Offset too small to rotate
                self.pupper.stop()
            
            time.sleep(0.1)
        
        # Timeout reached
        logger.warning(f"Centering timeout after {CENTERING_TIMEOUT}s")
        self.pupper.stop()
        return False
    
    def navigate_forward_with_avoidance(self) -> bool:
        """
        Navigate forward while avoiding obstacles using sensor monitoring.
        Moves forward for a set duration, avoiding obstacles by moving left when detected.
        
        Returns:
            bool: True if successfully moved forward, False if error
        """
        logger.info("=" * 60)
        logger.info("PHASE 2: NAVIGATING FORWARD WITH OBSTACLE AVOIDANCE")
        logger.info("=" * 60)
        
        # Import sensor monitor functionality
        try:
            import serial
            
            # Open serial connection to sensor
            port = '/dev/ttyACM1'
            baudrate = 115200
            timeout = 1
            
            serial_port = serial.Serial(port, baudrate=baudrate, timeout=timeout)
            logger.info(f"Connected to sensor at {port}")
            
        except Exception as e:
            logger.error(f"Failed to connect to sensor: {e}")
            # Move forward anyway without sensor
            logger.info("Moving forward without obstacle avoidance...")
            self.pupper.move_forward()
            time.sleep(FORWARD_MOVE_DURATION)
            self.pupper.stop()
            serial_port.close() if 'serial_port' in locals() else None
            return True
        
        # Navigate with sensor monitoring
        start_time = time.time()
        avoiding_obstacle = False
        last_log_time = start_time
        
        try:
            while time.time() - start_time < FORWARD_MOVE_DURATION:
                # Check for sensor data
                if serial_port.in_waiting > 0:
                    data = serial_port.readline()
                    
                    try:
                        decoded_data = data.decode('utf-8').rstrip()
                        
                        # Extract Sensor 1 data
                        sensor1_data = self._extract_sensor1_data(decoded_data)
                        
                        if sensor1_data:
                            is_valid = self._is_valid_sensor_data(sensor1_data)
                            
                            # Log status periodically
                            current_time = time.time()
                            if current_time - last_log_time > 1.0:
                                status = "OBSTACLE" if is_valid else "CLEAR"
                                logger.info(f"Sensor: {status}, Avoiding: {avoiding_obstacle}")
                                last_log_time = current_time
                            
                            if is_valid:
                                # Obstacle detected
                                if not avoiding_obstacle:
                                    logger.info("🚧 OBSTACLE DETECTED! Moving left...")
                                    self.pupper.bark()
                                    avoiding_obstacle = True
                                
                                # Keep moving left while obstacle present
                                self.pupper.move_left()
                                
                            else:
                                # Path is clear
                                if avoiding_obstacle:
                                    logger.info("✓ Path clear! Moving forward...")
                                    avoiding_obstacle = False
                                
                                # Move forward
                                self.pupper.move_forward()
                    
                    except UnicodeDecodeError:
                        pass
                else:
                    # No sensor data - assume clear and move forward
                    if not avoiding_obstacle:
                        self.pupper.move_forward()
                
                time.sleep(0.1)
            
            # Navigation duration complete
            logger.info(f"✅ Forward navigation complete ({FORWARD_MOVE_DURATION}s)")
            self.pupper.stop()
            serial_port.close()
            return True
            
        except Exception as e:
            logger.error(f"Error during navigation: {e}")
            self.pupper.stop()
            if 'serial_port' in locals() and serial_port.is_open:
                serial_port.close()
            return False
    
    def _extract_sensor1_data(self, data_str):
        """Extract Sensor 1 data from serial string."""
        if 'Sensor 1:' in data_str:
            parts = data_str.split('|')
            for part in parts:
                if 'Sensor 1:' in part:
                    return part.split('Sensor 1:')[1].strip()
        return None
    
    def _is_valid_sensor_data(self, data_str):
        """Check if sensor data is valid (non-error)."""
        data_lower = data_str.lower()
        error_keywords = ['error', 'fail', 'timeout', 'invalid', 'warning', 'exception', 'not found', 'disconnected']
        
        for keyword in error_keywords:
            if keyword in data_lower:
                return False
        
        return len(data_str.strip()) > 0
    
    def run(self):
        """
        Main coordination loop.
        Alternates between thermal centering and forward navigation.
        """
        logger.info("=" * 60)
        logger.info("STARTING THERMAL NAVIGATION COORDINATOR")
        logger.info("=" * 60)
        logger.info(f"Monitoring thermal images in: {SAVED_IMAGES_DIR}")
        logger.info(f"Center threshold: {CENTER_THRESHOLD}")
        logger.info(f"Forward move duration: {FORWARD_MOVE_DURATION}s")
        logger.info(f"Centering timeout: {CENTERING_TIMEOUT}s")
        logger.info("=" * 60)
        
        # Ensure saved_images directory exists
        os.makedirs(SAVED_IMAGES_DIR, exist_ok=True)
        
        self.running = True
        cycle_count = 0
        
        try:
            while self.running:
                cycle_count += 1
                logger.info(f"\n{'=' * 60}")
                logger.info(f"CYCLE {cycle_count}")
                logger.info(f"{'=' * 60}\n")
                
                # Phase 1: Center on thermal target
                centered = self.center_on_thermal_target()
                
                if not centered:
                    logger.warning("Failed to center on target, skipping forward navigation")
                    time.sleep(1.0)
                    continue
                
                # Brief pause before moving
                time.sleep(0.5)
                
                # Phase 2: Navigate forward with obstacle avoidance
                success = self.navigate_forward_with_avoidance()
                
                if not success:
                    logger.warning("Forward navigation encountered error")
                
                # Brief pause before next cycle
                logger.info(f"Cycle {cycle_count} complete. Pausing before next cycle...\n")
                time.sleep(1.0)
                
        except KeyboardInterrupt:
            logger.info("\n" + "=" * 60)
            logger.info("SHUTTING DOWN COORDINATOR")
            logger.info("=" * 60)
            self.pupper.stop()
        except Exception as e:
            logger.error(f"Error in coordination loop: {e}")
            self.pupper.stop()
            raise


def main():
    """Entry point for the thermal navigation coordinator."""
    coordinator = ThermalNavigationCoordinator()
    coordinator.run()


if __name__ == '__main__':
    main()
