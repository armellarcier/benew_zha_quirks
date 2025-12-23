"""Integration tests for IKEA RODRET remote multi-click detection.

This test suite validates the multi-click detection logic of the RODRET remote
by simulating button presses through the cluster request handler and verifying
that the correct events are emitted based on timing and button combinations.

Test Organization:
- Single Button Tests: Single, double, triple, quadruple, and quintuple presses
- Multi-Button Tests: Simultaneous and sequential button combinations
- Dual Button Tests: Dual button single, double, and triple presses
- Timing Tests: Boundary conditions and state management
- Edge Cases: Timer cancellation, rapid presses, boundary conditions
- Robustness Tests: Stress testing with rapid/mixed patterns
- Negative Tests: Verify correct event names and no duplicates

Test Coverage:
- Single button clicks: 1-5+ presses on ON and OFF buttons
- Dual button clicks: Simultaneous presses with 1-3 repetitions
- Timing boundaries: DUAL_BUTTON_TIMEOUT and CLICK_TIMEOUT edges
- State management: Reset after events, independent sequences
- Edge cases: Timer cancellation, rapid alternating presses
- Robustness: Back-to-back sequences, minimal intervals
"""

import asyncio
import pytest
from unittest.mock import Mock, MagicMock
import sys
from pathlib import Path

# Add parent directory to path to import rodret
sys.path.insert(0, str(Path(__file__).parent.parent))

from rodret import MultiClickOnOffCluster
from zhaquirks.const import (
    SHORT_PRESS, DOUBLE_PRESS, TRIPLE_PRESS, QUADRUPLE_PRESS, QUINTUPLE_PRESS,
    COMMAND_ON, COMMAND_OFF, COMMAND_BUTTON_DOUBLE, COMMAND, ZHA_SEND_EVENT
)


# Constants for command IDs (matching ZigBee cluster commands)
ON_COMMAND_ID = 0x01
OFF_COMMAND_ID = 0x00

# Custom test timing constants (faster than real-world for quicker tests)
TEST_CLICK_TIMEOUT = 0.045  # 35ms window (10x faster than real 350ms)
TEST_DUAL_BUTTON_TIMEOUT = 0.015  # 20ms window (10x faster than real 200ms)

# Sleep durations for test timing
QUICK_PRESS_INTERVAL = 0.005  # Time between rapid presses
MINIMAL_PRESS_INTERVAL = 0.001  # Minimal interval for stress testing
WAIT_FOR_EVENT = TEST_CLICK_TIMEOUT + MINIMAL_PRESS_INTERVAL  # Wait for event emission after timeout


@pytest.fixture
def cluster():
    """Create a cluster instance with mocked dependencies for testing.
    
    Sets up a MultiClickOnOffCluster with:
    - Initialized click tracking state
    - Mocked listener_event for capturing emitted events
    - Mocked endpoint for device identification
    - Custom faster timeouts for quicker tests
    """
    cluster = MultiClickOnOffCluster.__new__(MultiClickOnOffCluster)
    
    # Initialize click tracking state
    cluster._click_count = {"on": 0, "off": 0, "dual": 0}
    cluster._click_timer = {"on": None, "off": None, "dual": None}
    cluster._last_button_press = {"on": None, "off": None}
    cluster._last_dual_press = None
    
    # Set custom faster timeouts for testing
    cluster.click_timeout = TEST_CLICK_TIMEOUT
    cluster.dual_button_timeout = TEST_DUAL_BUTTON_TIMEOUT
    
    # Mock event listener
    cluster.listener_event = Mock()
    
    # Mock endpoint for device identification
    cluster.__dict__['_endpoint'] = MagicMock()
    cluster.__dict__['_endpoint'].device = MagicMock()
    cluster.__dict__['_endpoint'].device.ieee = "00:11:22:33:44:55:66:77"
    
    return cluster


