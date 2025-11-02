"""Tests for Link Monitor binary sensor."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    LinkMonitorBinarySensor,
    LinkMonitorConfig,
    LinkStatusBinarySensor,
)
from custom_components.plant_assistant.const import DOMAIN


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.data = {}
    hass.async_create_task = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=lambda: None)
    return hass


@pytest.fixture
def mock_device_registry():
    """Create a mock device registry."""
    return MagicMock()


@pytest.fixture
def sensor_config(mock_hass):
    """Create a default sensor configuration."""
    return LinkMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        monitoring_device_id="device_monitor_456",
        location_device_id="test_location_789",
    )


class TestLinkMonitorBinarySensorInit:
    """Test initialization of LinkMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = LinkMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Monitor Link"
        expected_unique_id = f"{DOMAIN}_test_entry_123_test_garden_monitor_link"
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.monitoring_device_id == "device_monitor_456"
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = LinkMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            monitoring_device_id="device_monitor",
            location_device_id="test_location",
        )
        sensor = LinkMonitorBinarySensor(config)

        # BinarySensorDeviceClass.CONNECTIVITY has a value of 'connectivity'
        assert sensor._attr_device_class == "connectivity"

    def test_sensor_initial_state(self, sensor_config):
        """Test that sensor starts with None state."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        assert sensor._state is None
        assert sensor._device_available is None


class TestLinkMonitorBinarySensorStateUpdate:
    """Test state update logic for LinkMonitorBinarySensor."""

    def test_update_state_when_device_available(self, sensor_config):
        """Test state update when device is available."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._device_available = True
        sensor._update_state()

        # When device is available, state should be True (connected)
        assert sensor._state is True

    def test_update_state_when_device_unavailable(self, sensor_config):
        """Test state update when device is unavailable."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._device_available = False
        sensor._update_state()

        # When device is unavailable, state should be False (disconnected)
        assert sensor._state is False

    def test_update_state_when_device_unknown(self, sensor_config):
        """Test state update when device availability is unknown."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._device_available = None
        sensor._update_state()

        # When device availability is unknown, state should be None
        assert sensor._state is None


