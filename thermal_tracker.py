#!/usr/bin/env python3
"""
Thermal Image Tracker for Rescue Pupper
Monitors saved_images folder for thermal images and centers the hottest region.
"""

import os
import time
import glob
import logging
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import cv2

# Add pupper_llm to path
sys.path.append(os.path.dirname(__file__))
from pupper_llm.karel.karel import KarelPupper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("thermal_tracker")

# Configuration
SAVED_IMAGES_DIR = os.path.join(os.path.dirname(__file__), 'saved_images')
IMAGE_CHECK_INTERVAL = 0.5  # Check for new images every 0.5 seconds
CENTER_THRESHOLD = 0.15 # Consider centered if offset is within 15% of image width (middle 30% of camera)
MIN_ROTATION_OFFSET = 0.02  # Minimum offset to trigger rotation (2% of image width)

# End state detection - when pupper has reached the person
HOT_PIXEL_COVERAGE_THRESHOLD = 0.15  # Stop when 15% of image is hot (person is close)
HOT_PIXEL_INTENSITY_THRESHOLD = 0.85  # Pixels at 85% of max intensity count as "hot"


class ThermalTracker:
    """Tracks the hottest region in thermal images and centers it."""
    
    def __init__(self):
        """Initialize the thermal tracker and Pupper connection."""
        logger.info("Initializing Thermal Tracker...")
        self.pupper = KarelPupper()
        self.last_image_path = None
        self.last_image_time = time.time()
        self.centered = False
        self.reached_target = False  # End state - pupper has reached the person
        logger.info("Thermal Tracker initialized")
    
    def get_latest_image(self) -> str:
        """
        Get the path to the latest thermal image in saved_images folder.
        
        Returns:
            str: Path to the latest image, or None if no images found
        """
        image_pattern = os.path.join(SAVED_IMAGES_DIR, '*.png')
        images = glob.glob(image_pattern)
        
        if not images:
            return None
        
        # Sort by modification time and get the latest
        latest_image = max(images, key=os.path.getmtime)
        return latest_image
    
    def find_hottest_pixel(self, image_path: str) -> tuple:
        """
        Find the hottest pixel in the thermal image.
        
        For thermal images, the hottest region is typically:
        - In colorized thermal images: red/orange/yellow colors (hot colors)
        - In grayscale: brightest pixels
        
        Args:
            image_path: Path to the thermal image
            
        Returns:
            tuple: (x, y) coordinates of the hottest pixel, or (None, None) if error
        """
        try:
            # Load image
            img = Image.open(image_path)
            img_array = np.array(img)
            
            # Handle different image formats
            if len(img_array.shape) == 2:
                # Grayscale image - use directly
                intensity = img_array.astype(np.float32)
            elif len(img_array.shape) == 3:
                # Color image - for thermal colorized images, hot regions are red/orange
                # Convert to HSV and prioritize pixels with:
                # - High Value (brightness)
                # - Low Hue (red/orange range) or high saturation
                img_rgb = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
                h, s, v = img_rgb[:, :, 0], img_rgb[:, :, 1], img_rgb[:, :, 2]
                
                # Create a heat score that favors:
                # 1. High brightness (value)
                # 2. Red/orange hues (low hue values or high hue values near 180)
                # 3. High saturation
                # Red is at hue 0 or near 180, orange is around 15-30
                red_mask = (h < 30) | (h > 150)  # Red/orange range
                heat_score = v.astype(np.float32) * (1.0 + s.astype(np.float32) / 255.0)
                heat_score[red_mask] *= 1.5  # Boost red/orange regions
                intensity = heat_score
            else:
                logger.error(f"Unexpected image shape: {img_array.shape}")
                return (None, None)
            
            # Find the pixel with maximum intensity/heat score
            max_intensity = np.max(intensity)
            
            # Use a threshold to find all "hot" pixels (within 95% of max)
            # This gives us a region rather than just a single pixel
            threshold = max_intensity * 0.95
            hot_pixels = np.where(intensity >= threshold)
            
            if len(hot_pixels[0]) > 0:
                # Use centroid of all hot pixels for more stable tracking
                y_center = int(np.mean(hot_pixels[0]))
                x_center = int(np.mean(hot_pixels[1]))
                return (x_center, y_center)
            else:
                logger.warning("No hot pixels found in image")
                return (None, None)
                
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            return (None, None)
    
    def calculate_horizontal_offset(self, image_path: str, hot_x: int) -> float:
        """
        Calculate the horizontal offset of the hottest pixel from image center.
        
        Args:
            image_path: Path to the image (to get dimensions)
            hot_x: X coordinate of the hottest pixel
            
        Returns:
            float: Normalized offset from center (-0.5 to 0.5)
                  Negative = left of center, Positive = right of center
        """
        try:
            img = Image.open(image_path)
            width = img.width
            center_x = width / 2.0
            
            # Calculate offset as fraction of image width
            offset = (hot_x - center_x) / width
            return offset
        except Exception as e:
            logger.error(f"Error calculating offset: {e}")
            return 0.0
    
    def calculate_hot_pixel_coverage(self, image_path: str) -> float:
        """
        Calculate what percentage of the image is covered by hot pixels.
        Used to detect when pupper has reached the person (hot region is large).
        
        Args:
            image_path: Path to the thermal image
            
        Returns:
            float: Fraction of image covered by hot pixels (0.0 to 1.0)
        """
        try:
            img = Image.open(image_path)
            img_array = np.array(img)
            
            # Handle different image formats
            if len(img_array.shape) == 2:
                # Grayscale image
                intensity = img_array.astype(np.float32)
            elif len(img_array.shape) == 3:
                # Color image - use same heat scoring as find_hottest_pixel
                img_rgb = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
                h, s, v = img_rgb[:, :, 0], img_rgb[:, :, 1], img_rgb[:, :, 2]
                
                red_mask = (h < 30) | (h > 150)
                heat_score = v.astype(np.float32) * (1.0 + s.astype(np.float32) / 255.0)
                heat_score[red_mask] *= 1.5
                intensity = heat_score
            else:
                return 0.0
            
            # Calculate threshold based on max intensity
            max_intensity = np.max(intensity)
            if max_intensity == 0:
                return 0.0
            
            threshold = max_intensity * HOT_PIXEL_INTENSITY_THRESHOLD
            
            # Count hot pixels
            hot_pixel_count = np.sum(intensity >= threshold)
            total_pixels = intensity.size
            
            coverage = hot_pixel_count / total_pixels
            return coverage
            
        except Exception as e:
            logger.error(f"Error calculating hot pixel coverage: {e}")
            return 0.0
    
    def check_reached_target(self, image_path: str) -> bool:
        """
        Check if pupper has reached the target (person is very close).
        
        Args:
            image_path: Path to the thermal image
            
        Returns:
            bool: True if target is reached (hot region covers enough of image)
        """
        coverage = self.calculate_hot_pixel_coverage(image_path)
        logger.info(f"Hot pixel coverage: {coverage:.1%}")
        
        if coverage >= HOT_PIXEL_COVERAGE_THRESHOLD:
            return True
        return False
    
    def handle_reached_target(self):
        """
        Handle the end state when pupper has reached the person.
        Stops movement and celebrates!
        """
        if not self.reached_target:
            logger.info("🎉🎉🎉 TARGET REACHED! Person found! 🎉🎉🎉")
            self.reached_target = True
            
            # Stop and celebrate
            self.pupper.stop()
            self.pupper.bark()
            time.sleep(0.5)
            self.pupper.bark()
            self.pupper.wiggle()
            
            logger.info("🐕 Rescue Pupper has found the person!")
        else:
            # Stay stopped
            self.pupper.stop()
    
    def rotate_to_center(self, offset: float):
        """
        Rotate Pupper to center the hottest region using turn_left/turn_right methods.
        When centered, move forward to approach the target.
        
        Args:
            offset: Normalized horizontal offset (-0.5 to 0.5)
                  Negative = hot region is left of center, Positive = right of center
        """
        if abs(offset) < CENTER_THRESHOLD:
            # Already centered - move forward to approach target
            if not self.centered:
                logger.info("🎯 Hot region is centered! Moving forward to approach...")
                self.centered = True
                self.pupper.bark()
            
            # Move forward toward the heat source
            logger.info("➡️ Moving forward toward target...")
            self.pupper.move_forward()
            return
        
        # Reset centered flag when we need to rotate
        self.centered = False
        
        # Only rotate if offset is significant enough
        if abs(offset) < MIN_ROTATION_OFFSET:
            # Too small to rotate, just stop
            self.pupper.stop()
            return
        
        # Determine rotation direction
        # Negative offset means hot region is to the left, so rotate RIGHT to point camera right (bringing left-side hot region toward center)
        # Positive offset means hot region is to the right, so rotate LEFT to point camera left (bringing right-side hot region toward center)
        if offset < 0:
            logger.info(f"Hot region LEFT of center (offset: {offset:.3f}), rotating RIGHT")
            self.pupper.turn_right()
        else:
            logger.info(f"Hot region RIGHT of center (offset: {offset:.3f}), rotating LEFT")
            self.pupper.turn_left()
    
    def process_image(self, image_path: str):
        """
        Process a thermal image and adjust Pupper orientation.
        
        Args:
            image_path: Path to the thermal image to process
        """
        logger.info(f"Processing image: {os.path.basename(image_path)}")
        
        # Check if we've reached the target (end state)
        if self.check_reached_target(image_path):
            self.handle_reached_target()
            return
        
        # Reset reached_target if coverage drops (person moved away)
        if self.reached_target:
            logger.info("Target moved away, resuming tracking...")
            self.reached_target = False
        
        # Find hottest pixel
        hot_x, hot_y = self.find_hottest_pixel(image_path)
        
        if hot_x is None or hot_y is None:
            logger.warning("Could not find hottest pixel, skipping")
            return
        
        logger.info(f"Hot pixel found at ({hot_x}, {hot_y})")
        
        # Calculate horizontal offset
        offset = self.calculate_horizontal_offset(image_path, hot_x)
        logger.info(f"Horizontal offset from center: {offset:.3f}")
        
        # Rotate to center
        self.rotate_to_center(offset)
    
    def run(self):
        """Main loop to monitor and process thermal images."""
        logger.info("Starting thermal tracking loop...")
        logger.info(f"Monitoring directory: {SAVED_IMAGES_DIR}")
        logger.info(f"Image check interval: {IMAGE_CHECK_INTERVAL}s")
        logger.info(f"Center threshold: {CENTER_THRESHOLD}")
        logger.info(f"Target reached threshold: {HOT_PIXEL_COVERAGE_THRESHOLD:.0%} hot pixel coverage")
        
        try:
            while True:
                # Get latest image
                latest_image = self.get_latest_image()
                
                if latest_image is None:
                    logger.debug("No images found, waiting...")
                    time.sleep(IMAGE_CHECK_INTERVAL)
                    continue
                
                # Check if this is a new image (different from last processed)
                if latest_image != self.last_image_path:
                    logger.info(f"New image detected: {os.path.basename(latest_image)}")
                    self.last_image_path = latest_image
                    self.process_image(latest_image)
                else:
                    # Same image - re-process to continue adjusting rotation
                    # This allows continuous rotation until centered
                    current_time = time.time()
                    if current_time - self.last_image_time > 0.5:  # Re-process every 0.5 seconds
                        self.last_image_time = current_time
                        self.process_image(latest_image)
                
                time.sleep(IMAGE_CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("Shutting down thermal tracker...")
            self.pupper.stop()
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self.pupper.stop()
            raise


def main():
    """Entry point for the thermal tracker."""
    # Ensure saved_images directory exists
    os.makedirs(SAVED_IMAGES_DIR, exist_ok=True)
    
    tracker = ThermalTracker()
    tracker.run()


if __name__ == '__main__':
    main()

