# Thermal Navigation Coordinator

## Overview

The Thermal Navigation Coordinator orchestrates autonomous navigation for the rescue pupper by combining thermal tracking and obstacle avoidance. The system operates in a continuous loop:

1. **Thermal Centering Phase**: Center pupper on the hottest thermal signature
2. **Navigation Phase**: Move forward while avoiding obstacles
3. **Repeat**: Return to step 1 for continuous autonomous navigation

## System Architecture

### Components

1. **thermal_navigation_coordinator.py** (Main Coordinator)
   - Orchestrates the overall navigation loop
   - Manages state transitions between centering and navigation phases
   - Integrates thermal tracking and sensor monitoring

2. **thermal_tracker.py** (Thermal Tracking Module)
   - Monitors saved_images/ directory for thermal images
   - Identifies the hottest region in thermal images
   - Rotates pupper to center on thermal target
   - CENTER_THRESHOLD: 0.20 (middle 40% of camera considered "centered")

3. **sensor_monitor.py** (Obstacle Avoidance Module)
   - Monitors Time of Flight (ToF) sensor on /dev/ttyACM1
   - Detects obstacles in the path
   - Moves left when obstacle detected
   - Moves forward when path is clear

## Behavior Flow

```
┌─────────────────────────────────────────────┐
│         START NAVIGATION CYCLE              │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│  PHASE 1: THERMAL CENTERING                 │
│  - Get latest thermal image                 │
│  - Find hottest region                      │
│  - Calculate offset from center             │
│  - Rotate left/right until centered         │
│  - Bark when centered! 🐕                   │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│  PHASE 2: FORWARD NAVIGATION                │
│  - Monitor ToF sensor continuously          │
│  - IF obstacle detected:                    │
│    • Bark! 🐕                               │
│    • Move left until path is clear          │
│  - ELSE (path clear):                       │
│    • Move forward                           │
│  - Continue for FORWARD_MOVE_DURATION       │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
           [Return to Phase 1]
```

## Configuration Parameters

### thermal_navigation_coordinator.py
```python
CENTERING_TIMEOUT = 10.0        # Max time to spend centering (seconds)
FORWARD_MOVE_DURATION = 2.0     # How long to move forward before re-centering
CENTER_THRESHOLD = 0.20         # Offset threshold for "centered" (20% = middle 40%)
MIN_ROTATION_OFFSET = 0.02      # Minimum offset to trigger rotation (2%)
```

### thermal_tracker.py
```python
IMAGE_CHECK_INTERVAL = 0.5      # Check for new images every 0.5 seconds
CENTER_THRESHOLD = 0.20         # Middle 40% of camera considered centered
MIN_ROTATION_OFFSET = 0.02      # Minimum offset to rotate (2% of image width)
```

### sensor_monitor.py
```python
SENSOR_PORT = '/dev/ttyACM1'    # Serial port for ToF sensor
BAUDRATE = 115200               # Serial communication speed
```

## Usage

### Running the Coordinator

The coordinator is the main entry point for autonomous thermal navigation:

```bash
# Start the full system with ROS2 launch
ros2 launch lab_7.launch.py

# In a separate terminal, run the coordinator
python3 thermal_navigation_coordinator.py
```

### Running Components Separately

You can also run the components independently for testing:

**Thermal Tracker Only** (continuous centering):
```bash
python3 thermal_tracker.py
```

**Sensor Monitor Only** (obstacle avoidance):
```bash
python3 sensor_monitor.py
```

## Sensor Data Format

The ToF sensor outputs data in the following format:
```
Sensor 1: <value> | Sensor 2: <value>
```

- **Valid Data** (numeric reading): Obstacle detected
- **Error/Invalid**: Path is clear (sensor out of range)

## Operation Modes

### 1. Thermal Centering Mode
- **Trigger**: Start of each cycle or after forward navigation
- **Duration**: Up to CENTERING_TIMEOUT (10s)
- **Success**: Thermal target centered within ±20% of image center
- **Failure**: Timeout reached without centering
- **Output**: Bark when successfully centered

### 2. Navigation Mode
- **Trigger**: After successful thermal centering
- **Duration**: FORWARD_MOVE_DURATION (2s)
- **Behaviors**:
  - Clear path → Move forward
  - Obstacle detected → Bark, move left until clear, then forward
- **Output**: Progress logged every 1 second

## Troubleshooting

### No Thermal Images Found
- Ensure thermal camera is running and saving images to `saved_images/`
- Check that `saved_images/` directory exists
- Verify thermal camera node is active in ROS2 launch

### Sensor Not Responding
- Check serial port connection: `ls /dev/ttyACM*`
- Verify sensor is connected to `/dev/ttyACM1`
- Test sensor manually: `python3 sensor_monitor.py`
- Check baud rate matches sensor configuration (115200)

### Pupper Not Moving
- Verify KarelPupper connection in logs
- Check ROS2 nodes are running: `ros2 node list`
- Ensure neural controller is active
- Test pupper commands manually using karel.py

### Constant Rotation/No Centering
- Check CENTER_THRESHOLD value (current: 0.20)
- Verify thermal images have clear hot spot
- Review thermal image quality in saved_images/
- Increase CENTER_THRESHOLD for more tolerance

## Log Output

The coordinator provides detailed logging for each phase:

```
================================================================
CYCLE 1
================================================================

================================================================
PHASE 1: CENTERING ON THERMAL TARGET
================================================================
Centering... offset: -0.125, centered: False
Rotating right (offset: -0.125)
🎯 Target CENTERED! (offset: 0.015)

================================================================
PHASE 2: NAVIGATING FORWARD WITH OBSTACLE AVOIDANCE
================================================================
Connected to sensor at /dev/ttyACM1
Sensor: CLEAR, Avoiding: False
➡️ Moving forward
🚧 OBSTACLE DETECTED! Moving left...
✓ Path clear! Moving forward...
✅ Forward navigation complete (2.0s)

Cycle 1 complete. Pausing before next cycle...
```

## Safety Considerations

- The system continuously monitors for obstacles during forward motion
- Pupper will stop and avoid obstacles before collision
- Manual override available via Ctrl+C at any time
- Coordinator stops all motors on shutdown
- Recommended to test in open area first

## Future Enhancements

- Adaptive FORWARD_MOVE_DURATION based on obstacle density
- Multi-obstacle tracking and path planning
- Temperature threshold filtering for thermal targets
- Integration with mapping/SLAM for navigation history
- Autonomous return-to-base after target reached

## Files Modified

- `thermal_tracker.py`: Enabled rotation commands (uncommented turn_left/turn_right)
- `sensor_monitor.py`: Updated to continuously move left until clear
- `thermal_navigation_coordinator.py`: New main coordinator script

## Dependencies

- ROS2 (robot control)
- pyserial (sensor communication)
- OpenCV/PIL (image processing)
- numpy (numerical operations)
- pupper_llm.karel (robot control interface)
