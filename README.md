# Benew ZHA Quirks

Custom device quirks for Home Assistant's ZHA (Zigbee Home Automation) integration.

These quirks are tailored to my specific setup and may not suit everyone's needs.

Feel free to adapt them for your own use!

## Devices

### IKEA RODRET Remote

An experiment to squeeze as much functionality as possible out of a simple two-button remote.

This quirk detects various click patterns (single, double, triple, etc.) and button combinations, letting you dispatch different events to control many different things with just one remote.

#### Features
- Single, double, triple, quadruple, and quintuple click detection
- Dual button press detection
- Sequential button press patterns

#### Available Events
- **ON button clicks:** `on_short_press`, `on_double_press`, `on_triple_press`, `on_quadruple_press`, `on_quintuple_press`
- **OFF button clicks:** `off_short_press`, `off_double_press`, `off_triple_press`, `off_quadruple_press`, `off_quintuple_press`
- **Dual button press:** `button_double`, `button_double_double_press`, `button_double_triple_press`
- **Sequential button patterns:**
  - 2-button sequences: `on_off`, `off_on`
  - 3-button sequences: `on_on_off`, `on_off_on`, `on_off_off`, `off_on_on`, `off_on_off`, `off_off_on`

### Sonoff TRVZB Thermostat

A custom quirk that lets external thermostat add-ons (like Versatile Thermostat) take control of the valve instead of using its built-in thermostat.

#### Features
- **Virtual valve position** - Allows external thermostat add-ons to control the valve directly
- **Calibration sliders** - Min/max opening percent limits must be configured manually using the slider controls in Home Assistant. These settings persist across restarts.

#### Setup
After installing the quirk, use the "Valve Min Limit" and "Valve Max Limit" sliders in Home Assistant to calibrate your valve. These values define the physical range of motion and are saved persistently, so you only need to configure them once.

## Installation

Copy the quirk files to your Home Assistant ZHA quirks directory:
```
~/.homeassistant/custom_zha_quirks/
```

## License

MIT License - See LICENSE file for details