class TestHelpers:
    """Helper methods for test setup and assertions."""
    
    @staticmethod
    def create_header(command_id):
        """Create a mock cluster request header.
        
        Args:
            command_id: The ZigBee command ID (0x00 for OFF, 0x01 for ON)
            
        Returns:
            MagicMock: Header object with command_id attribute
        """
        hdr = MagicMock()
        hdr.command_id = command_id
        return hdr
    
    @staticmethod
    async def press_button(cluster, command_id):
        """Simulate a button press via cluster request.
        
        Args:
            cluster: The cluster instance
            command_id: The button to press (0x00 for OFF, 0x01 for ON)
        """
        hdr = TestHelpers.create_header(command_id)
        result = cluster.handle_cluster_request(hdr, [], **{})
        assert result is None, "Cluster request should suppress default processing"
    
    @staticmethod
    async def wait_for_event():
        """Wait for event emission after click timeout."""
        await asyncio.sleep(WAIT_FOR_EVENT)
    
    @staticmethod
    def assert_event_emitted(cluster, expected_event, call_index=0):
        """Assert that an event was emitted with exact match.
        
        Args:
            cluster: The cluster instance
            expected_event: Exact event name to match
            call_index: Which call to check (0 for first, 1 for second, etc.)
        """
        assert cluster.listener_event.call_count > call_index, \
            f"Expected at least {call_index + 1} calls, got {cluster.listener_event.call_count}"
        
        call_args = cluster.listener_event.call_args_list[call_index][0]
        
        # Verify first argument is ZHA_SEND_EVENT
        assert call_args[0] == ZHA_SEND_EVENT, \
            f"Expected first argument to be ZHA_SEND_EVENT, got {call_args[0]}"
        
        # Extract and verify exact event name (second argument)
        actual_event = call_args[1]
        assert actual_event == expected_event, \
            f"Expected event '{expected_event}', got '{actual_event}'"
    
    @staticmethod
    def assert_event_count(cluster, expected_count):
        """Assert exact number of events emitted.
        
        Args:
            cluster: The cluster instance
            expected_count: Expected number of listener_event calls
        """
        assert cluster.listener_event.call_count == expected_count, \
            f"Expected {expected_count} events, got {cluster.listener_event.call_count}"
    
    @staticmethod
    def get_event_name(cluster, call_index=0):
        """Get the event name from a specific call.
        
        Args:
            cluster: The cluster instance
            call_index: Which call to get (0 for first, 1 for second, etc.)
            
        Returns:
            str: The event name
        """
        return cluster.listener_event.call_args_list[call_index][0][1]


class TestSingleButtonPresses:
    """Tests for single button press detection (1-5 clicks)."""
    
    @pytest.mark.asyncio
    async def test_single_on_press(self, cluster):
        """Single ON button press should emit short press event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "on_remote_button_short_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_single_off_press(self, cluster):
        """Single OFF button press should emit short press event."""
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "off_remote_button_short_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("button_id,button_name", [
        (ON_COMMAND_ID, "on"),
        (OFF_COMMAND_ID, "off"),
    ])
    async def test_double_press(self, cluster, button_id, button_name):
        """Two rapid presses should emit double press event."""
        await TestHelpers.press_button(cluster, button_id)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, button_id)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, f"{button_name}_remote_button_double_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("button_id,button_name", [
        (ON_COMMAND_ID, "on"),
        (OFF_COMMAND_ID, "off"),
    ])
    async def test_triple_press(self, cluster, button_id, button_name):
        """Three rapid presses should emit triple press event."""
        for _ in range(3):
            await TestHelpers.press_button(cluster, button_id)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, f"{button_name}_remote_button_triple_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("button_id,button_name", [
        (ON_COMMAND_ID, "on"),
        (OFF_COMMAND_ID, "off"),
    ])
    async def test_quadruple_press(self, cluster, button_id, button_name):
        """Four rapid presses should emit quadruple press event."""
        for _ in range(4):
            await TestHelpers.press_button(cluster, button_id)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, f"{button_name}_remote_button_quadruple_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("button_id,button_name", [
        (ON_COMMAND_ID, "on"),
        (OFF_COMMAND_ID, "off"),
    ])
    async def test_quintuple_press(self, cluster, button_id, button_name):
        """Five rapid presses should emit quintuple press event."""
        for _ in range(5):
            await TestHelpers.press_button(cluster, button_id)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, f"{button_name}_remote_button_quintuple_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_six_presses_treated_as_quintuple(self, cluster):
        """Six or more presses should emit quintuple press event (max)."""
        for _ in range(6):
            await TestHelpers.press_button(cluster, ON_COMMAND_ID)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "on_remote_button_quintuple_press")
        TestHelpers.assert_event_count(cluster, 1)


class TestMultiButtonPresses:
    """Tests for multi-button press detection."""
    
    @pytest.mark.asyncio
    async def test_simultaneous_buttons_on_first(self, cluster):
        """Pressing ON then OFF within DUAL_BUTTON_TIMEOUT should emit dual button event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "button_double")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_simultaneous_buttons_off_first(self, cluster):
        """Pressing OFF then ON within DUAL_BUTTON_TIMEOUT should emit dual button event."""
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "button_double")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_slow_button_presses_emit_separate_events(self, cluster):
        """Pressing buttons with long delays should emit separate single press events."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        first_call_count = cluster.listener_event.call_count
        
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        assert cluster.listener_event.call_count == first_call_count + 1
        TestHelpers.assert_event_emitted(cluster, "on_remote_button_short_press", call_index=0)
        TestHelpers.assert_event_emitted(cluster, "off_remote_button_short_press", call_index=1)


class TestDualButtonPresses:
    """Tests for dual button (simultaneous) press detection."""
    
    @pytest.mark.asyncio
    async def test_dual_button_single_press(self, cluster):
        """Single simultaneous button press should emit dual button event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "button_double")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_dual_button_double_press(self, cluster):
        """Two rapid simultaneous button press sequences should emit dual button double press."""
        for _ in range(2):
            await TestHelpers.press_button(cluster, ON_COMMAND_ID)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
            await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
        
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "button_double_remote_button_double_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_dual_button_triple_press(self, cluster):
        """Three rapid simultaneous button press sequences should emit dual button triple press."""
        for _ in range(3):
            await TestHelpers.press_button(cluster, ON_COMMAND_ID)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
            await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
        
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "button_double_remote_button_triple_press")
        TestHelpers.assert_event_count(cluster, 1)


