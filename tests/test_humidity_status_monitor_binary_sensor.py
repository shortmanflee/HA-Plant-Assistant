"""Tests for Humidity Status Monitor binary sensor."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    HumidityStatusMonitorBinarySensor,
    HumidityStatusMonitorConfig,
)
from custom_components.plant_assistant.const import DOMAIN


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
    return HumidityStatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        humidity_entity_id="sensor.test_humidity",
        location_device_id="test_location_456",
    )


class TestHumidityStatusMonitorBinarySensorInit:
    """Test initialization of HumidityStatusMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = HumidityStatusMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Humidity Status"
        expected_unique_id = f"{DOMAIN}_test_entry_123_test_garden_humidity_status"
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.humidity_entity_id == "sensor.test_humidity"
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_icon_when_humidity_above(self, mock_hass):
        """Test that sensor has correct icon when humidity is above threshold."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # When problem detected and status is above
        sensor._state = True
        sensor._humidity_status = "above"
        assert sensor.icon == "mdi:water-percent"

    def test_sensor_icon_when_humidity_below(self, mock_hass):
        """Test that sensor has correct icon when humidity is below threshold."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # When problem detected and status is below
        sensor._state = True
        sensor._humidity_status = "below"
        assert sensor.icon == "mdi:water-percent-alert"

    def test_sensor_icon_when_humidity_normal(self, mock_hass):
        """Test that sensor has correct icon when humidity is normal."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # When no problem
        sensor._state = False
        sensor._humidity_status = "normal"
        assert sensor.icon == "mdi:water-percent"

        # When state is None (unavailable)
        sensor._state = None
        assert sensor.icon == "mdi:water-percent"

    def test_sensor_device_info(self, mock_hass):
        """Test that sensor has correct device info."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location_123",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        device_info = sensor.device_info
        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, "test_location_123")}


class TestHumidityStatusMonitorBinarySensorStateLogic:
    """Test state calculation logic."""

    def test_parse_float_with_valid_value(self, mock_hass):
        """Test parsing valid float values."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        assert sensor._parse_float("65.5") == 65.5
        assert sensor._parse_float("0") == 0.0
        assert sensor._parse_float("100") == 100.0
        assert sensor._parse_float("50") == 50.0

    def test_parse_float_with_invalid_value(self, mock_hass):
        """Test parsing invalid values returns None."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        assert sensor._parse_float("invalid") is None
        assert sensor._parse_float(None) is None
        assert sensor._parse_float(STATE_UNAVAILABLE) is None
        assert sensor._parse_float(STATE_UNKNOWN) is None

    def test_update_state_when_above_threshold_exceeds_limit(self, mock_hass):
        """Test state is ON with 'above' status when above threshold hours > 2."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # Above threshold hours exceeds 2 hour limit
        sensor._above_threshold_hours = 3.5
        sensor._below_threshold_hours = 0.5
        sensor._update_state()

        assert sensor._state is True
        assert sensor._humidity_status == "above"

    def test_update_state_when_below_threshold_exceeds_limit(self, mock_hass):
        """Test state is ON with 'below' status when below threshold hours > 2."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # Below threshold hours exceeds 2 hour limit
        sensor._above_threshold_hours = 0.5
        sensor._below_threshold_hours = 4.0
        sensor._update_state()

        assert sensor._state is True
        assert sensor._humidity_status == "below"

    def test_update_state_when_both_below_threshold_limit(self, mock_hass):
        """Test that state is OFF and status is 'normal' when both hours are below 2."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # Both threshold hours are below 2 hour limit
        sensor._above_threshold_hours = 1.0
        sensor._below_threshold_hours = 0.5
        sensor._update_state()

        assert sensor._state is False
        assert sensor._humidity_status == "normal"

    def test_update_state_when_above_exactly_at_threshold(self, mock_hass):
        """Test that state is OFF when above threshold hours is exactly 2."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # Above threshold hours is exactly at 2 hour limit (not exceeding)
        sensor._above_threshold_hours = 2.0
        sensor._below_threshold_hours = 0.5
        sensor._update_state()

        assert sensor._state is False
        assert sensor._humidity_status == "normal"

    def test_update_state_when_below_exactly_at_threshold(self, mock_hass):
        """Test that state is OFF when below threshold hours is exactly 2."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # Below threshold hours is exactly at 2 hour limit (not exceeding)
        sensor._above_threshold_hours = 0.5
        sensor._below_threshold_hours = 2.0
        sensor._update_state()

        assert sensor._state is False
        assert sensor._humidity_status == "normal"

    def test_update_state_when_values_unavailable(self, mock_hass):
        """Test that state is None when either threshold duration is unavailable."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # Above threshold is None (unavailable)
        sensor._above_threshold_hours = None
        sensor._below_threshold_hours = 1.0
        sensor._update_state()

        assert sensor._state is None
        assert sensor._humidity_status == "normal"

        # Below threshold is None (unavailable)
        sensor._above_threshold_hours = 1.0
        sensor._below_threshold_hours = None
        sensor._update_state()

        assert sensor._state is None
        assert sensor._humidity_status == "normal"

    def test_update_state_when_above_preference_over_below(self, mock_hass):
        """Test that 'above' status takes precedence when both exceed threshold."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # Both exceed threshold limit
        sensor._above_threshold_hours = 3.5
        sensor._below_threshold_hours = 4.0
        sensor._update_state()

        # 'above' should be checked first, so status is 'above'
        assert sensor._state is True
        assert sensor._humidity_status == "above"


class TestHumidityStatusMonitorBinarySensorAttributes:
    """Test state attributes."""

    def test_extra_state_attributes_when_above_threshold(self, mock_hass):
        """Test extra state attributes when humidity is above threshold."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        sensor._state = True
        sensor._humidity_status = "above"
        sensor._above_threshold_hours = 3.5
        sensor._below_threshold_hours = 0.5

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Critical"
        assert attrs["message"] == "Humidity Above"
        assert attrs["task"] is True
        assert attrs["humidity_status"] == "above"
        assert attrs["above_threshold_hours"] == 3.5
        assert attrs["below_threshold_hours"] == 0.5
        assert attrs["threshold_hours"] == 2.0
        assert "test_garden" in attrs["tags"]
        assert "zone_a" in attrs["tags"]

    def test_extra_state_attributes_when_below_threshold(self, mock_hass):
        """Test extra state attributes when humidity is below threshold."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        sensor._state = True
        sensor._humidity_status = "below"
        sensor._above_threshold_hours = 0.5
        sensor._below_threshold_hours = 4.0

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Critical"
        assert attrs["message"] == "Humidity Below"
        assert attrs["task"] is True
        assert attrs["humidity_status"] == "below"
        assert attrs["above_threshold_hours"] == 0.5
        assert attrs["below_threshold_hours"] == 4.0
        assert attrs["threshold_hours"] == 2.0

    def test_extra_state_attributes_when_normal(self, mock_hass):
        """Test extra state attributes when humidity is normal."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        sensor._state = False
        sensor._humidity_status = "normal"
        sensor._above_threshold_hours = 1.0
        sensor._below_threshold_hours = 0.5

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Critical"
        assert attrs["message"] == "Humidity Normal"
        assert attrs["task"] is True
        assert attrs["humidity_status"] == "normal"


