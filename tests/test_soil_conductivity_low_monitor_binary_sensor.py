"""Tests for Soil Conductivity Low Monitor binary sensor."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    SoilConductivityLowMonitorBinarySensor,
    SoilConductivityLowMonitorConfig,
)
from custom_components.plant_assistant.const import DOMAIN

from .conftest import create_state_changed_event


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.data = {}
    hass.async_create_task = MagicMock()
    return hass


@pytest.fixture
def mock_entity_registry():
    """Create a mock entity registry."""
    registry = MagicMock()
    registry.entities = MagicMock()
    registry.entities.values = MagicMock(return_value=[])

    with patch(
        "custom_components.plant_assistant.binary_sensor.er.async_get",
        return_value=registry,
    ):
        yield registry


@pytest.fixture
def sensor_config(mock_hass):
    """Create a default sensor configuration."""
    return SoilConductivityLowMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        soil_conductivity_entity_id="sensor.test_conductivity",
        soil_moisture_entity_id="sensor.test_moisture",
        location_device_id="test_location_456",
    )


class TestSoilConductivityLowMonitorBinarySensorInit:
    """Test initialization of SoilConductivityLowMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = SoilConductivityLowMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Soil Conductivity Low Monitor"
        expected_unique_id = (
            f"{DOMAIN}_test_entry_123_test_garden_soil_conductivity_low_monitor"
        )
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.soil_conductivity_entity_id == "sensor.test_conductivity"
        assert sensor.soil_moisture_entity_id == "sensor.test_moisture"
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_icon(self, mock_hass):
        """Test that sensor has correct icon based on state."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # When state is True (problem detected), icon should be mdi:flash-off
        sensor._state = True
        assert sensor.icon == "mdi:flash-off"

        # When state is False (no problem), icon should be mdi:flash-check
        sensor._state = False
        assert sensor.icon == "mdi:flash-check"

        # When state is None (unavailable), icon should be mdi:flash-check (default)
        sensor._state = None
        assert sensor.icon == "mdi:flash-check"

    def test_sensor_device_info(self, mock_hass):
        """Test that sensor has correct device info."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location_123",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        device_info = sensor.device_info
        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, "test_location_123")}


