"""IKEA RODRET remote with multi-click support."""

import asyncio
import logging

from zigpy.profiles import zha
from zigpy.quirks import CustomDevice
from zigpy.zcl.clusters.general import (
    Basic, Groups, Identify, LevelControl, OnOff, Ota, PollControl, PowerConfiguration
)
from zigpy.zcl.clusters.lightlink import LightLink

from zhaquirks.const import (
    MODELS_INFO, PROFILE_ID, DEVICE_TYPE, ENDPOINTS, INPUT_CLUSTERS, OUTPUT_CLUSTERS,
    COMMAND_BUTTON_DOUBLE, COMMAND_ON, COMMAND_OFF, ZHA_SEND_EVENT,
    SHORT_PRESS, DOUBLE_PRESS, TRIPLE_PRESS, QUADRUPLE_PRESS, QUINTUPLE_PRESS, COMMAND
)
from zhaquirks.ikea import IKEA, IKEA_CLUSTER_ID, PowerConfig1AAACluster

_LOGGER = logging.getLogger(__name__)

# Timing constants (base values)
CLICK_TIMEOUT = 0.45  # 450ms window for detecting multiple clicks
DUAL_BUTTON_TIMEOUT = 0.15  # 150ms window for detecting simultaneous button presses

# Click type mapping
CLICK_TYPES = {
    1: SHORT_PRESS,
    2: DOUBLE_PRESS,
    3: TRIPLE_PRESS,
    4: QUADRUPLE_PRESS,
    5: QUINTUPLE_PRESS,
}

# Button names
ON_BUTTON = "on"
OFF_BUTTON = "off"
DUAL_BUTTON = "dual"