class TestLinkMonitorBinarySensorProperty:
    """Test properties of LinkMonitorBinarySensor."""

    def test_is_on_property_when_unavailable(self, sensor_config):
        """Test is_on property when device is unavailable."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._state = True
        assert sensor.is_on is True

    def test_is_on_property_when_available(self, sensor_config):
        """Test is_on property when device is available."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._state = False
        assert sensor.is_on is False

    def test_is_on_property_when_unknown(self, sensor_config):
        """Test is_on property when state is unknown."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._state = None
        assert sensor.is_on is None

    def test_icon_when_unavailable(self, sensor_config):
        """Test icon when device is unavailable."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._state = True
        assert sensor.icon == "mdi:link"

    def test_icon_when_available(self, sensor_config):
        """Test icon when device is available."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._state = False
        assert sensor.icon == "mdi:link-off"

    def test_icon_when_unknown(self, sensor_config):
        """Test icon when state is unknown."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._state = None
        assert sensor.icon == "mdi:link-off"

    def test_available_property(self, sensor_config):
        """Test that sensor is always available."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        assert sensor.available is True

    def test_device_info(self, sensor_config):
        """Test device info property."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        device_info = sensor.device_info

        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, "test_location_789")}

    def test_device_info_without_location_device_id(self, mock_hass):
        """Test device info when location_device_id is not provided."""
        config = LinkMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            monitoring_device_id="device_monitor",
        )
        sensor = LinkMonitorBinarySensor(config)
        device_info = sensor.device_info

        assert device_info is None

    def test_extra_state_attributes_when_unavailable(self, sensor_config):
        """Test extra state attributes when device is unavailable."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._state = True
        sensor._device_available = False

        attributes = sensor.extra_state_attributes

        assert attributes["monitoring_device_id"] == "device_monitor_456"

    def test_extra_state_attributes_when_available(self, sensor_config):
        """Test extra state attributes when device is available."""
        sensor = LinkMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._device_available = True

        attributes = sensor.extra_state_attributes

        assert attributes["monitoring_device_id"] == "device_monitor_456"


class TestLinkMonitorBinarySensorDeviceAvailability:
    """Test device availability checking."""

    def test_check_device_availability_available(
        self, sensor_config, mock_device_registry
    ):
        """Test checking device availability when device is available."""
        mock_device = MagicMock()
        mock_device.disabled_by = None
        mock_device_registry.async_get.return_value = mock_device

        with patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ):
            sensor = LinkMonitorBinarySensor(sensor_config)
            # Mock entity availability check
            with patch.object(
                sensor, "_check_device_entity_availability", return_value=True
            ):
                result = sensor._check_device_availability()

        assert result is True

    def test_check_device_availability_unavailable_by_entities(
        self, sensor_config, mock_device_registry
    ):
        """Test checking device availability when all entities are unavailable."""
        mock_device = MagicMock()
        mock_device.disabled_by = None
        mock_device_registry.async_get.return_value = mock_device

        with patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ):
            sensor = LinkMonitorBinarySensor(sensor_config)
            # Mock entity availability check returning False
            with patch.object(
                sensor, "_check_device_entity_availability", return_value=False
            ):
                result = sensor._check_device_availability()

        assert result is False

    def test_check_device_entity_availability_all_available(
        self, sensor_config, mock_device_registry
    ):
        """Test device entity availability when at least one entity is available."""
        # Create mock entities
        mock_entity1 = MagicMock()
        mock_entity1.entity_id = "sensor.device_temperature"
        mock_entity1.device_id = "device_monitor_456"

        mock_entity2 = MagicMock()
        mock_entity2.entity_id = "sensor.device_humidity"
        mock_entity2.device_id = "device_monitor_456"

        mock_device_registry.entities.values.return_value = [mock_entity1, mock_entity2]

        # Mock entity states
        temp_state = MagicMock()
        temp_state.state = "22.5"
        humidity_state = MagicMock()
        humidity_state.state = "45"

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_device_registry,
        ):
            sensor = LinkMonitorBinarySensor(sensor_config)
            sensor.hass.states.get = MagicMock(
                side_effect=lambda eid: (
                    temp_state if eid == "sensor.device_temperature" else humidity_state
                )
            )
            result = sensor._check_device_entity_availability()

        assert result is True

    def test_check_device_entity_availability_all_unavailable(
        self, sensor_config, mock_device_registry
    ):
        """Test device entity availability when all entities are unavailable."""
        # Create mock entities
        mock_entity1 = MagicMock()
        mock_entity1.entity_id = "sensor.device_temperature"
        mock_entity1.device_id = "device_monitor_456"

        mock_entity2 = MagicMock()
        mock_entity2.entity_id = "sensor.device_humidity"
        mock_entity2.device_id = "device_monitor_456"

        mock_device_registry.entities.values.return_value = [mock_entity1, mock_entity2]

        # Mock entity states as unavailable
        unavailable_state = MagicMock()
        unavailable_state.state = STATE_UNAVAILABLE

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_device_registry,
        ):
            sensor = LinkMonitorBinarySensor(sensor_config)
            sensor.hass.states.get = MagicMock(return_value=unavailable_state)
            result = sensor._check_device_entity_availability()

        assert result is False

    def test_check_device_entity_availability_no_entities(
        self, sensor_config, mock_device_registry
    ):
        """Test device entity availability when device has no entities."""
        mock_device_registry.entities.values.return_value = []

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_device_registry,
        ):
            sensor = LinkMonitorBinarySensor(sensor_config)
            result = sensor._check_device_entity_availability()

        assert result is None


class TestLinkStatusBinarySensorInit:
    """Test initialization of LinkStatusBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = LinkStatusBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Monitor Link Status"
        expected_unique_id = f"{DOMAIN}_test_entry_123_test_garden_monitor_link_status"
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.monitoring_device_id == "device_monitor_456"
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = LinkMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            monitoring_device_id="device_monitor",
            location_device_id="test_location",
        )
        sensor = LinkStatusBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_initial_state(self, sensor_config):
        """Test that sensor starts with None state."""
        sensor = LinkStatusBinarySensor(sensor_config)
        assert sensor._state is None
        assert sensor._device_available is None


