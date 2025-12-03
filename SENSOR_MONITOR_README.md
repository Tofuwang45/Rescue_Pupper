# Sensor Monitor with Bark Trigger

## Overview
This ROS2 node monitors serial sensor data from Sensor 1 (Arduino/ESP32) and triggers the robot to bark when valid (non-error) data is received.

## Features
- **Continuous monitoring** of serial port data
- **Automatic bark trigger** when valid sensor data is detected
- **Error filtering** - ignores error messages and only responds to valid sensor readings
- **Threaded operation** - runs serial monitoring in background while maintaining ROS2 functionality
- **Timestamped logging** - all sensor data is logged with millisecond precision

## Quick Start

### 1. Check Available Serial Ports
```bash
python read_data.py -l
```

This will show you available devices like:
- `/dev/ttyACM0` - Arduino (Sensor 1)
- `/dev/ttyACM1` - ESP32
- `/dev/ttyAMA10` - Other device

### 2. Run the Sensor Monitor
```bash
# For Arduino on /dev/ttyACM0
python sensor_monitor.py

# Or run as ROS2 node
ros2 run . sensor_monitor.py
```

### 3. Configure Different Port (Optional)
Edit `sensor_monitor.py` line 176 to change the port:
```python
node = SensorMonitorNode(port='/dev/ttyACM1', baudrate=115200)
```

## How It Works

### Data Flow
```
Arduino/Sensor → Serial Port (/dev/ttyACM0) → Sensor Monitor Node → KarelPupper.bark()
```

### Valid Data Detection
The system considers data **valid** (and triggers bark) when:
- ✓ Data is successfully decoded as UTF-8
- ✓ Data is not empty
- ✓ Data does NOT contain error keywords like:
  - "error"
  - "fail"
  - "timeout"
  - "invalid"
  - "warning"
  - "exception"
  - "not found"
  - "disconnected"

### Example Arduino Code
For the sensor to work correctly, your Arduino should send data like:
```cpp
void setup() {
    Serial.begin(115200);  // Must match Python baudrate
}

void loop() {
    // Read sensor value (e.g., temperature, distance, etc.)
    int sensorValue = analogRead(A0);
    
    // Send valid sensor data - this will trigger bark
    Serial.print("Sensor reading: ");
    Serial.println(sensorValue);
    
    delay(1000);  // Send data every second
}
```

## Integration with Existing System

### Option 1: Standalone Mode
Run independently for testing:
```bash
python sensor_monitor.py
```

### Option 2: Launch File Integration
Add to your existing launch file (e.g., `lab_7.launch.py`):
```python
sensor_monitor_node = Node(
    package='rescue_pupper',
    executable='sensor_monitor.py',
    name='sensor_monitor',
    output='screen',
)

# Add to nodes list
nodes.append(sensor_monitor_node)
```

### Option 3: Script Integration
Add to `scripts/run_full_system.sh`:
```bash
python "$PROJECT_ROOT/sensor_monitor.py" &
```

## Customization

### Adjust Valid Data Filtering
Edit the `_is_valid_sensor_data()` method in `sensor_monitor.py`:
```python
def _is_valid_sensor_data(self, data_str):
    # Add your custom validation logic here
    # For example, check if data contains numbers:
    if any(char.isdigit() for char in data_str):
        return True
    return False
```

### Change Robot Action
Replace the bark action with other commands in the `_monitor_loop()` method:
```python
if self._is_valid_sensor_data(decoded_data):
    # Instead of barking, try:
    # self.pupper.wiggle()
    # self.pupper.dance()
    # self.pupper.move_forward()
    self.pupper.bark()
```

### Adjust Serial Settings
Modify when creating the node:
```python
node = SensorMonitorNode(
    port='/dev/ttyACM0',    # Serial port
    baudrate=115200,         # Communication speed
)
```

## Troubleshooting

### "Error opening serial port"
**Solution:** Check available ports and update the port parameter:
```bash
python read_data.py -l
```

### Permission Denied
**Solution:** Add user to dialout group:
```bash
sudo usermod -a -G dialout pi
# Log out and back in
```

### No Bark Response
**Possible causes:**
1. Data contains error keywords → Check sensor output with `read_data.py`
2. Data is not being received → Verify baud rate matches Arduino
3. Serial port is wrong → Use `read_data.py -l` to find correct port

### Robot Not Responding
**Solution:** Ensure ROS2 system is running:
```bash
# Check if ROS2 nodes are active
ros2 node list

# Restart robot controller
ros2 launch lab_7.launch.py
```

## Testing

### Test 1: Verify Sensor Data
```bash
# Monitor raw sensor data first
python read_data.py /dev/ttyACM0
```

### Test 2: Test Bark Function
```bash
# In Python
python3 -c "import karel_lab6; k = karel_lab6.KarelPupper(); k.bark()"
```

### Test 3: Full System Test
```bash
# Run sensor monitor and send test data from Arduino
python sensor_monitor.py
```

## Files Modified/Created
- `sensor_monitor.py` - **NEW** - Main ROS2 node for sensor monitoring
- `read_data.py` - Updated with better error handling
- `SENSOR_MONITOR_README.md` - **NEW** - This documentation

## System Requirements
- ROS2 (Humble or later)
- Python 3.11+
- pyserial library
- pygame (for sound)
- Arduino or compatible serial device

## Notes
- The monitoring runs in a background thread to avoid blocking ROS2
- All sensor data is logged to ROS2 logger for debugging
- The bark sound is played through pygame mixer
- System uses the same KarelPupper class as other lab components
