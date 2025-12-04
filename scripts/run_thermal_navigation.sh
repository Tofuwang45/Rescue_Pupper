#!/bin/bash
# Launch script for Thermal Navigation Coordinator
# This script starts the thermal navigation system

echo "=========================================="
echo "Thermal Navigation Coordinator"
echo "=========================================="
echo ""
echo "Starting thermal navigation system..."
echo ""
echo "Prerequisites:"
echo "  1. ROS2 system must be running (ros2 launch lab_7.launch.py)"
echo "  2. Thermal camera must be saving images to saved_images/"
echo "  3. ToF sensor must be connected to /dev/ttyACM1"
echo ""
echo "Press Ctrl+C to stop the system"
echo ""
echo "=========================================="
echo ""

# Change to script directory
cd "$(dirname "$0")"

# Run the coordinator
python3 thermal_navigation_coordinator.py
