# EPlumber

A Python-based IoT automation system that monitors sensors via MQTT and HTTP, evaluates rules, and triggers actions. Designed for home automation scenarios like managing water heating based on solar power production, temperature, and time conditions.

![ScreenShot](screenshot.png)

## Architecture

- **Sensors**: Collect data from various sources (MQTT topics, HTTP endpoints, system time)
- **Rules**: Define automation logic with multiple test conditions  
- **Actions**: HTTP-based commands to control devices
- **Main loop**: Continuously evaluates rules and triggers actions when conditions are met

## Hardware Compatibility

This project is used with:
- **EmonPi** energy monitoring system with MQTT broker for solar monitoring (from [Open Energy Monitor](https://openenergymonitor.org/)) running on Raspberry Pi
- **OpenEVSE** charging station for electric vehicle monitoring
- **Shelly switches** and temperature sensors for water heater control 
- **Shelly plugs** for battery charger management

These hardware solutions could be run on local network, with http and mqtt support.


## Installation

1. Clone the repository:
```bash
git clone https://github.com/freddez/eplumber
cd eplumber
```

2. Install dependencies using [uv](https://docs.astral.sh/uv/):
```bash
uv sync
```

## Configuration

Create an `eplumber.json` configuration file in the project directory or user config directory:

```json
{
  "global": {
    "recipients": ["your-email@example.com"]
  },
  "mqtt": {
    "host": "your-mqtt-broker",
    "port": 1883,
    "username": "mqtt-user",
    "password": "your-password"
  },
  "sensors": [
    {
      "name": "consumption",
      "route": "emon/emonpi/power1"
    },
    {
      "name": "tank_temp",
      "json_path": "'tC'",
      "route": "shelly/status/temperature:100"
    },
    {
      "name": "tank_switch_status",
      "type": "http",
      "route": "http://192.168.0.15/rpc/Shelly.GetStatus",
      "json_path": "'switch:0'.output",
      "return_type": "bool"
    },
    {
      "name": "vehicle_connected",
      "route": "emon/openevse/vehicle",
      "return_type": "bool"
    }
  ],
  "actions": [
    {
      "name": "switch_on_tank",
      "route": "http://192.168.0.15/relay/0?turn=on"
    },
    {
      "name": "switch_off_tank",
      "route": "http://192.168.0.15/relay/0?turn=off"
    }
  ],
  "rules": [
    {
      "name": "Solar to Water Heater",
      "tests": [
        ["tank_temp", "<", 65],
        ["tank_switch_status", "==", false],
        ["consumption", "<", -1700]
      ],
      "action": "switch_on_tank"
    },
    {
      "name": "Night Heating",
      "tests": [
        ["tank_temp", "<", 55],
        ["time", ">", "22:00"],
        ["tank_switch_status", "==", false]
      ],
      "action": "switch_on_tank"
    },
    {
      "name": "Tank Full - Turn Off",
      "tests": [
        ["tank_switch_status", "==", true],
        ["time", ">", "08:00"],
        ["time", "<", "21:00"],
        ["tank_temp", ">", 68]
      ],
      "action": "switch_off_tank"
    }
  ]
}
```

### Configuration Sections

- **global**: Email recipients for notifications
- **mqtt**: MQTT broker connection settings
- **sensors**: Define data sources (MQTT topics, HTTP endpoints)
- **actions**: HTTP commands to control devices
- **rules**: Automation logic with test conditions and actions

### Sensor Types

- **MQTT sensors**: Subscribe to MQTT topics for real-time data
- **HTTP sensors**: Poll HTTP endpoints for device status
- **Time sensors**: Built-in time source for schedule-based rules

### Rule Operators

Support for comparison operators: `<`, `<=`, `>`, `>=`, `==`, `!=`

## Usage

Run the application:

```bash
make run
# or
uv run main.py
```

For debugging:
```bash
make rundbg
```

## Example Use Cases

### Solar Water Heating
Automatically turn on water heater when:
- Tank temperature is below threshold
- Solar panels are producing excess power (negative consumption)
- Tank is currently off

### Smart Charging
Control battery chargers based on:
- Power consumption levels
- Time of day restrictions
- Device connection status

### Temperature Management
Monitor and control heating based on:
- Current temperature readings
- Time-based schedules
- System status checks


## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
