"""Tests for Soil Moisture Status Monitor binary sensor."""

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    SoilMoistureStatusMonitorBinarySensor,
    SoilMoistureStatusMonitorConfig,
)
from custom_components.plant_assistant.const import DOMAIN


def create_state_changed_event(new_state):
    """Create an Event object for state changed callbacks."""
    event_data = EventStateChangedData(
        entity_id="sensor.test",
        old_state=None,
        new_state=new_state,
    )
    return Event("state_changed", event_data)


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
    return SoilMoistureStatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        soil_moisture_entity_id="sensor.test_moisture",
        location_device_id="test_location_456",
    )


class TestSoilMoistureStatusMonitorBinarySensorInit:
    """Test initialization of SoilMoistureStatusMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = SoilMoistureStatusMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Soil Moisture Status"
        expected_unique_id = f"{DOMAIN}_test_entry_123_test_garden_soil_moisture_status"
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.soil_moisture_entity_id == "sensor.test_moisture"
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_icon_when_moisture_low(self, mock_hass):
        """Test that sensor has correct icon when moisture is low."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # When problem detected and status is low
        sensor._state = True
        sensor._moisture_status = "low"
        assert sensor.icon == "mdi:water-minus"

    def test_sensor_icon_when_moisture_high(self, mock_hass):
        """Test that sensor has correct icon when moisture is high."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # When problem detected and status is high
        sensor._state = True
        sensor._moisture_status = "high"
        assert sensor.icon == "mdi:water-plus"

    def test_sensor_icon_when_moisture_water_soon(self, mock_hass):
        """Test that sensor has correct icon when moisture is water soon."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # When problem detected and status is water soon
        sensor._state = True
        sensor._moisture_status = "water_soon"
        assert sensor.icon == "mdi:watering-can"

    def test_sensor_icon_when_moisture_normal(self, mock_hass):
        """Test that sensor has correct icon when moisture is normal."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # When no problem
        sensor._state = False
        sensor._moisture_status = "normal"
        assert sensor.icon == "mdi:water-check"

        # When state is None (unavailable)
        sensor._state = None
        assert sensor.icon == "mdi:water-check"

    def test_sensor_device_info(self, mock_hass):
        """Test that sensor has correct device info."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location_123",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        device_info = sensor.device_info
        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, "test_location_123")}