class TestSoilConductivityLowMonitorBinarySensorStateLogic:
    """Test state calculation logic."""

    def test_parse_float_with_valid_value(self, mock_hass):
        """Test parsing valid float values."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        assert sensor._parse_float("45.5") == 45.5
        assert sensor._parse_float("0") == 0.0
        assert sensor._parse_float("100") == 100.0

    def test_parse_float_with_invalid_value(self, mock_hass):
        """Test parsing invalid values returns None."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        assert sensor._parse_float("invalid") is None
        assert sensor._parse_float(None) is None
        assert sensor._parse_float(STATE_UNAVAILABLE) is None
        assert sensor._parse_float(STATE_UNKNOWN) is None

    def test_update_state_when_conductivity_low_and_moisture_adequate(self, mock_hass):
        """Test that state is ON when conductivity is low and moisture is adequate."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Conductivity below threshold: 400 < 500
        # Moisture at least 10 points above threshold: 50 >= 30 + 10
        sensor._current_soil_conductivity = 400.0
        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is True

    def test_update_state_when_conductivity_high(self, mock_hass):
        """Test that state is OFF when conductivity is above threshold."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Conductivity above threshold: 600 >= 500
        sensor._current_soil_conductivity = 600.0
        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is False

    def test_update_state_when_moisture_insufficient(self, mock_hass):
        """Test that state is OFF when moisture is not 10 points above threshold."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Conductivity below threshold: 400 < 500
        # Moisture not enough above threshold: 35 < 30 + 10
        sensor._current_soil_conductivity = 400.0
        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = 35.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is False

    def test_update_state_when_moisture_exactly_at_threshold(self, mock_hass):
        """Test that state is OFF when moisture is exactly at required threshold."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Conductivity below threshold: 400 < 500
        # Moisture exactly at required threshold: 40 == 30 + 10
        sensor._current_soil_conductivity = 400.0
        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = 40.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is True

    def test_update_state_when_conductivity_unavailable(self, mock_hass):
        """Test that state is None when conductivity is unavailable."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        sensor._current_soil_conductivity = None
        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is None

    def test_update_state_when_moisture_unavailable(self, mock_hass):
        """Test that state is None when moisture is unavailable."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        sensor._current_soil_conductivity = 400.0
        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = None
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is None

    def test_update_state_when_thresholds_unavailable(self, mock_hass):
        """Test that state is None when thresholds are unavailable."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        sensor._current_soil_conductivity = 400.0
        sensor._min_soil_conductivity = None
        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is None


class TestSoilConductivityLowMonitorBinarySensorProperties:
    """Test binary sensor properties."""

    def test_is_on_returns_state(self, mock_hass):
        """Test is_on property returns current state."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        sensor._state = True
        assert sensor.is_on is True

        sensor._state = False
        assert sensor.is_on is False

        sensor._state = None
        assert sensor.is_on is None

    def test_extra_state_attributes(self, mock_hass):
        """Test that extra state attributes are set correctly."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        sensor._current_soil_conductivity = 400.0
        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0

        attrs = sensor.extra_state_attributes

        # Check required attributes from user request
        assert attrs["type"] == "Critical"
        assert attrs["message"] == "Soil Conductivity Low"
        assert attrs["task"] is True
        assert attrs["tags"] == ["test_garden", "zone_a"]

        # Check internal attributes
        assert attrs["current_soil_conductivity"] == 400.0
        assert attrs["minimum_soil_conductivity_threshold"] == 500.0
        assert attrs["current_soil_moisture"] == 50.0
        assert attrs["minimum_soil_moisture_threshold"] == 30.0
        assert attrs["source_entity"] == "sensor.test_conductivity"
        assert attrs["moisture_source_entity"] == "sensor.test_moisture"
        assert attrs["soil_moisture_threshold_for_conductivity_check"] == 40.0

    def test_available_when_both_entities_exist(self, mock_hass):
        """Test sensor is available when both entities exist."""
        mock_conductivity_state = MagicMock()
        mock_conductivity_state.state = "500"
        mock_moisture_state = MagicMock()
        mock_moisture_state.state = "50"

        def get_state_side_effect(entity_id):
            if entity_id == "sensor.test_conductivity":
                return mock_conductivity_state
            if entity_id == "sensor.test_moisture":
                return mock_moisture_state
            return None

        mock_hass.states.get.side_effect = get_state_side_effect

        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        assert sensor.available is True

    def test_unavailable_when_conductivity_missing(self, mock_hass):
        """Test sensor is unavailable when conductivity entity is missing."""
        mock_moisture_state = MagicMock()
        mock_moisture_state.state = "50"

        def get_state_side_effect(entity_id):
            if entity_id == "sensor.test_moisture":
                return mock_moisture_state
            return None

        mock_hass.states.get.side_effect = get_state_side_effect

        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        assert sensor.available is False

    def test_unavailable_when_moisture_missing(self, mock_hass):
        """Test sensor is unavailable when moisture entity is missing."""
        mock_conductivity_state = MagicMock()
        mock_conductivity_state.state = "500"

        def get_state_side_effect(entity_id):
            if entity_id == "sensor.test_conductivity":
                return mock_conductivity_state
            return None

        mock_hass.states.get.side_effect = get_state_side_effect

        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        assert sensor.available is False


class TestSoilConductivityLowMonitorBinarySensorCallbacks:
    """Test state change callbacks."""

    def test_soil_conductivity_state_changed_callback(self, mock_hass):
        """Test soil conductivity state change callback."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0

        # Simulate conductivity dropping below threshold
        old_state = MagicMock()
        old_state.state = "550"
        new_state = MagicMock()
        new_state.state = "400"

        event = create_state_changed_event(new_state)
        sensor._soil_conductivity_state_changed(event)

        assert sensor._current_soil_conductivity == 400.0
        assert sensor._state is True
        sensor.async_write_ha_state.assert_called_once()

    def test_soil_moisture_state_changed_callback(self, mock_hass):
        """Test soil moisture state change callback."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_conductivity = 400.0
        sensor._min_soil_conductivity = 500.0
        sensor._min_soil_moisture = 30.0

        # Simulate moisture increasing to meet requirement
        old_state = MagicMock()
        old_state.state = "35"
        new_state = MagicMock()
        new_state.state = "50"

        event = create_state_changed_event(new_state)
        sensor._soil_moisture_state_changed(event)

        assert sensor._current_soil_moisture == 50.0
        assert sensor._state is True  # Now meets moisture requirement
        sensor.async_write_ha_state.assert_called_once()

    def test_min_soil_conductivity_state_changed_callback(self, mock_hass):
        """Test minimum soil conductivity threshold change callback."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_conductivity = 450.0
        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0

        # Simulate threshold lowering below current conductivity
        old_state = MagicMock()
        old_state.state = "500"
        new_state = MagicMock()
        new_state.state = "400"

        event = create_state_changed_event(new_state)
        sensor._min_soil_conductivity_state_changed(event)

        assert sensor._min_soil_conductivity == 400.0
        assert sensor._state is False  # Now above threshold
        sensor.async_write_ha_state.assert_called_once()

    def test_min_soil_moisture_state_changed_callback(self, mock_hass):
        """Test minimum soil moisture threshold change callback."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_conductivity = 400.0
        sensor._min_soil_conductivity = 500.0
        sensor._current_soil_moisture = 40.0

        # Simulate threshold decreasing, making moisture check fail
        old_state = MagicMock()
        old_state.state = "25"
        new_state = MagicMock()
        new_state.state = "35"

        event = create_state_changed_event(new_state)
        sensor._min_soil_moisture_state_changed(event)

        assert sensor._min_soil_moisture == 35.0
        assert sensor._state is False  # Moisture no longer 10 points above
        sensor.async_write_ha_state.assert_called_once()


class TestSoilConductivityLowMonitorBinarySensorCleanup:
    """Test resource cleanup."""

    async def test_async_will_remove_from_hass(self, mock_hass):
        """Test cleanup when entity is removed."""
        config = SoilConductivityLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_conductivity_entity_id="sensor.test_conductivity",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilConductivityLowMonitorBinarySensor(config)

        # Mock the unsubscribe functions
        mock_unsubscribe = MagicMock()
        mock_unsubscribe_moisture = MagicMock()
        mock_unsubscribe_conductivity_min = MagicMock()
        mock_unsubscribe_moisture_min = MagicMock()

        sensor._unsubscribe = mock_unsubscribe
        sensor._unsubscribe_moisture = mock_unsubscribe_moisture
        sensor._unsubscribe_conductivity_min = mock_unsubscribe_conductivity_min
        sensor._unsubscribe_moisture_min = mock_unsubscribe_moisture_min

        await sensor.async_will_remove_from_hass()

        # Verify all unsubscribe functions were called
        mock_unsubscribe.assert_called_once()
        mock_unsubscribe_moisture.assert_called_once()
        mock_unsubscribe_conductivity_min.assert_called_once()
        mock_unsubscribe_moisture_min.assert_called_once()