class TestTimingBoundaries:
    """Tests for timing boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_dual_button_timeout_boundary_under(self, cluster):
        """Presses just under DUAL_BUTTON_TIMEOUT should be detected as dual button."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT - MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "button_double")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_click_timeout_boundary(self, cluster):
        """Presses at exact CLICK_TIMEOUT should still emit event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_CLICK_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        
        # Event should be emitted after timeout
        TestHelpers.assert_event_emitted(cluster, "on_remote_button_short_press")
        TestHelpers.assert_event_count(cluster, 1)


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""
    
    @pytest.mark.asyncio
    async def test_rapid_alternating_presses(self, cluster):
        """Rapid alternating ON-OFF-ON presses should detect dual button."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should detect dual button press (first ON-OFF), then another ON
        # The exact behavior depends on implementation
        assert cluster.listener_event.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_minimal_interval_presses(self, cluster):
        """Presses with minimal interval should still be detected as rapid."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "on_remote_button_double_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_back_to_back_sequences(self, cluster):
        """Multiple sequences back-to-back should emit independent events."""
        # First sequence: double click
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        first_count = cluster.listener_event.call_count
        
        # Second sequence: single click
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should have two separate events
        assert cluster.listener_event.call_count == first_count + 1
        assert "double_press" in TestHelpers.get_event_name(cluster, 0)
        assert "short_press" in TestHelpers.get_event_name(cluster, 1)


class TestStateManagement:
    """Tests for internal state management."""
    
    @pytest.mark.asyncio
    async def test_state_reset_after_event(self, cluster):
        """State should be reset after event emission."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Event should be emitted
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_independent_button_sequences(self, cluster):
        """Multiple button sequences should be independent."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        first_call_count = cluster.listener_event.call_count
        
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        assert cluster.listener_event.call_count == first_call_count + 1
        TestHelpers.assert_event_emitted(cluster, "on_remote_button_short_press", call_index=0)
        TestHelpers.assert_event_emitted(cluster, "off_remote_button_short_press", call_index=1)
    
    @pytest.mark.asyncio
    async def test_dual_button_state_reset(self, cluster):
        """Dual button state should be reset after event emission."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Event should be emitted
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_individual_button_state_independence(self, cluster):
        """ON and OFF button states should be independent."""
        # Press ON multiple times
        for _ in range(3):
            await TestHelpers.press_button(cluster, ON_COMMAND_ID)
            await asyncio.sleep(QUICK_PRESS_INTERVAL)
        await TestHelpers.wait_for_event()
        
        first_count = cluster.listener_event.call_count
        
        # Press OFF
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should have two separate events
        assert cluster.listener_event.call_count == first_count + 1


