#!/usr/bin/env python3
"""
Unified Rescue Pupper Controller
Combines thermal tracking and sensor monitoring in a single, simple loop.

Logic flow:
1. Get latest thermal image
2. Check end state (hot pixel threshold) - EXIT if reached
3. Find hottest region and calculate offset from center
4. If not centered: rotate to center
5. If centered: check sensor for obstacles
   - Obstacle: bark, move left
   - No obstacle: move forward
6. Repeat until target reached

Run: python3 unified_rescue.py
"""

import os
import sys
import time
import glob
import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image
import cv2
import serial
import pygame

# Add pupper_llm to path
sys.path.append(os.path.dirname(__file__))
from pupper_llm.karel.karel import KarelPupper

# ============== CONFIGURATION ==============
SAVED_IMAGES_DIR = os.path.join(os.path.dirname(__file__), 'saved_images')
IMAGE_CHECK_INTERVAL = 0.5  # seconds between image checks
CENTER_THRESHOLD = 0.15     # 15% offset = centered
MIN_ROTATION_OFFSET = 0.02  # ignore tiny offsets

# End state - when to stop
HOT_PIXEL_THRESHOLD = 10.0       # Stop when >10% of image is hot pixels
HOT_PIXEL_INTENSITY_MIN = 155    # Minimum intensity to count as "hot"

# Sensor configuration
SENSOR_PORT = '/dev/ttyACM1'
SENSOR_BAUDRATE = 115200
SENSOR_TIMEOUT = 1.0

# Error keywords that indicate NO obstacle (sensor can't see anything)
ERROR_KEYWORDS = [
    'error',
    'fail',
    'timeout',
    'invalid',
    'warning',
    'exception',
    'not found',
    'disconnected',
]

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("rescue_pupper")


# ============== THERMAL IMAGE FUNCTIONS ==============

def get_latest_image() -> str:
    """Get the path to the latest thermal image."""
    pattern = os.path.join(SAVED_IMAGES_DIR, '*.png')
    images = glob.glob(pattern)
    if not images:
        return None
    return max(images, key=os.path.getmtime)


def count_hot_pixels(image_path: str) -> float:
    """Count hot pixels and return percentage."""
    try:
        img = Image.open(image_path)
        arr = np.array(img)
        total = arr.shape[0] * arr.shape[1]
        
        if len(arr.shape) == 2:
            # Grayscale
            intensity = arr
        elif len(arr.shape) == 3:
            # Color - combine red channel with brightness
            r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            intensity = (r.astype(np.float32) * 0.6 + 
                        (r + g + b).astype(np.float32) / 3 * 0.4)
        else:
            return 0.0
        
        hot_count = np.sum(intensity >= HOT_PIXEL_INTENSITY_MIN)
        return (hot_count / total) * 100.0
    except Exception as e:
        logger.error(f"Error counting hot pixels: {e}")
        return 0.0


def find_hottest_pixel(image_path: str) -> tuple:
    """Find (x, y) coordinates of the hottest pixel."""
    try:
        img = Image.open(image_path)
        arr = np.array(img)
        
        if len(arr.shape) == 2:
            # Grayscale
            intensity = arr.astype(np.float32)
        elif len(arr.shape) == 3:
            # Color thermal - hot regions are red/orange
            hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
            h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
            
            # Favor red/orange hues with high brightness
            red_mask = (h < 30) | (h > 150)
            heat = v.astype(np.float32) * (1.0 + s.astype(np.float32) / 255.0)
            heat[red_mask] *= 1.5
            intensity = heat
        else:
            return None, None
        
        # Find hottest region
        threshold = np.max(intensity) * 0.999
        hot_pixels = np.where(intensity >= threshold)
        
        if len(hot_pixels[0]) > 0:
            y = int(np.mean(hot_pixels[0]))
            x = int(np.mean(hot_pixels[1]))
            return x, y
        
        # Fallback: exact max
        idx = np.unravel_index(np.argmax(intensity), intensity.shape)
        return int(idx[1]), int(idx[0])
    except Exception as e:
        logger.error(f"Error finding hottest pixel: {e}")
        return None, None


def calculate_offset(image_path: str, hot_x: int) -> float:
    """Calculate horizontal offset from center (-0.5 to 0.5)."""
    try:
        img = Image.open(image_path)
        center = img.width / 2.0
        return (hot_x - center) / img.width
    except Exception as e:
        logger.error(f"Error calculating offset: {e}")
        return 0.0


# ============== SENSOR MONITOR CLASS ==============