class TestSoilMoistureStatusMonitorBinarySensorStateLogic:
    """Test state calculation logic."""

    def test_parse_float_with_valid_value(self, mock_hass):
        """Test parsing valid float values."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        assert sensor._parse_float("45.5") == 45.5
        assert sensor._parse_float("0") == 0.0
        assert sensor._parse_float("100") == 100.0

    def test_parse_float_with_invalid_value(self, mock_hass):
        """Test parsing invalid values returns None."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        assert sensor._parse_float("invalid") is None
        assert sensor._parse_float(None) is None
        assert sensor._parse_float(STATE_UNAVAILABLE) is None
        assert sensor._parse_float(STATE_UNKNOWN) is None

    def test_update_state_when_moisture_low(self, mock_hass):
        """Test that state is ON and status is 'low' when moisture is."""
        # below minimum
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        assert sensor._state is True
        assert sensor._moisture_status == "low"

    def test_update_state_when_moisture_high(self, mock_hass):
        """Test that state is ON and status is 'high' when moisture is."""
        # above maximum
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 75.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        assert sensor._state is True
        assert sensor._moisture_status == "high"

    def test_update_state_when_moisture_water_soon(self, mock_hass):
        """Test that state is ON and status is 'water_soon' when."""
        # moisture is in water soon zone
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Water soon zone is min + 5 = 30 + 5 = 35
        # So water soon is between 30 and 35
        sensor._current_soil_moisture = 32.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        assert sensor._state is True
        assert sensor._moisture_status == "water_soon"

    def test_update_state_when_moisture_normal(self, mock_hass):
        """Test that state is OFF and status is 'normal'."""
        # when moisture is within safe range (above water soon threshold)
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Water soon zone is min + 5 = 30 + 5 = 35
        # Safe is above 35
        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        assert sensor._state is False
        assert sensor._moisture_status == "normal"

    def test_update_state_when_moisture_at_min_threshold(self, mock_hass):
        """Test that state is ON (water soon) when moisture is exactly at minimum."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 30.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        # At minimum threshold should be in water soon zone
        assert sensor._state is True
        assert sensor._moisture_status == "water_soon"

    def test_update_state_when_moisture_at_water_soon_upper_limit(self, mock_hass):
        """Test that state is ON (water soon) when soil is at water soon threshold."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Water soon threshold is min + 5 = 30 + 5 = 35
        sensor._current_soil_moisture = 35.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        # At water soon upper limit should be last value in zone
        assert sensor._state is True
        assert sensor._moisture_status == "water_soon"

    def test_update_state_when_moisture_just_above_water_soon_threshold(
        self, mock_hass
    ):
        """Test that state is OFF (normal) when moisture is just above water soon."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Water soon threshold is min + 5 = 30 + 5 = 35
        # Just above would be 35.01
        sensor._current_soil_moisture = 35.01
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        assert sensor._state is False
        assert sensor._moisture_status == "normal"

    def test_update_state_when_moisture_at_max_threshold(self, mock_hass):
        """Test that state is OFF when moisture is exactly at maximum threshold."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 70.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        assert sensor._state is False
        assert sensor._moisture_status == "normal"

    def test_update_state_when_moisture_unavailable(self, mock_hass):
        """Test that state is None when moisture is unavailable."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = None
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        assert sensor._state is None
        assert sensor._moisture_status == "normal"

    def test_update_state_when_min_threshold_unavailable(self, mock_hass):
        """Test that state is None when min threshold is unavailable."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = None
        sensor._max_soil_moisture = 70.0
        sensor._update_state()

        assert sensor._state is None
        assert sensor._moisture_status == "normal"

    def test_update_state_when_max_threshold_unavailable(self, mock_hass):
        """Test that state is None when max threshold is unavailable."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = None
        sensor._update_state()

        assert sensor._state is None
        assert sensor._moisture_status == "normal"


class TestSoilMoistureStatusMonitorBinarySensorProperties:
    """Test binary sensor properties."""

    def test_is_on_returns_state(self, mock_hass):
        """Test is_on property returns current state."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._state = True
        assert sensor.is_on is True

        sensor._state = False
        assert sensor.is_on is False

        sensor._state = None
        assert sensor.is_on is None

    def test_extra_state_attributes_when_low(self, mock_hass):
        """Test that extra state attributes are set correctly when low."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._state = True
        sensor._moisture_status = "low"

        attrs = sensor.extra_state_attributes

        # Check required attributes
        assert attrs["type"] == "Critical"
        assert attrs["message"] == "Soil Moisture Low"
        assert attrs["task"] is True
        assert attrs["tags"] == ["test_garden", "zone_a"]

        # Check internal attributes
        assert attrs["current_soil_moisture"] == 25.0
        assert attrs["minimum_soil_moisture_threshold"] == 30.0
        assert attrs["maximum_soil_moisture_threshold"] == 70.0
        assert attrs["source_entity"] == "sensor.test_moisture"
        assert attrs["moisture_status"] == "low"
        assert attrs["water_soon_threshold"] == 35.0

    def test_extra_state_attributes_when_high(self, mock_hass):
        """Test that extra state attributes are set correctly when high."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 75.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._state = True
        sensor._moisture_status = "high"

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Critical"
        assert attrs["message"] == "Soil Moisture High"
        assert attrs["moisture_status"] == "high"

    def test_extra_state_attributes_when_water_soon(self, mock_hass):
        """Test that extra state attributes are set correctly when water soon."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 32.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._state = True
        sensor._moisture_status = "water_soon"

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Warning"
        assert attrs["message"] == "Soil Moisture Water_soon"
        assert attrs["moisture_status"] == "water_soon"

    def test_extra_state_attributes_when_normal(self, mock_hass):
        """Test that extra state attributes are set correctly when normal."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._state = False
        sensor._moisture_status = "normal"

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Critical"
        assert attrs["message"] == "Soil Moisture Normal"
        assert attrs["moisture_status"] == "normal"

    def test_attribute_type_values_for_all_statuses(self, mock_hass):
        """Test that type attribute has correct values for all statuses."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0

        # Test 'low' status
        sensor._current_soil_moisture = 25.0
        sensor._moisture_status = "low"
        sensor._state = True
        attrs = sensor.extra_state_attributes
        assert attrs["type"] == "Critical", "Type should be Critical for low status"

        # Test 'high' status
        sensor._current_soil_moisture = 75.0
        sensor._moisture_status = "high"
        sensor._state = True
        attrs = sensor.extra_state_attributes
        assert attrs["type"] == "Critical", "Type should be Critical for high status"

        # Test 'water_soon' status
        sensor._current_soil_moisture = 32.0
        sensor._moisture_status = "water_soon"
        sensor._state = True
        attrs = sensor.extra_state_attributes
        assert attrs["type"] == "Warning", (
            "Type should be Warning for water_soon status"
        )

        # Test 'normal' status
        sensor._current_soil_moisture = 50.0
        sensor._moisture_status = "normal"
        sensor._state = False
        attrs = sensor.extra_state_attributes
        assert attrs["type"] == "Critical", "Type should be Critical for normal status"

    def test_available_when_entity_exists(self, mock_hass):
        """Test sensor is available when entity exists."""
        mock_moisture_state = MagicMock()
        mock_moisture_state.state = "50"

        def get_state_side_effect(entity_id):
            if entity_id == "sensor.test_moisture":
                return mock_moisture_state
            return None

        mock_hass.states.get.side_effect = get_state_side_effect

        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        assert sensor.available is True

    def test_unavailable_when_entity_missing(self, mock_hass):
        """Test sensor is unavailable when entity is missing."""

        def get_state_side_effect(_entity_id):
            return None

        mock_hass.states.get.side_effect = get_state_side_effect

        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        assert sensor.available is False


class TestSoilMoistureStatusMonitorBinarySensorCallbacks:
    """Test state change callbacks."""

    def test_soil_moisture_state_changed_callback(self, mock_hass):
        """Test soil moisture state change callback."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0

        # Simulate moisture dropping below threshold
        old_state = MagicMock()
        old_state.state = "35"
        new_state = MagicMock()
        new_state.state = "25"

        event = create_state_changed_event(new_state)
        sensor._soil_moisture_state_changed(event)

        assert sensor._current_soil_moisture == 25.0
        assert sensor._state is True
        assert sensor._moisture_status == "low"
        sensor.async_write_ha_state.assert_called_once()

    def test_min_soil_moisture_state_changed_callback(self, mock_hass):
        """Test minimum soil moisture threshold change callback."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_moisture = 35.0
        sensor._max_soil_moisture = 70.0

        # Simulate threshold lowering below current moisture
        old_state = MagicMock()
        old_state.state = "30"
        new_state = MagicMock()
        new_state.state = "20"

        event = create_state_changed_event(new_state)
        sensor._min_soil_moisture_state_changed(event)

        assert sensor._min_soil_moisture == 20.0
        assert sensor._state is False  # Now within range (above water soon threshold)
        assert sensor._moisture_status == "normal"
        sensor.async_write_ha_state.assert_called_once()

    def test_max_soil_moisture_state_changed_callback(self, mock_hass):
        """Test maximum soil moisture threshold change callback."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_moisture = 65.0
        sensor._min_soil_moisture = 30.0

        # Simulate threshold raising above current moisture
        old_state = MagicMock()
        old_state.state = "60"
        new_state = MagicMock()
        new_state.state = "80"

        event = create_state_changed_event(new_state)
        sensor._max_soil_moisture_state_changed(event)

        assert sensor._max_soil_moisture == 80.0
        assert sensor._state is False  # Now within range
        assert sensor._moisture_status == "normal"
        sensor.async_write_ha_state.assert_called_once()


