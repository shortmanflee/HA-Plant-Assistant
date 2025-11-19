# Plant Assistant for Home Assistant

A comprehensive Home Assistant custom component for intelligent plant care and monitoring. Track your plants' health, automate irrigation, monitor environmental conditions, and ensure optimal growing conditions with advanced sensors and automations.

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

## Features

- 🌱 **Plant Monitoring**: Track individual plants with sensors for moisture, light, temperature, humidity, and conductivity
- 💡 **Daily Light Integral (DLI)**: Automatic calculation of DLI and PPFD (Photosynthetic Photon Flux Density) for optimal light management
- 💧 **Irrigation Management**: Automated irrigation zone control with scheduling and soil moisture monitoring
- 📊 **Comprehensive Sensors**: Monitor plant health with problem detection, status alerts, and environmental thresholds
- 🔗 **OpenPlantBook Integration**: Connect to [OpenPlantBook](https://open.plantbook.io/) for species-specific care requirements
- 🏡 **Multi-Location Support**: Organize plants by location (rooms, zones, etc.)
- 📱 **ESPHome Integration**: Seamless integration with ESPHome-based plant sensors
- 🎯 **Smart Alerts**: Binary sensors for water needs, fertilizer schedules, battery levels, and environmental conditions

## Installation

### HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. In Home Assistant, go to **HACS** → **Integrations**
3. Click the **⋮** menu in the top right and select **Custom repositories**
4. Add `https://github.com/shortmanflee/HA-Plant-Assistant` as an **Integration**
5. Click **Download** and restart Home Assistant
6. Go to **Settings** → **Devices & Services** → **Add Integration**
7. Search for **Plant Assistant** and follow the setup wizard

### Manual Installation

1. Download the latest release from the [releases page][releases]
2. Extract the `custom_components/plant_assistant` directory to your Home Assistant `custom_components` folder
3. Restart Home Assistant
4. Go to **Settings** → **Devices & Services** → **Add Integration**
5. Search for **Plant Assistant** and follow the setup wizard

## Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Plant Assistant**
3. Follow the configuration flow:
   - **Optional**: Link an ESPHome device for automatic sensor discovery
   - **Alternative**: Enter a custom name for your plant or location
4. Configure plant details and monitoring preferences

### OpenPlantBook Integration

Plant Assistant integrates with [OpenPlantBook](https://open.plantbook.io/) for species-specific plant care data.

**Required**: You must install the [HA-OpenPlantbook-Reference-Library](https://github.com/shortmanflee/HA-OpenPlantbook-Reference-Library) integration for OpenPlantBook support:

1. Install the [HA-OpenPlantbook-Reference-Library](https://github.com/shortmanflee/HA-OpenPlantbook-Reference-Library) integration via HACS or manually
2. Configure it with your OpenPlantBook API credentials
3. Plant Assistant will automatically use plant care parameters from OpenPlantBook through this integration

### Linking Sensors

After setup, you can link various sensors to each plant or location:

- **Soil Moisture** sensors
- **Light/Illuminance** sensors for DLI calculation
- **Temperature** sensors
- **Humidity** sensors
- **Conductivity** sensors (for fertilizer monitoring)

## Entities Created

### Sensors

Each plant location can have the following sensors:

- **Environmental Sensors**:
  - Min/Max Light (lux)
  - Min/Max Temperature
  - Min/Max Humidity
  - Min/Max Soil Moisture
  - Min/Max Soil Conductivity
- **Light Metrics**:
  - PPFD (Photosynthetic Photon Flux Density)
  - DLI (Daily Light Integral)
  - DLI Weekly Average
  - DLI Prior Period
- **Status Sensors**:
  - Plant Count
  - Location Count
  - Error Count
  - Fertilizer Due

### Binary Sensors

Problem detection and status monitoring:

- **Plant Health**:
  - Soil Moisture Low/High
  - Soil Moisture Water Soon
  - Soil Conductivity Low/High
  - DLI Status Monitor
  - Humidity Above/Below Threshold
  - Temperature Above/Below Threshold
- **System Status**:
  - Battery Level Status
  - ESPHome Running Status
  - Error Status Monitor
  - Irrigation Zone Status
  - Schedule Misconfiguration
  - Recently Watered

### Switches

Control and automation switches:

- Irrigation zone enable/disable
- Auto-schedule controls
- Manual override switches

### Buttons

Quick actions for maintenance:

- Reset error count
- Irrigation controls

### Number Entities

Adjustable parameters for fine-tuning:

- Moisture thresholds
- Conductivity thresholds
- Light requirements
- Schedule parameters

### DateTime Entities

Time-based scheduling:

- Last watered timestamp
- Next fertilization schedule
- Irrigation schedules

## Usage Examples

### Automation: Water When Soil is Dry

```yaml
automation:
  - alias: "Water Plant When Dry"
    trigger:
      - platform: state
        entity_id: binary_sensor.plant_location_soil_moisture_low
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Your plant needs water!"
      - service: switch.turn_on
        target:
          entity_id: switch.irrigation_zone_1
```

### Automation: Alert on Insufficient Light

```yaml
automation:
  - alias: "Alert Low Light"
    trigger:
      - platform: numeric_state
        entity_id: sensor.plant_location_dli
        below: 5
    action:
      - service: notify.mobile_app
        data:
          message: "Your plant is not getting enough light (DLI below 5)"
```

### Lovelace Card Example

```yaml
type: entities
title: My Plant
entities:
  - entity: sensor.my_plant_soil_moisture
  - entity: sensor.my_plant_dli
  - entity: sensor.my_plant_temperature
  - entity: binary_sensor.my_plant_soil_moisture_low
  - entity: binary_sensor.my_plant_dli_status
  - entity: sensor.my_plant_fertilizer_due
```

## Daily Light Integral (DLI)

Plant Assistant automatically calculates DLI from your light sensors:

- **DLI** measures the total amount of photosynthetically active light delivered to plants over a 24-hour period
- Calculated in mol/m²/day using illuminance (lux) readings
- Helps ensure your plants receive optimal light for growth
- Weekly averages help track trends and adjust placement

### DLI Guidelines

- **Low Light Plants**: 5-10 mol/m²/day
- **Medium Light Plants**: 10-20 mol/m²/day
- **High Light Plants**: 20-40 mol/m²/day

## Development

### Prerequisites

- Python 3.11+
- Home Assistant development environment

### Setup Development Environment

1. Clone the repository:

   ```bash
   git clone https://github.com/shortmanflee/HA-Plant-Assistant.git
   cd HA-Plant-Assistant
   ```

2. **Recommended**: Open in VS Code with DevContainer:
   - Install Docker Desktop and VS Code Dev Containers extension
   - Open the folder in VS Code
   - Click "Reopen in Container" when prompted

3. **Alternative**: Local development:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On macOS/Linux
   pip install -r requirements.txt
   ```

### Running Tests

```bash
python -m pytest tests/ -v
```

### Code Quality

Run pre-commit hooks to ensure code quality:

```bash
pre-commit run --all-files
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Support

- **Issues**: [GitHub Issues](https://github.com/shortmanflee/HA-Plant-Assistant/issues)
- **Discussions**: [GitHub Discussions](https://github.com/shortmanflee/HA-Plant-Assistant/discussions)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgements

- Built with the [Home Assistant Integration Template](https://github.com/shortmanflee/HA-Integration-Template)
- Inspired by [Integration Blueprint](https://github.com/ludeeus/integration_blueprint) by [ludeeus](https://github.com/ludeeus)
- Plant care data powered by [OpenPlantBook](https://open.plantbook.io/)

[commits-shield]: https://img.shields.io/github/commit-activity/y/shortmanflee/HA-Plant-Assistant.svg?style=for-the-badge
[commits]: https://github.com/shortmanflee/HA-Plant-Assistant/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/shortmanflee/HA-Plant-Assistant.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/shortmanflee/HA-Plant-Assistant.svg?style=for-the-badge
[releases]: https://github.com/shortmanflee/HA-Plant-Assistant/releases
