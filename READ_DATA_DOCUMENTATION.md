# Serial Data Reader Documentation

## Overview
`read_data.py` is a Python script that reads data from Arduino or any other serial device and displays it in the terminal with timestamps.

## How It Works

### 1. Serial Communication
- Opens a serial connection to the specified COM port (e.g., COM3, COM4)
- Uses the `pyserial` library to handle low-level serial communication
- Continuously monitors the serial buffer for incoming data

### 2. Data Processing Flow
```
Arduino → Serial Port → Python Script → Terminal Display
```

**Step-by-step:**
1. Arduino sends data via serial communication (e.g., `Serial.println()`)
2. Data arrives at the computer's COM port
3. Python script reads data line-by-line from the serial buffer
4. Each line is decoded from bytes to UTF-8 text
5. Timestamp is added and data is printed to terminal

### 3. Key Components

#### Serial Connection
```python
ser = serial.Serial(port, baudrate=115200, timeout=1)
```
- **port**: COM port identifier (COM3, COM4, etc.)
- **baudrate**: Communication speed (must match Arduino's baud rate)
- **timeout**: Max time to wait for data (1 second)

#### Data Reading Loop
```python
while True:
    if ser.in_waiting > 0:
        data = ser.readline()
```
- Checks if data is available in the buffer (`in_waiting`)
- Reads one complete line (until newline character)
- Non-blocking - only reads when data is present

#### Data Decoding
```python
decoded_data = data.decode('utf-8').rstrip()
```
- Converts bytes to UTF-8 string
- Removes trailing whitespace/newlines
- Falls back to hex display if decoding fails

#### Timestamp
```python
timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
print(f"[{timestamp}] {decoded_data}")
```
- Records exact time when data is received
- Format: HH:MM:SS.mmm (milliseconds precision)

## Usage Examples

### List Available Ports
```bash
python read_data.py --list
```
Shows all connected serial devices with descriptions.

### Read from Arduino (Default Baud Rate)
```bash
python read_data.py COM3
```
Connects to COM3 at 115200 baud (default).

### Custom Baud Rate
```bash
python read_data.py COM3 -b 9600
```
Use this if your Arduino uses `Serial.begin(9600)`.

### Custom Timeout
```bash
python read_data.py COM3 -t 2.0
```
Increases timeout to 2 seconds for slower devices.

## Common Arduino Setup

For this script to work, your Arduino code should use:

```cpp
void setup() {
    Serial.begin(115200);  // Must match Python baudrate
}

void loop() {
    Serial.println("Sensor value: 123");  // Data appears in terminal
    delay(1000);
}
```

## Troubleshooting

### "Error opening serial port"
- **Cause**: Port doesn't exist or is already in use
- **Fix**: 
  - Check port name with `--list` option
  - Close Arduino IDE Serial Monitor
  - Unplug and replug Arduino

### No Data Appearing
- **Cause**: Baud rate mismatch
- **Fix**: Match baudrate in script with `Serial.begin()` value in Arduino

### Garbled Text
- **Cause**: Wrong baud rate
- **Fix**: Try common rates: 9600, 57600, 115200

### "HEX" Output Instead of Text
- **Cause**: Non-UTF-8 data or corrupted transmission
- **Fix**: Check Arduino is sending text, verify baud rate

## Exit the Program
Press `Ctrl+C` to stop reading and close the connection gracefully.

## Requirements
- Python 3.x
- `pyserial` package (`pip install pyserial`)
- Arduino or serial device connected via USB