class SensorMonitor:
    """
    Monitors serial sensor data in a background thread.
    Checks BOTH Sensor 1 and Sensor 2 for obstacles.
    
    Sensor behavior (matching sensor_monitor.py):
    - Valid data (numbers, readings) = obstacle detected
    - Error messages = no obstacle / path clear
    """
    
    def __init__(self):
        self.serial_port = None
        self.monitoring = False
        self.monitor_thread = None
        
        # Shared state (thread-safe via GIL for simple reads/writes)
        self.sensor1_obstacle = False
        self.sensor2_obstacle = False
        self.last_sensor1_value = ""
        self.last_sensor2_value = ""
        
        # Connect to sensor
        self._connect()
    
    def _connect(self):
        """Try to connect to the obstacle sensor."""
        try:
            self.serial_port = serial.Serial(
                SENSOR_PORT,
                baudrate=SENSOR_BAUDRATE,
                timeout=SENSOR_TIMEOUT
            )
            logger.info(f"Connected to sensor on {SENSOR_PORT}")
        except serial.SerialException as e:
            logger.warning(f"Sensor not available: {e}")
            logger.warning("Running without obstacle detection")
            self.serial_port = None
    
    def start(self):
        """Start the background monitoring thread."""
        if not self.serial_port:
            logger.warning("No sensor connected, skipping monitoring")
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Sensor monitoring thread started")
    
    def stop(self):
        """Stop monitoring and close serial port."""
        self.monitoring = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            logger.info("Sensor connection closed")
    
    def _is_valid_sensor_data(self, data_str: str) -> bool:
        """
        Determine if sensor data indicates obstacle (valid reading) or not (error).
        Matches logic from sensor_monitor.py.
        
        Returns:
            True if valid data (obstacle present)
            False if error message (no obstacle)
        """
        if not data_str or not data_str.strip():
            return False
        
        data_lower = data_str.lower()
        
        # Check for error keywords - these mean NO obstacle
        for keyword in ERROR_KEYWORDS:
            if keyword in data_lower:
                return False
        
        # Non-empty data without error keywords = valid = obstacle detected
        return True
    
    def _parse_sensor_data(self, line: str):
        """
        Parse sensor data line and update obstacle states.
        Format: "Sensor 1: value | Sensor 2: value"
        """
        parts = line.split('|')
        
        for part in parts:
            part = part.strip()
            
            # Parse Sensor 1
            if 'Sensor 1:' in part:
                value = part.split('Sensor 1:')[1].strip()
                self.last_sensor1_value = value
                self.sensor1_obstacle = self._is_valid_sensor_data(value)
                
                status = "OBSTACLE" if self.sensor1_obstacle else "clear"
                logger.debug(f"Sensor 1: '{value}' -> {status}")
            
            # Parse Sensor 2
            if 'Sensor 2:' in part:
                value = part.split('Sensor 2:')[1].strip()
                self.last_sensor2_value = value
                self.sensor2_obstacle = self._is_valid_sensor_data(value)
                
                status = "OBSTACLE" if self.sensor2_obstacle else "clear"
                logger.debug(f"Sensor 2: '{value}' -> {status}")
    
    def _monitor_loop(self):
        """Background thread that continuously reads sensor data."""
        logger.info("Sensor monitoring loop started")
        
        while self.monitoring:
            try:
                if self.serial_port and self.serial_port.in_waiting > 0:
                    data = self.serial_port.readline()
                    
                    try:
                        decoded = data.decode('utf-8').rstrip()
                        
                        # Parse the sensor data
                        if 'Sensor' in decoded:
                            self._parse_sensor_data(decoded)
                        
                    except UnicodeDecodeError:
                        logger.debug("Could not decode sensor data")
                
                # Small sleep to prevent CPU spin
                time.sleep(0.01)
                
            except Exception as e:
                logger.debug(f"Error in sensor monitor loop: {e}")
                time.sleep(0.1)
    
    def obstacle_detected(self) -> bool:
        """
        Check if ANY sensor detects an obstacle.
        Returns True if Sensor 1 OR Sensor 2 sees an obstacle.
        """
        if not self.serial_port:
            return False
        
        # Either sensor detecting obstacle = obstacle present
        return self.sensor1_obstacle or self.sensor2_obstacle
    
    def get_status(self) -> str:
        """Get human-readable status of both sensors."""
        s1 = "OBSTACLE" if self.sensor1_obstacle else "clear"
        s2 = "OBSTACLE" if self.sensor2_obstacle else "clear"
        return f"Sensor1: {s1} ({self.last_sensor1_value}) | Sensor2: {s2} ({self.last_sensor2_value})"


# ============== CELEBRATION ==============

def celebrate(pupper):
    """Celebrate reaching the target, then stop."""
    logger.info("=" * 60)
    logger.info("TARGET REACHED - Hot pixel threshold exceeded")
    logger.info("=" * 60)
    
    pupper.stop()
    time.sleep(0.2)
    
    # Wiggle celebration
    try:
        logger.info("Executing victory wiggle")
        pupper.wiggle(wiggle_time=3, play_sound=False)
    except Exception as e:
        logger.warning(f"Could not wiggle: {e}")
    
    # Play success sound
    try:
        pygame.mixer.init()
        success_path = os.path.join(os.path.dirname(__file__), 'success.wav')
        if os.path.exists(success_path):
            logger.info("Playing success sound")
            sound = pygame.mixer.Sound(success_path)
            sound.play()
            time.sleep(5.0)
        else:
            logger.info("Target acquired - Mission accomplished")
    except Exception as e:
        logger.error(f"Could not play sound: {e}")
        logger.info("Target acquired - Mission accomplished")
    
    pupper.stop()
    logger.info("MISSION COMPLETE - Shutting down")