class TestHumidityStatusMonitorBinarySensorProperties:
    """Test sensor properties."""

    def test_is_on_property(self, mock_hass):
        """Test is_on property returns correct state."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        # Test when state is True
        sensor._state = True
        assert sensor.is_on is True

        # Test when state is False
        sensor._state = False
        assert sensor.is_on is False

        # Test when state is None
        sensor._state = None
        assert sensor.is_on is None

    def test_available_property_when_humidity_available(self, mock_hass):
        """Test available property when humidity entity is available."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )

        # Mock that humidity entity exists
        mock_state = MagicMock()
        mock_hass.states.get.return_value = mock_state

        sensor = HumidityStatusMonitorBinarySensor(config)

        assert sensor.available is True
        mock_hass.states.get.assert_called_with("sensor.test_humidity")

    def test_available_property_when_humidity_unavailable(self, mock_hass):
        """Test available property when humidity entity is not available."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )

        # Mock that humidity entity does not exist
        mock_hass.states.get.return_value = None

        sensor = HumidityStatusMonitorBinarySensor(config)

        assert sensor.available is False


class TestHumidityStatusMonitorBinarySensorStateCallbacks:
    """Test state change callbacks."""

    def test_above_threshold_state_changed_callback(self, mock_hass):
        """Test callback when above threshold state changes."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        sensor._below_threshold_hours = 1.0
        sensor.async_write_ha_state = MagicMock()

        # Create a mock new_state with state = "3.5"
        mock_new_state = MagicMock()
        mock_new_state.state = "3.5"

        sensor._above_threshold_state_changed("entity_id", None, mock_new_state)

        assert sensor._above_threshold_hours == 3.5
        assert sensor._state is True
        assert sensor._humidity_status == "above"

    def test_below_threshold_state_changed_callback(self, mock_hass):
        """Test callback when below threshold state changes."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        sensor._above_threshold_hours = 0.5
        sensor.async_write_ha_state = MagicMock()

        # Create a mock new_state with state = "4.0"
        mock_new_state = MagicMock()
        mock_new_state.state = "4.0"

        sensor._below_threshold_state_changed("entity_id", None, mock_new_state)

        assert sensor._below_threshold_hours == 4.0
        assert sensor._state is True
        assert sensor._humidity_status == "below"

    def test_above_threshold_state_changed_with_none(self, mock_hass):
        """Test callback when above threshold state becomes None."""
        config = HumidityStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            humidity_entity_id="sensor.test_humidity",
            location_device_id="test_location",
        )
        sensor = HumidityStatusMonitorBinarySensor(config)

        sensor._below_threshold_hours = 1.0
        sensor.async_write_ha_state = MagicMock()

        sensor._above_threshold_state_changed("entity_id", None, None)

        assert sensor._above_threshold_hours is None
        assert sensor._state is None
