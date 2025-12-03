#!/usr/bin/env python3
"""
Sensor Monitor Node
Monitors serial sensor data and triggers robot actions based on sensor readings.
When data is received from sensor 1 (non-error), the robot will bark.
"""

import rclpy
from rclpy.node import Node
import serial
import serial.tools.list_ports
import sys
import os
from datetime import datetime
import threading
import queue

# Add karel to path
sys.path.append(os.path.dirname(__file__))
import pupper_llm.karel.karel as karel


class SensorMonitorNode(Node):
    """ROS2 node that monitors serial sensor and triggers robot actions."""
    
    def __init__(self, port='/dev/ttyACM0', baudrate=115200, timeout=1):
        super().__init__('sensor_monitor_node')
        
        # Initialize KarelPupper for robot control
        self.pupper = karel.KarelPupper()
        
        # Serial port configuration
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_port = None
        self.monitoring = False
        
        # Thread for serial monitoring
        self.monitor_thread = None
        
        # Queue for thread-safe communication between serial thread and ROS2 thread
        self.bark_queue = queue.Queue()
        
        # Track current state - should we be barking?
        self.should_bark = False
        self.last_was_error = True  # Start assuming error state
        
        # Create a timer to check for bark requests
        self.create_timer(0.1, self.check_bark_queue)
        
        self.get_logger().info(f'Sensor Monitor Node initialized')
        self.get_logger().info(f'Will monitor {port} at {baudrate} baud')
        self.get_logger().info(f'Behavior: Error → Walk Forward | Valid → Bark + Avoid Obstacle (Left 90° → Forward → Right 90°)')
        
    def start_monitoring(self):
        """Start monitoring the serial port in a separate thread."""
        try:
            # Open serial port
            self.serial_port = serial.Serial(
                self.port, 
                baudrate=self.baudrate, 
                timeout=self.timeout
            )
            self.get_logger().info(f'Connected to {self.port} at {self.baudrate} baud')
            
            # Start monitoring thread
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            
            self.get_logger().info('Serial monitoring started')
            
        except serial.SerialException as e:
            self.get_logger().error(f'Error opening serial port: {e}')
            self._list_available_ports()
            sys.exit(1)
    
    def _monitor_loop(self):
        """Monitor serial port and process incoming data."""
        self.get_logger().info('Monitoring loop started. Press Ctrl+C to stop.')
        
        while self.monitoring and rclpy.ok():
            try:
                if self.serial_port and self.serial_port.in_waiting > 0:
                    # Read a line from serial port
                    data = self.serial_port.readline()
                    
                    try:
                        # Try to decode as UTF-8 string
                        decoded_data = data.decode('utf-8').rstrip()
                        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        
                        # Extract only Sensor 1 data from format: "Sensor 1: value | Sensor 2: value"
                        sensor1_data = self._extract_sensor1_data(decoded_data)
                        
                        if sensor1_data:
                            # Check if this is valid sensor data (not an error message)
                            is_valid = self._is_valid_sensor_data(sensor1_data)
                            
                            # Log the data with status indicator
                            status = "✓ Valid" if is_valid else "✗ Error"
                            self.get_logger().info(f'[{timestamp}] Sensor 1: {sensor1_data} ({status})')
                            
                            if is_valid:
                                # Valid data detected - obstacle avoidance maneuver
                                if self.last_was_error:
                                    self.get_logger().info('🔔 Sensor 1 recovered from error!')
                                self.get_logger().info('✓ Valid data - Obstacle detected! Starting avoidance maneuver...')
                                self.should_bark = True
                                self.bark_queue.put('avoid_obstacle')
                                self.last_was_error = False
                            else:
                                # Error detected - walk forward
                                if not self.last_was_error:
                                    self.get_logger().info('✗ Error detected - Walking Forward!')
                                self.should_bark = False
                                # Clear any pending bark commands
                                while not self.bark_queue.empty():
                                    try:
                                        self.bark_queue.get_nowait()
                                    except queue.Empty:
                                        break
                                # Walk forward when error
                                self.bark_queue.put('walk_forward')
                                self.last_was_error = True
                        else:
                            # Log raw data if we couldn't parse sensor 1
                            self.get_logger().debug(f'[{timestamp}] Raw: {decoded_data}')
                        
                    except UnicodeDecodeError:
                        # If decoding fails, print as hex
                        hex_data = ' '.join([f'{b:02x}' for b in data])
                        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        self.get_logger().warning(f'[{timestamp}] HEX: {hex_data}')
                        
            except Exception as e:
                self.get_logger().error(f'Error in monitor loop: {e}')
                
    def _extract_sensor1_data(self, data_str):
        """
        Extract only Sensor 1 data from the combined sensor string.
        
        Format: "Sensor 1: value | Sensor 2: value" -> returns "value"
        
        Args:
            data_str: The full decoded string from serial port
            
        Returns:
            str: Sensor 1 data only, or None if not found
        """
        # Look for "Sensor 1:" pattern
        if 'Sensor 1:' in data_str:
            # Split by pipe to separate sensors
            parts = data_str.split('|')
            
            # Find the part with Sensor 1
            for part in parts:
                if 'Sensor 1:' in part:
                    # Extract everything after "Sensor 1:"
                    sensor1_value = part.split('Sensor 1:')[1].strip()
                    return sensor1_value
        
        return None
    
    def _is_valid_sensor_data(self, data_str):
        """
        Determine if the received data is valid sensor data (non-error) from sensor 1.
        
        Args:
            data_str: The decoded string from sensor 1
            
        Returns:
            bool: True if valid sensor 1 data, False if error message
        """
        # Convert to lowercase for case-insensitive checking
        data_lower = data_str.lower()
        
        # List of error keywords to filter out
        error_keywords = [
            'error',
            'fail',
            'timeout',
            'invalid',
            'warning',
            'exception',
            'not found',
            'disconnected',
        ]
        
        # Check if any error keyword is in the data
        for keyword in error_keywords:
            if keyword in data_lower:
                return False
        
        # If data is not empty and doesn't contain error keywords, it's valid
        return len(data_str.strip()) > 0
    
    def check_bark_queue(self):
        """Timer callback to check for commands and execute them safely in ROS2 thread."""
        try:
            # Process all pending commands from the queue
            while not self.bark_queue.empty():
                command = self.bark_queue.get_nowait()
                
                if command == 'avoid_obstacle':
                    # Obstacle detected - perform avoidance maneuver
                    self.get_logger().info('🐕 Barking! Obstacle detected!')
                    self.pupper.bark()
                    
                    # Step 1: Turn left 90 degrees
                    self.get_logger().info('↰ Step 1: Turning left 90°')
                    self.pupper.turn_left()
                    
                    # Step 2: Walk forward a moderate amount
                    self.get_logger().info('➡️ Step 2: Walking forward')
                    self.pupper.move_forward()
                    
                    # Step 3: Turn right 90 degrees (back to original direction)
                    self.get_logger().info('↱ Step 3: Turning right 90° (returning to original heading)')
                    self.pupper.turn_right()
                    
                    self.get_logger().info('✅ Obstacle avoidance maneuver complete!')
                    
                elif command == 'walk_forward':
                    # Error detected - walk forward
                    self.get_logger().info('➡️ Walking forward (no obstacle)')
                    self.pupper.move_forward()
                    
        except queue.Empty:
            pass
        except Exception as e:
            self.get_logger().error(f'Error executing command: {e}')
    
    def _list_available_ports(self):
        """List available serial ports for debugging."""
        ports = serial.tools.list_ports.comports()
        
        if not ports:
            self.get_logger().warning('No serial ports found')
            return
        
        self.get_logger().info('Available serial ports:')
        for port in ports:
            self.get_logger().info(f'  {port.device}')
            if port.description:
                self.get_logger().info(f'    Description: {port.description}')
            if port.manufacturer:
                self.get_logger().info(f'    Manufacturer: {port.manufacturer}')
    
    def stop_monitoring(self):
        """Stop monitoring and close serial port."""
        self.monitoring = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.get_logger().info(f'Closed connection to {self.port}')


def main(args=None):
    """Main entry point."""
    rclpy.init(args=args)
    
    # Create sensor monitor node for SENSOR 1 ONLY
    # Sensor 1 is connected to /dev/ttyACM0 (Arduino)
    # This will only respond to data from sensor 1 and ignore other sensors
    node = SensorMonitorNode(port='/dev/ttyACM0', baudrate=115200)
    
    try:
        # Start monitoring
        node.start_monitoring()
        
        # Spin the node
        rclpy.spin(node)
        
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down by user request')
    except Exception as e:
        node.get_logger().error(f'Error during execution: {e}')
    finally:
        node.stop_monitoring()
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
