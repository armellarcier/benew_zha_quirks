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
    CLUSTER_ID, COMMAND, DEVICE_TYPE, ENDPOINT_ID, ENDPOINTS, INPUT_CLUSTERS,
    LONG_PRESS, LONG_RELEASE, MODELS_INFO, OUTPUT_CLUSTERS, PARAMS, PROFILE_ID,
    SHORT_PRESS, TURN_OFF, TURN_ON, DIM_UP, DIM_DOWN,
    COMMAND_ON, COMMAND_OFF, COMMAND_MOVE_ON_OFF, COMMAND_STOP_ON_OFF, COMMAND_MOVE, COMMAND_STOP,
    ZHA_SEND_EVENT, DOUBLE_PRESS, TRIPLE_PRESS, QUADRUPLE_PRESS, QUINTUPLE_PRESS
)
from zhaquirks.ikea import IKEA, IKEA_CLUSTER_ID, PowerConfig1AAACluster

_LOGGER = logging.getLogger(__name__)

CLICK_TIMEOUT = 0.35  # 350ms window for detecting multiple clicks


class MultiClickOnOffCluster(OnOff):
    """OnOff cluster with multi-click detection."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._click_count = {"on": 0, "off": 0}
        self._click_timer = {"on": None, "off": None}
        
        # Only initialize multi-click for actual devices, not groups
        if hasattr(self.endpoint, 'device') and hasattr(self.endpoint.device, 'ieee'):
            _LOGGER.info(f"MultiClickOnOffCluster initialized for device {self.endpoint.device.ieee}")
        else:
            _LOGGER.info(f"MultiClickOnOffCluster initialized for group/other endpoint")

    async def _handle_click(self, button: str) -> None:
        """Handle button click with multi-click detection."""
        self._click_count[button] += 1
        _LOGGER.info(f"RODRET: Click #{self._click_count[button]} on {button} button")

        # Cancel existing timer for this button
        if self._click_timer[button]:
            _LOGGER.info(f"RODRET: Cancelling existing timer for {button} button")
            self._click_timer[button].cancel()

        # Set new timer to process clicks after timeout
        self._click_timer[button] = asyncio.create_task(self._process_clicks(button))

    async def _process_clicks(self, button: str) -> None:
        """Process accumulated clicks after timeout."""
        try:
            await asyncio.sleep(CLICK_TIMEOUT)

            click_count = self._click_count[button]

            _LOGGER.info(f"RODRET: {click_count} click(s) on {button} button - emitting event")

            # Emit appropriate event based on click count
            if click_count == 1:
                self._emit_single_click(button)
            elif click_count == 2:
                self._emit_double_click(button)
            elif click_count == 3:
                self._emit_triple_click(button)
            elif click_count == 4:
                self._emit_quadruple_click(button)
            elif click_count >= 5:
                self._emit_quintuple_click(button)

            # Reset for next sequence
            self._click_count[button] = 0
            self._click_timer[button] = None

        except asyncio.CancelledError:
            _LOGGER.info(f"RODRET: Click timer cancelled for {button} button")
            pass

    def _emit_single_click(self, button: str) -> None:
        """Emit single click event."""
        _LOGGER.info(f"RODRET: Emitting single click event for {button}")
        # Emit the custom event instead of letting the default "On"/"Off" event through
        self.listener_event(ZHA_SEND_EVENT, f"{button}_{SHORT_PRESS}", {})

    def _emit_double_click(self, button: str) -> None:
        """Emit double click event."""
        _LOGGER.info(f"RODRET: Emitting double click event for {button}")
        self.listener_event(ZHA_SEND_EVENT, f"{button}_{DOUBLE_PRESS}", {})

    def _emit_triple_click(self, button: str) -> None:
        """Emit triple click event."""
        _LOGGER.info(f"RODRET: Emitting triple click event for {button}")
        self.listener_event(ZHA_SEND_EVENT, f"{button}_{TRIPLE_PRESS}", {})

    def _emit_quadruple_click(self, button: str) -> None:
        """Emit quadruple click event."""
        _LOGGER.info(f"RODRET: Emitting quadruple click event for {button}")
        self.listener_event(ZHA_SEND_EVENT, f"{button}_{QUADRUPLE_PRESS}", {})

    def _emit_quintuple_click(self, button: str) -> None:
        """Emit quintuple click event."""
        _LOGGER.info(f"RODRET: Emitting quintuple click event for {button}")
        self.listener_event(ZHA_SEND_EVENT, f"{button}_{QUINTUPLE_PRESS}", {})

    def handle_cluster_request(self, hdr, args, **kwargs):
        """Handle cluster requests - intercept button presses."""
        # Only do multi-click detection for actual devices, not groups
        if hasattr(self.endpoint, 'device') and hasattr(self.endpoint.device, 'ieee'):
            _LOGGER.info(f"RODRET cluster request: command_id={hdr.command_id}, args={args}")
            
            # Check for on/off commands
            if hdr.command_id == 0x01:  # ON command
                _LOGGER.info("RODRET: ON button pressed - suppressing default event")
                asyncio.create_task(self._handle_click("on"))
                # Return None to suppress default processing
                return None
            elif hdr.command_id == 0x00:  # OFF command
                _LOGGER.info("RODRET: OFF button pressed - suppressing default event")
                asyncio.create_task(self._handle_click("off"))
                # Return None to suppress default processing
                return None
        
        # Pass through other commands or group requests
        return super().handle_cluster_request(hdr, args, **kwargs)



class IkeaRodretRemoteMultiClick(CustomDevice):
    """IKEA RODRET with double/triple click support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _LOGGER.info(f"IkeaRodretRemoteMultiClick quirk loaded for device {self.ieee}")

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
    }
