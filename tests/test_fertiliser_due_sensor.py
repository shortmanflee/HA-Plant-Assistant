"""Tests for the irrigation zone fertiliser due sensor."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import Mock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util

from custom_components.plant_assistant.sensor import (
    IrrigationZoneFertiliserDueSensor,
)


def create_device_registry_mock() -> Mock:
    """Create a mock device registry."""
    registry = Mock()

    # Create mock zone device
    zone_device = Mock()
    zone_device.id = "abc123"
    zone_device.name = "Irrigation Zone"
    zone_device.parent_device_id = "parent123"
    zone_device.identifiers = {("esphome", "abc123")}

    # Create mock parent device
    parent_device = Mock()
    parent_device.id = "parent123"
    parent_device.name = "ESP32 Device"
    parent_device.parent_device_id = None

    # Create mock fertiliser tank device
    tank_device = Mock()
    tank_device.id = "tank123"
    tank_device.name = "Fertiliser Tank"
    tank_device.parent_device_id = "parent123"

    devices = {
        "abc123": zone_device,
        "parent123": parent_device,
        "tank123": tank_device,
    }
    # Create a mock devices dict that returns the correct device
    mock_devices = Mock()
    mock_devices.values = Mock(return_value=devices.values())
    registry.devices = mock_devices
    registry.async_get = Mock(side_effect=lambda device_id: devices.get(device_id))

    return registry


def create_entity_registry_mock() -> Mock:
    """Create a mock entity registry."""
    registry = Mock()

    # Create mock fertiliser enabled switch entity
    fertiliser_switch = Mock()
    fertiliser_switch.device_id = "tank123"
    fertiliser_switch.domain = "switch"
    fertiliser_switch.name = "Fertiliser Enabled"
    fertiliser_switch.entity_id = "switch.esp32dev_fertiliser_enabled"
    fertiliser_switch.unique_id = "esp32dev_fertiliser_enabled"

    # Create mock last fertiliser injection sensor entity
    last_injection_sensor = Mock()
    last_injection_sensor.device_id = "abc123"
    last_injection_sensor.domain = "sensor"
    last_injection_sensor.name = "Last Fertiliser Injection"
    last_injection_sensor.entity_id = "sensor.zone_1_last_fertiliser_injection"
    last_injection_sensor.unique_id = "zone_1_last_fertiliser_injection"

    entities = [fertiliser_switch, last_injection_sensor]
    registry.entities = {e.entity_id: e for e in entities}
    registry.entities.values = Mock(return_value=entities)

    return registry


@pytest.fixture
def hass_mock() -> Mock:
    """Create a mock Home Assistant instance."""
    return Mock()


@pytest.fixture
def sensor(hass_mock: Mock) -> IrrigationZoneFertiliserDueSensor:
    """Create a fertiliser due sensor instance."""
    # Mock the registries for device discovery
    with (
        patch("custom_components.plant_assistant.sensor.dr.async_get") as mock_dr,
        patch(
            "custom_components.plant_assistant.sensor.find_device_entities_by_pattern"
        ) as mock_find,
    ):
        mock_dr.return_value = create_device_registry_mock()

        # Mock the entity discovery to return different entities based on domain
        def find_entities_side_effect(_hass, _device_id, domain, pattern_keywords):
            if domain == "sensor" and "last_fertiliser_injection" in pattern_keywords:
                return {
                    "last_fertiliser_injection": (
                        "sensor.zone_1_last_fertiliser_injection",
                        "zone_1_last_fertiliser_injection",
                    )
                }
            if domain == "switch" and "allow_fertiliser_injection" in pattern_keywords:
                return {
                    "allow_fertiliser_injection": (
                        "switch.zone_1_allow_fertiliser_injection",
                        "zone_1_allow_fertiliser_injection",
                    )
                }
            if domain == "number" and "fertiliser_injection_days" in pattern_keywords:
                return {
                    "fertiliser_injection_days": (
                        "number.zone_1_fertiliser_injection_days",
                        "zone_1_fertiliser_injection_days",
                    )
                }
            return {}

        mock_find.side_effect = find_entities_side_effect

        return IrrigationZoneFertiliserDueSensor(
            hass=hass_mock,
            entry_id="test_entry",
            zone_device_id=("esphome", "abc123"),
            zone_name="Front Garden",
            zone_id="zone-1",
        )


class MockState:
    """Mock state object."""

    def __init__(self, state: str) -> None:
        """Initialize the mock state."""
        self.state = state
        self.attributes: dict[str, Any] = {}


class TestIrrigationZoneFertiliserDueSensor:
    """Test the fertiliser due sensor."""

    def test_sensor_attributes(self, sensor: IrrigationZoneFertiliserDueSensor) -> None:
        """Test sensor attributes are correctly set."""
        assert sensor._attr_name == "Front Garden Fertiliser Due"
        assert sensor._attr_icon == "mdi:water-opacity"
        assert sensor._attr_options == ["off", "on"]
        assert sensor._attr_device_class == "enum"
        assert sensor._attr_unique_id is not None
        assert "abc123" in str(sensor._attr_unique_id)
        assert "fertiliser_due" in str(sensor._attr_unique_id)

    def test_native_value_returns_state(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test native_value returns the internal state."""
        assert sensor.native_value == "off"
        sensor._state = "on"
        assert sensor.native_value == "on"

    def test_get_entity_state_available(
        self, hass_mock: Mock, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test getting an available entity state."""
        state = MockState("on")
        hass_mock.states.get.return_value = state
        result = sensor._get_entity_state("switch.test")
        assert result == "on"

    def test_get_entity_state_unavailable(
        self, hass_mock: Mock, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test getting an unavailable entity state returns None."""
        state = MockState(STATE_UNAVAILABLE)
        hass_mock.states.get.return_value = state
        result = sensor._get_entity_state("switch.test")
        assert result is None

    def test_get_entity_state_unknown(
        self, hass_mock: Mock, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test getting an unknown entity state returns None."""
        state = MockState(STATE_UNKNOWN)
        hass_mock.states.get.return_value = state
        result = sensor._get_entity_state("switch.test")
        assert result is None

    def test_get_entity_state_missing(
        self, hass_mock: Mock, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test getting a missing entity state returns None."""
        hass_mock.states.get.return_value = None
        result = sensor._get_entity_state("switch.missing")
        assert result is None

    def test_parse_datetime_state_valid(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test parsing a valid datetime string."""
        dt_str = "2025-01-15T10:30:00+00:00"
        result = sensor._parse_datetime_state(dt_str)
        assert result is not None
        assert isinstance(result, datetime)

    def test_parse_datetime_state_invalid(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test parsing an invalid datetime string returns None."""
        result = sensor._parse_datetime_state("not-a-datetime")
        assert result is None

    def test_parse_datetime_state_none(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test parsing None returns None."""
        result = sensor._parse_datetime_state(None)
        assert result is None

    def test_parse_datetime_state_unavailable(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test parsing unavailable state returns None."""
        result = sensor._parse_datetime_state(STATE_UNAVAILABLE)
        assert result is None

    def test_evaluate_fertiliser_due_zone_disabled(
        self, hass_mock: Mock, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test evaluation returns False when zone fertiliser is disabled."""

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("off")
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is False

    def test_evaluate_fertiliser_due_zero_schedule(
        self, hass_mock: Mock, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test evaluation returns False when schedule is 0."""

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("0")
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is False

    def test_evaluate_fertiliser_due_negative_schedule(
        self, hass_mock: Mock, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test evaluation returns False when schedule is negative."""

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("-5")
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is False

    def test_evaluate_fertiliser_due_invalid_schedule(
        self, hass_mock: Mock, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test evaluation returns False when schedule cannot be parsed."""

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("invalid")
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is False

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_outside_season_january(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation returns False when outside fertiliser season."""
        # Set current month to January (outside April-September)
        january_date = datetime(2025, 1, 15, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = january_date

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is False

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_outside_season_october(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation returns False when outside fertiliser season (October)."""
        # Set current month to October (outside April-September)
        october_date = datetime(2025, 10, 15, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = october_date

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is False

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_no_previous_injection(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation returns True when no previous injection recorded."""
        # Set current month to May (in season)
        may_date = datetime(2025, 5, 15, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = may_date

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            if "last_fertiliser_injection" in entity_id:
                return None
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is True

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_not_yet_due(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation returns False when fertiliser is not yet due."""
        # Last injection was 3 days ago, schedule is 7 days
        current = datetime(2025, 5, 18, 10, 30, tzinfo=dt_util.UTC)
        last_injection = "2025-05-15T10:30:00+00:00"

        mock_now.return_value = current

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            if "last_fertiliser_injection" in entity_id:
                return MockState(last_injection)
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is False

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_is_due(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation returns True when fertiliser is due."""
        # Last injection was 7 days ago, schedule is 7 days
        current = datetime(2025, 5, 22, 10, 30, tzinfo=dt_util.UTC)
        last_injection = "2025-05-15T10:30:00+00:00"

        mock_now.return_value = current

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            if "last_fertiliser_injection" in entity_id:
                return MockState(last_injection)
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is True

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_is_overdue(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation returns True when fertiliser is overdue."""
        # Last injection was 10 days ago, schedule is 7 days
        current = datetime(2025, 5, 25, 10, 30, tzinfo=dt_util.UTC)
        last_injection = "2025-05-15T10:30:00+00:00"

        mock_now.return_value = current

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            if "last_fertiliser_injection" in entity_id:
                return MockState(last_injection)
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is True

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_in_season_april(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation works in April (season starts)."""
        current = datetime(2025, 4, 15, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = current

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            if "last_fertiliser_injection" in entity_id:
                return None
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is True

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_in_season_september(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation works in September (season ends)."""
        current = datetime(2025, 9, 15, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = current

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            if "last_fertiliser_injection" in entity_id:
                return None
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is True

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_evaluate_fertiliser_due_invalid_last_injection_date(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test evaluation returns False when last injection date is invalid."""
        current = datetime(2025, 5, 25, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = current

        def side_effect(entity_id: str) -> MockState | None:
            if "allow_fertiliser_injection" in entity_id:
                return MockState("on")
            if "fertiliser_injection_days" in entity_id:
                return MockState("7")
            if "last_fertiliser_injection" in entity_id:
                return MockState("invalid-date")
            return MockState("on")

        hass_mock.states.get.side_effect = side_effect

        result = sensor._evaluate_fertiliser_due()
        assert result is False

    def test_zone_id_normalization(
        self, hass_mock: Mock
    ) -> IrrigationZoneFertiliserDueSensor:
        """Test that zone IDs are normalized from dashes to underscores."""
        sensor = IrrigationZoneFertiliserDueSensor(
            hass=hass_mock,
            entry_id="test_entry",
            zone_device_id=("esphome", "abc123"),
            zone_name="Front Garden",
            zone_id="zone-1",
        )

        hass_mock.states.get.side_effect = [
            MockState("on"),  # system switch
            MockState("on"),  # zone enabled - using zone_1 format
        ]

        # Check that _build_entity_id is called with zone_1 format
        sensor._get_entity_state("input_boolean.zone_1_fertiliser_injection")
        hass_mock.states.get.assert_called()

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_handle_esphome_event_triggers_update(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test that esphome event triggers state update."""
        current = datetime(2025, 5, 15, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = current

        hass_mock.states.get.side_effect = [
            MockState("on"),  # zone enabled
            MockState("7"),  # schedule days
            None,  # no last injection - should be True
        ]

        # Initially state is "off"
        assert sensor._state == "off"

        # Create mock event
        event = Mock()
        event.data = {}

        # Mock async_write_ha_state
        sensor.async_write_ha_state = Mock()

        # Handle event
        sensor._handle_esphome_event(event)

        # State should now be "on"
        assert sensor._state == "on"

    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    def test_handle_esphome_event_no_state_change(
        self,
        mock_now: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test that esphome event doesn't trigger update if state unchanged."""
        current = datetime(2025, 1, 15, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = current

        hass_mock.states.get.side_effect = [
            MockState("on"),  # zone enabled
            MockState("7"),  # schedule days
        ]

        # Initially state is "off"
        assert sensor._state == "off"

        # Create mock event
        event = Mock()
        event.data = {}

        # Mock async_write_ha_state to track calls
        sensor.async_write_ha_state = Mock()

        # Handle event - outside season, should remain "off"
        sensor._handle_esphome_event(event)

        # State should still be "off"
        assert sensor._state == "off"
        # async_write_ha_state should not be called since state didn't change
        sensor.async_write_ha_state.assert_not_called()

    def test_extra_state_attributes(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test extra state attributes."""
        sensor._attributes = {
            "last_evaluation": "2025-01-15T10:30:00+00:00",
            "event_type": "esphome.irrigation_gateway_update",
            "zone_id": "zone-1",
        }

        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "last_evaluation" in attrs
        assert attrs["zone_id"] == "zone-1"

    def test_extra_state_attributes_empty(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test extra state attributes when empty."""
        sensor._attributes = {}
        attrs = sensor.extra_state_attributes
        # When attributes are empty, the property returns empty dict instead of None
        assert attrs == {} or attrs is None

    @patch(
        "custom_components.plant_assistant.sensor.IrrigationZoneFertiliserDueSensor.async_get_last_state"
    )
    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    async def test_async_added_to_hass_restores_state(
        self,
        mock_now: Mock,
        mock_get_last_state: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test that async_added_to_hass restores previous state."""
        mock_now.return_value = datetime(2025, 5, 15, 10, 30, tzinfo=dt_util.UTC)

        # Mock previous state
        last_state = Mock()
        last_state.state = "on"
        last_state.attributes = {"zone_id": "zone-1"}

        mock_get_last_state.return_value = last_state

        # Set up subscription mock
        hass_mock.bus.async_listen.return_value = Mock()

        # Call async_added_to_hass
        await sensor.async_added_to_hass()

        # Check that state was restored
        assert sensor._state == "on"
        assert "zone_id" in sensor._attributes

    @patch(
        "custom_components.plant_assistant.sensor.IrrigationZoneFertiliserDueSensor.async_get_last_state"
    )
    @patch("custom_components.plant_assistant.sensor.dt_util.now")
    async def test_async_added_to_hass_evaluates_if_no_state(
        self,
        mock_now: Mock,
        mock_get_last_state: Mock,
        hass_mock: Mock,
        sensor: IrrigationZoneFertiliserDueSensor,
    ) -> None:
        """Test that async_added_to_hass evaluates if no previous state."""
        current = datetime(2025, 5, 15, 10, 30, tzinfo=dt_util.UTC)
        mock_now.return_value = current

        # No previous state
        mock_get_last_state.return_value = None

        hass_mock.states.get.side_effect = [
            MockState("on"),  # zone enabled
            MockState("7"),  # schedule days
            None,  # no last injection - should be True
        ]

        # Set up subscription mock
        hass_mock.bus.async_listen.return_value = Mock()

        # Call async_added_to_hass
        await sensor.async_added_to_hass()

        # Check that state was evaluated to "on"
        assert sensor._state == "on"

    async def test_async_will_remove_from_hass(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test cleanup when entity is removed."""
        # Set up mock unsubscribe
        mock_unsubscribe = Mock()
        sensor._unsubscribe = mock_unsubscribe

        await sensor.async_will_remove_from_hass()

        # Check that unsubscribe was called
        mock_unsubscribe.assert_called_once()

    async def test_async_will_remove_from_hass_no_unsubscribe(
        self, sensor: IrrigationZoneFertiliserDueSensor
    ) -> None:
        """Test cleanup when there is no unsubscribe function."""
        sensor._unsubscribe = None

        # Should not raise exception
        await sensor.async_will_remove_from_hass()