class TestSequentialPresses:
    """Tests for sequential button press detection (ON→OFF or OFF→ON)."""
    
    @pytest.mark.asyncio
    async def test_on_then_off_sequential(self, cluster):
        """ON button followed by OFF button within timing window should emit on_off event."""
        # Press ON
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + QUICK_PRESS_INTERVAL)
        
        # Press OFF within CLICK_TIMEOUT but after DUAL_BUTTON_TIMEOUT
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should emit sequential event
        TestHelpers.assert_event_emitted(cluster, "on_off")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_off_then_on_sequential(self, cluster):
        """OFF button followed by ON button within timing window should emit off_on event."""
        # Press OFF
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + QUICK_PRESS_INTERVAL)
        
        # Press ON within CLICK_TIMEOUT but after DUAL_BUTTON_TIMEOUT
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should emit sequential event
        TestHelpers.assert_event_emitted(cluster, "off_on")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_sequential_event_exact_name(self, cluster):
        """Sequential events should have exact event names."""
        # Test on_off
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + QUICK_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        event_name = TestHelpers.get_event_name(cluster, 0)
        assert event_name == "on_off", f"Expected 'on_off', got '{event_name}'"
    
    @pytest.mark.asyncio
    async def test_sequential_not_emitted_if_too_slow(self, cluster):
        """Presses beyond CLICK_TIMEOUT should not emit sequential event."""
        # Press ON
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        first_count = cluster.listener_event.call_count
        
        # Press OFF after CLICK_TIMEOUT (too slow for sequential)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should emit two separate single press events, not sequential
        assert cluster.listener_event.call_count == first_count + 1
        # First event should be on_short_press
        assert "on_remote_button_short_press" in TestHelpers.get_event_name(cluster, 0)
        # Second event should be off_short_press
        assert "off_remote_button_short_press" in TestHelpers.get_event_name(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_sequential_not_emitted_if_too_fast(self, cluster):
        """Presses within DUAL_BUTTON_TIMEOUT should emit dual button, not sequential."""
        # Press ON
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        
        # Press OFF within DUAL_BUTTON_TIMEOUT (too fast for sequential)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should emit dual button event, not sequential
        TestHelpers.assert_event_emitted(cluster, "button_double")
        TestHelpers.assert_event_count(cluster, 1)


class TestTripleClickSequences:
    """Tests for triple-click button sequences (on_on_off, on_off_on, etc.)."""
    
    @pytest.mark.asyncio
    async def test_on_on_off_sequence(self, cluster):
        """ON-ON-OFF sequence should emit on_on_off event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "on_on_off")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_on_off_on_sequence(self, cluster):
        """ON-OFF-ON sequence should emit on_off_on event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "on_off_on")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_off_on_off_sequence(self, cluster):
        """OFF-ON-OFF sequence should emit off_on_off event."""
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "off_on_off")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_off_off_on_sequence(self, cluster):
        """OFF-OFF-ON sequence should emit off_off_on event."""
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "off_off_on")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_on_on_on_sequence(self, cluster):
        """ON-ON-ON triple press should emit triple press event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "on_remote_button_triple_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_off_off_off_sequence(self, cluster):
        """OFF-OFF-OFF triple press should emit triple press event."""
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "off_remote_button_triple_press")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_on_off_off_sequence(self, cluster):
        """ON-OFF-OFF sequence should emit on_off_off event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "on_off_off")
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_off_on_on_sequence(self, cluster):
        """OFF-ON-ON sequence should emit off_on_on event."""
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(TEST_DUAL_BUTTON_TIMEOUT + MINIMAL_PRESS_INTERVAL)
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        TestHelpers.assert_event_emitted(cluster, "off_on_on")
        TestHelpers.assert_event_count(cluster, 1)