class TestSoilMoistureStatusMonitorBinarySensorIgnoreUntil:
    """Test ignore until datetime functionality."""

    def test_sensor_not_on_when_ignore_until_in_future(self, mock_hass):
        """Test that sensor is OFF when ignore until datetime is in the future."""
        from datetime import datetime, timedelta

        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0

        # Set ignore until to 1 hour in the future
        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        sensor._update_state()

        # Should be False (no problem) even though moisture is below threshold
        assert sensor._state is False
        assert sensor._moisture_status == "normal"

    def test_sensor_on_when_ignore_until_in_past(self, mock_hass):
        """Test that sensor is ON when ignore until datetime is in the past."""
        from datetime import datetime, timedelta

        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0

        # Set ignore until to 1 hour in the past
        past_time = datetime.now(UTC) - timedelta(hours=1)
        sensor._ignore_until_datetime = past_time

        sensor._update_state()

        # Should be True (problem) since ignore period has expired
        assert sensor._state is True
        assert sensor._moisture_status == "low"

    def test_ignore_until_datetime_state_changed_callback(self, mock_hass):
        """Test ignore until datetime state change callback."""
        from datetime import datetime, timedelta

        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0

        # Initially state should be True (problem)
        sensor._update_state()
        assert sensor._state is True

        # Simulate datetime entity state change to future time
        future_time_str = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        new_state = MagicMock()
        new_state.state = future_time_str

        event = create_state_changed_event(new_state)
        sensor._soil_moisture_ignore_until_state_changed(event)

        # State should now be False (no problem)
        assert sensor._state is False
        assert sensor._moisture_status == "normal"
        sensor.async_write_ha_state.assert_called_once()

    def test_ignore_until_datetime_cleared_when_unavailable(self, mock_hass):
        """Test that ignore until datetime is cleared when state becomes unavailable."""
        from datetime import datetime, timedelta

        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_device_id="test_location",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        # Set initial ignore until datetime
        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0

        # State should be False (no problem) due to ignore until
        sensor._update_state()
        assert sensor._state is False

        # Simulate datetime entity becoming unavailable
        new_state = MagicMock()
        new_state.state = STATE_UNAVAILABLE

        event = create_state_changed_event(new_state)
        sensor._soil_moisture_ignore_until_state_changed(event)

        # Ignore until should be cleared
        assert sensor._ignore_until_datetime is None

        # State should now be True (problem) since ignore was cleared
        assert sensor._state is True
        assert sensor._moisture_status == "low"

    def test_extra_state_attributes_includes_ignore_until(self, mock_hass):
        """Test that extra state attributes include ignore until information."""
        from datetime import datetime, timedelta

        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_device_id="test_location",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0

        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        attrs = sensor.extra_state_attributes

        assert "ignore_until" in attrs
        assert "currently_ignoring" in attrs
        assert attrs["currently_ignoring"] is True

    def test_extra_state_attributes_without_ignore_until(self, mock_hass):
        """Test that extra state attributes don't include ignore until when not set."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_device_id="test_location",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._max_soil_moisture = 70.0
        sensor._ignore_until_datetime = None

        attrs = sensor.extra_state_attributes

        assert "ignore_until" not in attrs
        assert "currently_ignoring" not in attrs


class TestSoilMoistureStatusMonitorBinarySensorCleanup:
    """Test resource cleanup."""

    async def test_async_will_remove_from_hass(self, mock_hass):
        """Test cleanup when entity is removed."""
        config = SoilMoistureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureStatusMonitorBinarySensor(config)

        # Mock the unsubscribe functions
        mock_unsubscribe = MagicMock()
        mock_unsubscribe_moisture_min = MagicMock()
        mock_unsubscribe_moisture_max = MagicMock()
        mock_unsubscribe_ignore_until = MagicMock()

        sensor._unsubscribe = mock_unsubscribe
        sensor._unsubscribe_moisture_min = mock_unsubscribe_moisture_min
        sensor._unsubscribe_moisture_max = mock_unsubscribe_moisture_max
        sensor._unsubscribe_ignore_until = mock_unsubscribe_ignore_until

        await sensor.async_will_remove_from_hass()

        # Verify all unsubscribe functions were called
        mock_unsubscribe.assert_called_once()
        mock_unsubscribe_moisture_min.assert_called_once()
        mock_unsubscribe_moisture_max.assert_called_once()
        mock_unsubscribe_ignore_until.assert_called_once()