# ============== MAIN CONTROL LOOP ==============

def run():
    """Main control loop - simple and terminates cleanly."""
    logger.info("=" * 60)
    logger.info("RESCUE PUPPER - Unified Controller")
    logger.info("=" * 60)
    logger.info(f"Monitoring: {SAVED_IMAGES_DIR}")
    logger.info(f"Hot pixel threshold: {HOT_PIXEL_THRESHOLD}%")
    logger.info(f"Center threshold: {CENTER_THRESHOLD * 100}%")
    logger.info(f"Using BOTH sensors for obstacle detection")
    logger.info("=" * 60)
    
    # Ensure image directory exists
    os.makedirs(SAVED_IMAGES_DIR, exist_ok=True)
    
    # Initialize
    pupper = KarelPupper()
    sensor_monitor = SensorMonitor()
    sensor_monitor.start()  # Start background sensor monitoring thread
    centered = False
    avoiding_obstacle = False  # Track if we're in obstacle avoidance mode
    
    try:
        while True:
            # --- Step 1: Get latest thermal image ---
            image_path = get_latest_image()
            
            if not image_path:
                logger.debug("No images found, waiting...")
                time.sleep(IMAGE_CHECK_INTERVAL)
                continue
            
            # --- Step 2: CHECK END STATE FIRST ---
            hot_pct = count_hot_pixels(image_path)
            logger.info(f"Hot pixels: {hot_pct:.1f}% (threshold: {HOT_PIXEL_THRESHOLD}%)")
            
            if hot_pct >= HOT_PIXEL_THRESHOLD:
                # TARGET REACHED - celebrate and EXIT
                sensor_monitor.stop()
                celebrate(pupper)
                break  # <-- Clean exit from loop
            
            # --- Step 3: Find hottest pixel ---
            hot_x, hot_y = find_hottest_pixel(image_path)
            if hot_x is None:
                logger.warning("Could not find hottest pixel")
                time.sleep(IMAGE_CHECK_INTERVAL)
                continue
            
            # --- Step 4: Calculate offset from center ---
            offset = calculate_offset(image_path, hot_x)
            logger.info(f"Hot pixel at ({hot_x}, {hot_y}), offset: {offset:.3f}")
            
            # --- Step 5: Rotate if not centered ---
            if abs(offset) >= CENTER_THRESHOLD:
                centered = False
                avoiding_obstacle = False  # Reset obstacle avoidance when rotating
                
                if abs(offset) < MIN_ROTATION_OFFSET:
                    # Too small, don't bother
                    pupper.stop()
                elif offset < 0:
                    # Hot region is LEFT of center, rotate RIGHT
                    logger.info(f"Rotating RIGHT (offset: {offset:.3f})")
                    pupper.turn_right()
                    time.sleep(0.3)
                    pupper.stop()
                else:
                    # Hot region is RIGHT of center, rotate LEFT
                    logger.info(f"Rotating LEFT (offset: {offset:.3f})")
                    pupper.turn_left()
                    time.sleep(0.3)
                    pupper.stop()
            
            # --- Step 6: If centered, check obstacles and move ---
            else:
                if not centered:
                    logger.info("Centered on target")
                    pupper.bark()
                    centered = True
                
                # Log sensor status
                logger.info(f"Sensors: {sensor_monitor.get_status()}")
                
                # Check for obstacles (EITHER sensor)
                if sensor_monitor.obstacle_detected():
                    if not avoiding_obstacle:
                        logger.info("Obstacle detected - initiating avoidance")
                        pupper.bark()
                        avoiding_obstacle = True
                    
                    # Keep moving left until obstacle is cleared
                    move_count = 0
                    max_moves = 30  # Safety limit to prevent infinite loop
                    
                    while sensor_monitor.obstacle_detected() and move_count < max_moves:
                        move_count += 1
                        logger.info(f"Avoiding obstacle: move left #{move_count}")
                        pupper.move_left()
                        time.sleep(0.1)  # Brief pause to let sensor update
                    
                    pupper.stop()
                    
                    if move_count >= max_moves:
                        logger.warning(f"Hit max avoidance moves ({max_moves}), stopping")
                    else:
                        logger.info(f"Obstacle cleared after {move_count} moves")
                    
                    avoiding_obstacle = False
                else:
                    # Path is clear
                    if avoiding_obstacle:
                        logger.info("Path now clear after avoiding obstacle")
                        avoiding_obstacle = False
                    
                    logger.info("Path clear - moving forward")
                    pupper.move_forward(duration=0.4)  # Smaller, more granular movement
                    pupper.stop()
                    
                    # After moving forward, will need to re-center
                    centered = False
            
            time.sleep(IMAGE_CHECK_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("Stopped by user (Ctrl+C)")
    
    finally:
        # ALWAYS clean up
        logger.info("Cleaning up...")
        pupper.stop()
        sensor_monitor.stop()
        logger.info("Shutdown complete")


# ============== ENTRY POINT ==============

if __name__ == '__main__':
    run()