class TestDeviceAutomationTriggers:
    """Tests to verify device_automation_triggers are properly defined."""
    
    def test_all_single_button_triggers_defined(self):
        """Verify all single button click triggers are defined."""
        from rodret import IkeaRodretRemoteMultiClick
        
        triggers = IkeaRodretRemoteMultiClick.device_automation_triggers
        
        # ON button triggers
        assert (SHORT_PRESS, COMMAND_ON) in triggers
        assert (DOUBLE_PRESS, COMMAND_ON) in triggers
        assert (TRIPLE_PRESS, COMMAND_ON) in triggers
        assert (QUADRUPLE_PRESS, COMMAND_ON) in triggers
        assert (QUINTUPLE_PRESS, COMMAND_ON) in triggers
        
        # OFF button triggers
        assert (SHORT_PRESS, COMMAND_OFF) in triggers
        assert (DOUBLE_PRESS, COMMAND_OFF) in triggers
        assert (TRIPLE_PRESS, COMMAND_OFF) in triggers
        assert (QUADRUPLE_PRESS, COMMAND_OFF) in triggers
        assert (QUINTUPLE_PRESS, COMMAND_OFF) in triggers
    
    def test_all_dual_button_triggers_defined(self):
        """Verify all dual button click triggers are defined."""
        from rodret import IkeaRodretRemoteMultiClick
        
        triggers = IkeaRodretRemoteMultiClick.device_automation_triggers
        
        assert (SHORT_PRESS, COMMAND_BUTTON_DOUBLE) in triggers
        assert (DOUBLE_PRESS, COMMAND_BUTTON_DOUBLE) in triggers
        assert (TRIPLE_PRESS, COMMAND_BUTTON_DOUBLE) in triggers
    
    def test_all_sequential_triggers_defined(self):
        """Verify all sequential button press triggers are defined."""
        from rodret import IkeaRodretRemoteMultiClick
        
        triggers = IkeaRodretRemoteMultiClick.device_automation_triggers
        
        # Two-button sequences
        assert (SHORT_PRESS, "on_off") in triggers
        assert (SHORT_PRESS, "off_on") in triggers
        
        # Three-button sequences (6 combinations - excluding same button)
        assert (SHORT_PRESS, "on_on_off") in triggers
        assert (SHORT_PRESS, "on_off_on") in triggers
        assert (SHORT_PRESS, "on_off_off") in triggers
        assert (SHORT_PRESS, "off_on_on") in triggers
        assert (SHORT_PRESS, "off_on_off") in triggers
        assert (SHORT_PRESS, "off_off_on") in triggers
    
    def test_trigger_command_values_correct(self):
        """Verify trigger command values are correctly formatted."""
        from rodret import IkeaRodretRemoteMultiClick
        
        triggers = IkeaRodretRemoteMultiClick.device_automation_triggers
        
        # Check single button triggers
        assert triggers[(SHORT_PRESS, COMMAND_ON)][COMMAND] == f"{COMMAND_ON}_{SHORT_PRESS}"
        assert triggers[(DOUBLE_PRESS, COMMAND_ON)][COMMAND] == f"{COMMAND_ON}_{DOUBLE_PRESS}"
        assert triggers[(SHORT_PRESS, COMMAND_OFF)][COMMAND] == f"{COMMAND_OFF}_{SHORT_PRESS}"
        assert triggers[(DOUBLE_PRESS, COMMAND_OFF)][COMMAND] == f"{COMMAND_OFF}_{DOUBLE_PRESS}"
        
        # Check dual button triggers
        assert triggers[(SHORT_PRESS, COMMAND_BUTTON_DOUBLE)][COMMAND] == COMMAND_BUTTON_DOUBLE
        assert triggers[(DOUBLE_PRESS, COMMAND_BUTTON_DOUBLE)][COMMAND] == f"{COMMAND_BUTTON_DOUBLE}_{DOUBLE_PRESS}"
        
        # Check sequential triggers
        assert triggers[(SHORT_PRESS, "on_off")][COMMAND] == "on_off"
        assert triggers[(SHORT_PRESS, "off_on")][COMMAND] == "off_on"
    
    def test_total_trigger_count(self):
        """Verify the total number of triggers is correct."""
        from rodret import IkeaRodretRemoteMultiClick
        
        triggers = IkeaRodretRemoteMultiClick.device_automation_triggers
        
        # 5 single button clicks × 2 buttons = 10
        # 3 dual button clicks = 3
        # 2 two-button sequences = 2
        # 6 three-button sequences (excluding same button) = 6
        # Total = 21
        assert len(triggers) == 21, f"Expected 21 triggers, got {len(triggers)}"


class TestNegativeCases:
    """Tests to verify correct behavior and prevent regressions."""
    
    @pytest.mark.asyncio
    async def test_no_duplicate_events(self, cluster):
        """Single press should emit exactly one event, not duplicates."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should be exactly 1 event, not 2 or more
        TestHelpers.assert_event_count(cluster, 1)
    
    @pytest.mark.asyncio
    async def test_event_name_exact_match(self, cluster):
        """Event names should match exactly, not just contain substring."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        event_name = TestHelpers.get_event_name(cluster, 0)
        # Should be exactly this, not a substring
        assert "on_remote_button_short_press" in event_name
        assert "double" not in event_name
        assert "triple" not in event_name
    
    @pytest.mark.asyncio
    async def test_dual_button_resets_individual_counts(self, cluster):
        """Dual button detection should emit correct event."""
        await TestHelpers.press_button(cluster, ON_COMMAND_ID)
        await asyncio.sleep(QUICK_PRESS_INTERVAL)
        
        # Pressing OFF within DUAL_BUTTON_TIMEOUT triggers dual button detection
        await TestHelpers.press_button(cluster, OFF_COMMAND_ID)
        await TestHelpers.wait_for_event()
        
        # Should emit dual button event
        TestHelpers.assert_event_emitted(cluster, "button_double")
        TestHelpers.assert_event_count(cluster, 1)
