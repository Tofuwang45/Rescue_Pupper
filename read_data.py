#!/usr/bin/env python3
"""
Serial Port Reader
Reads data from a serial port and prints it to the terminal.
"""

import serial
import sys
import argparse
from datetime import datetime


def read_serial(port, baudrate=115200, timeout=1):
    """
    Read data from serial port and print to terminal.
    
    Args:
        port: Serial port name (e.g., '/dev/ttyUSB0', 'COM3')
        baudrate: Communication speed (default: 115200)
        timeout: Read timeout in seconds (default: 1)
    """
    try:
        # Open serial port
        ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        print(f"Connected to {port} at {baudrate} baud")
        print(f"Press Ctrl+C to stop\n")
        print("-" * 50)
        
        # Continuously read and print data
        while True:
            if ser.in_waiting > 0:
                # Read a line from serial port
                data = ser.readline()
                
                try:
                    # Try to decode as UTF-8 string
                    decoded_data = data.decode('utf-8').rstrip()
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"[{timestamp}] {decoded_data}")
                except UnicodeDecodeError:
                    # If decoding fails, print as hex
                    hex_data = ' '.join([f'{b:02x}' for b in data])
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"[{timestamp}] HEX: {hex_data}")
                    
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print(f"Closed connection to {port}")


def list_serial_ports():
    """List available serial ports."""
    import serial.tools.list_ports
    
    ports = serial.tools.list_ports.comports()
    
    if not ports:
        print("No serial ports found")
        return
    
    print("Available serial ports:")
    for port in ports:
        print(f"  {port.device}")
        if port.description:
            print(f"    Description: {port.description}")
        if port.manufacturer:
            print(f"    Manufacturer: {port.manufacturer}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Read data from a serial port and print to terminal',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python serial_reader.py /dev/ttyUSB0
  python serial_reader.py COM3 -b 9600
  python serial_reader.py --list
        """
    )
    
    parser.add_argument('port', nargs='?', help='Serial port name (e.g., /dev/ttyUSB0, COM3)')
    parser.add_argument('-b', '--baudrate', type=int, default=115200,
                        help='Baud rate (default: 115200)')
    parser.add_argument('-t', '--timeout', type=float, default=1.0,
                        help='Read timeout in seconds (default: 1.0)')
    parser.add_argument('-l', '--list', action='store_true',
                        help='List available serial ports')
    
    args = parser.parse_args()
    
    if args.list:
        list_serial_ports()
        sys.exit(0)
    
    if not args.port:
        parser.print_help()
        print("\n")
        list_serial_ports()
        sys.exit(1)
    
    read_serial(args.port, args.baudrate, args.timeout)


if __name__ == "__main__":
    main()