class MultiClickOnOffCluster(OnOff):
    """OnOff cluster with multi-click detection for single and dual button presses."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Track button presses with timestamps: [(button, timestamp), ...]
        try:
            object.__setattr__(self, '_presses', [])
            object.__setattr__(self, '_timer', None)
            # Configurable timeouts (can be overridden for testing)
            object.__setattr__(self, 'click_timeout', CLICK_TIMEOUT)
            object.__setattr__(self, 'dual_button_timeout', DUAL_BUTTON_TIMEOUT)
        except Exception:
            pass

    def __getattr__(self, name):
        """Handle attribute access for private attributes."""
        if name in ('_presses', '_timer', 'click_timeout', 'dual_button_timeout'):
            try:
                return object.__getattribute__(self, name)
            except AttributeError:
                if name == '_presses':
                    presses = []
                    object.__setattr__(self, '_presses', presses)
                    return presses
                elif name == '_timer':
                    return None
                elif name == 'click_timeout':
                    return CLICK_TIMEOUT
                elif name == 'dual_button_timeout':
                    return DUAL_BUTTON_TIMEOUT
        return super().__getattr__(name)

    async def _handle_click(self, button: str) -> None:
        """Handle button click with multi-click and sequence detection."""
        now = asyncio.get_event_loop().time()
        
        # Ensure _presses exists
        try:
            presses = object.__getattribute__(self, '_presses')
        except AttributeError:
            presses = []
            object.__setattr__(self, '_presses', presses)
        
        # Add this press
        presses.append((button, now))
        
        # Cancel existing timer
        try:
            timer = object.__getattribute__(self, '_timer')
        except AttributeError:
            timer = None
        
        if timer:
            timer.cancel()
        
        # Set new timer to process presses
        object.__setattr__(self, '_timer', asyncio.create_task(self._process_presses()))

    async def _process_presses(self) -> None:
        """Process accumulated presses after timeout."""
        try:
            await asyncio.sleep(self.click_timeout)
            self._emit_event_for_presses()
            self._presses.clear()
        except asyncio.CancelledError:
            pass

    def _emit_event_for_presses(self) -> None:
        """Analyze presses and emit appropriate event."""
        presses = self._presses
        if not presses:
            return
        
        # Extract buttons and timestamps
        buttons = [p[0] for p in presses]
        times = [p[1] for p in presses]
        
        event_name = None
        
        # Determine event type based on press pattern
        if len(presses) == 1:
            # Single press
            event_name = f"{buttons[0]}_{SHORT_PRESS}"
        
        elif len(set(buttons)) == 1:
            # All same button - count presses
            count = len(presses)
            if count > 5:
                count = 5
            
            click_type = CLICK_TYPES.get(count, SHORT_PRESS)
            event_name = f"{buttons[0]}_{click_type}"
        
        else:
            # Mixed buttons - check timing to distinguish dual vs sequential
            time_between_first_two = times[1] - times[0]
            
            if time_between_first_two < self.dual_button_timeout and len(presses) == 2:
                # Very fast (dual button timeout) AND exactly 2 presses - treat as dual button press
                event_name = "button_double"
            
            elif time_between_first_two < self.dual_button_timeout and len(presses) > 2:
                # Very fast but more than 2 presses - check for repeated dual button pattern
                # Only treat as dual button if it's a clear pattern like ON-OFF-ON-OFF
                dual_count = 1
                i = 2
                while i + 1 < len(presses):
                    if (buttons[i] != buttons[i+1] and 
                        (times[i+1] - times[i]) < self.dual_button_timeout and
                        (times[i] - times[i-1]) < self.click_timeout):
                        dual_count += 1
                        i += 2
                    else:
                        break
                
                if dual_count > 1 and i == len(presses):
                    # Complete dual button pattern (all presses accounted for)
                    click_type = CLICK_TYPES.get(dual_count, QUINTUPLE_PRESS)
                    event_name = f"button_double_{click_type}"
                else:
                    # Incomplete pattern or mixed - treat as sequential
                    event_name = "_".join(buttons)
            
            else:
                # Slower (sequential timeout) - treat as sequential button press
                event_name = "_".join(buttons)
        
        # Emit the event
        if event_name:
            _LOGGER.debug(f"RODRET: Emitting event: {event_name}")
            self.listener_event(ZHA_SEND_EVENT, event_name, {})

    def handle_cluster_request(self, hdr, args, **kwargs):
        """Handle cluster requests - intercept button presses."""
        # Only do multi-click detection for actual devices, not groups
        if not (hasattr(self.endpoint, 'device') and hasattr(self.endpoint.device, 'ieee')):
            return super().handle_cluster_request(hdr, args, **kwargs)

        # Check for on/off commands
        if hdr.command_id == 0x01:  # ON command
            asyncio.create_task(self._handle_click(ON_BUTTON))
            return None
        elif hdr.command_id == 0x00:  # OFF command
            asyncio.create_task(self._handle_click(OFF_BUTTON))
            return None
        
        # Pass through other commands
        return super().handle_cluster_request(hdr, args, **kwargs)


class IkeaRodretRemoteMultiClick(CustomDevice):
    """IKEA RODRET remote with multi-click support."""

    signature = {
        MODELS_INFO: [(IKEA, "RODRET Dimmer"), (IKEA, "RODRET wireless dimmer")],
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.NON_COLOR_CONTROLLER,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    PowerConfiguration.cluster_id,
                    Identify.cluster_id,
                    Groups.cluster_id,
                    PollControl.cluster_id,
                    LightLink.cluster_id,
                    IKEA_CLUSTER_ID,
                ],
                OUTPUT_CLUSTERS: [
                    Identify.cluster_id,
                    Groups.cluster_id,
                    OnOff.cluster_id,
                    LevelControl.cluster_id,
                    Ota.cluster_id,
                    LightLink.cluster_id,
                ],
            }
        },
    }

    replacement = {
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.NON_COLOR_CONTROLLER,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    PowerConfig1AAACluster,
                    Identify.cluster_id,
                    PollControl.cluster_id,
                    LightLink.cluster_id,
                    IKEA_CLUSTER_ID,
                ],
                OUTPUT_CLUSTERS: [
                    Identify.cluster_id,
                    Groups.cluster_id,
                    MultiClickOnOffCluster,
                    LevelControl.cluster_id,
                    Ota.cluster_id,
                    LightLink.cluster_id,
                ],
            }
        }
    }

    device_automation_triggers = {
        (SHORT_PRESS, COMMAND_ON): {COMMAND: f"{COMMAND_ON}_{SHORT_PRESS}"},
        (DOUBLE_PRESS, COMMAND_ON): {COMMAND: f"{COMMAND_ON}_{DOUBLE_PRESS}"},
        (TRIPLE_PRESS, COMMAND_ON): {COMMAND: f"{COMMAND_ON}_{TRIPLE_PRESS}"},
        (QUADRUPLE_PRESS, COMMAND_ON): {COMMAND: f"{COMMAND_ON}_{QUADRUPLE_PRESS}"},
        (QUINTUPLE_PRESS, COMMAND_ON): {COMMAND: f"{COMMAND_ON}_{QUINTUPLE_PRESS}"},
        (SHORT_PRESS, COMMAND_OFF): {COMMAND: f"{COMMAND_OFF}_{SHORT_PRESS}"},
        (DOUBLE_PRESS, COMMAND_OFF): {COMMAND: f"{COMMAND_OFF}_{DOUBLE_PRESS}"},
        (TRIPLE_PRESS, COMMAND_OFF): {COMMAND: f"{COMMAND_OFF}_{TRIPLE_PRESS}"},
        (QUADRUPLE_PRESS, COMMAND_OFF): {COMMAND: f"{COMMAND_OFF}_{QUADRUPLE_PRESS}"},
        (QUINTUPLE_PRESS, COMMAND_OFF): {COMMAND: f"{COMMAND_OFF}_{QUINTUPLE_PRESS}"},
        (SHORT_PRESS, COMMAND_BUTTON_DOUBLE): {COMMAND: COMMAND_BUTTON_DOUBLE},
        (DOUBLE_PRESS, COMMAND_BUTTON_DOUBLE): {COMMAND: f"{COMMAND_BUTTON_DOUBLE}_{DOUBLE_PRESS}"},
        (TRIPLE_PRESS, COMMAND_BUTTON_DOUBLE): {COMMAND: f"{COMMAND_BUTTON_DOUBLE}_{TRIPLE_PRESS}"},
        (SHORT_PRESS, "on_off"): {COMMAND: "on_off"},
        (SHORT_PRESS, "off_on"): {COMMAND: "off_on"},
        # Triple-click sequences (6 combinations - excluding same button sequences)
        (SHORT_PRESS, "on_on_off"): {COMMAND: "on_on_off"},
        (SHORT_PRESS, "on_off_on"): {COMMAND: "on_off_on"},
        (SHORT_PRESS, "on_off_off"): {COMMAND: "on_off_off"},
        (SHORT_PRESS, "off_on_on"): {COMMAND: "off_on_on"},
        (SHORT_PRESS, "off_on_off"): {COMMAND: "off_on_off"},
        (SHORT_PRESS, "off_off_on"): {COMMAND: "off_off_on"},
    }