class TestLinkStatusBinarySensorStateUpdate:
    """Test state update logic for LinkStatusBinarySensor."""

    def test_update_state_when_device_available(self, sensor_config):
        """Test state update when device is available."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._device_available = True
        sensor._update_state()

        # When device is available, state should be False (no problem)
        assert sensor._state is False

    def test_update_state_when_device_unavailable(self, sensor_config):
        """Test state update when device is unavailable."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._device_available = False
        sensor._update_state()

        # When device is unavailable, state should be True (problem)
        assert sensor._state is True

    def test_update_state_when_device_unknown(self, sensor_config):
        """Test state update when device availability is unknown."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._device_available = None
        sensor._update_state()

        # When device availability is unknown, state should be None
        assert sensor._state is None


class TestLinkStatusBinarySensorProperty:
    """Test properties of LinkStatusBinarySensor."""

    def test_is_on_property_when_unavailable(self, sensor_config):
        """Test is_on property when device is unavailable."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._state = True
        assert sensor.is_on is True

    def test_is_on_property_when_available(self, sensor_config):
        """Test is_on property when device is available."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._state = False
        assert sensor.is_on is False

    def test_is_on_property_when_unknown(self, sensor_config):
        """Test is_on property when state is unknown."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._state = None
        assert sensor.is_on is None

    def test_icon_when_unavailable(self, sensor_config):
        """Test icon when device is unavailable."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._state = True
        assert sensor.icon == "mdi:link-off"

    def test_icon_when_available(self, sensor_config):
        """Test icon when device is available."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._state = False
        assert sensor.icon == "mdi:link"

    def test_icon_when_unknown(self, sensor_config):
        """Test icon when state is unknown."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._state = None
        assert sensor.icon == "mdi:link"

    def test_available_property(self, sensor_config):
        """Test that sensor is always available."""
        sensor = LinkStatusBinarySensor(sensor_config)
        assert sensor.available is True

    def test_device_info(self, sensor_config):
        """Test device info property."""
        sensor = LinkStatusBinarySensor(sensor_config)
        device_info = sensor.device_info

        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, "test_location_789")}

    def test_device_info_without_location_device_id(self, mock_hass):
        """Test device info when location_device_id is not provided."""
        config = LinkMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            monitoring_device_id="device_monitor",
        )
        sensor = LinkStatusBinarySensor(config)
        device_info = sensor.device_info

        assert device_info is None

    def test_extra_state_attributes_when_unavailable(self, sensor_config):
        """Test extra state attributes when device is unavailable."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._state = True
        sensor._device_available = False

        attributes = sensor.extra_state_attributes

        assert attributes["type"] == "Critical"
        assert attributes["message"] == "Monitoring device unavailable"
        assert attributes["task"] is True
        assert attributes["device_available"] is False
        assert attributes["monitoring_device_id"] == "device_monitor_456"
        assert "test_garden" in attributes["tags"]
        assert "zone_a" in attributes["tags"]

    def test_extra_state_attributes_when_available(self, sensor_config):
        """Test extra state attributes when device is available."""
        sensor = LinkStatusBinarySensor(sensor_config)
        sensor._state = False
        sensor._device_available = True

        attributes = sensor.extra_state_attributes

        assert attributes["type"] == "Normal"
        assert attributes["message"] == "Monitoring device available"
        assert attributes["task"] is False
        assert attributes["device_available"] is True
