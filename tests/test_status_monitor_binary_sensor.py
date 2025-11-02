"""Tests for Status Monitor binary sensor."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    StatusMonitorBinarySensor,
    StatusMonitorConfig,
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
    return StatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        location_device_id="test_location_456",
    )


@pytest.fixture
def sensor(sensor_config):
    """Create a Status Monitor binary sensor."""
    return StatusMonitorBinarySensor(sensor_config)


class TestStatusMonitorInitialization:
    """Tests for Status Monitor initialization."""

    def test_initialization(self, sensor):
        """Test sensor initialization."""
        assert sensor.name == "Test Garden Status"
        assert sensor.unique_id == "plant_assistant_test_entry_123_test_garden_status"
        assert sensor.device_class.value == "problem"

    def test_initial_state(self, sensor):
        """Test initial state is None."""
        assert sensor.is_on is None


class TestStatusMonitorIconProperty:
    """Tests for Status Monitor icon property."""

    def test_icon_when_on(self, sensor):
        """Test icon when state is on."""
        sensor._state = True
        assert sensor.icon == "mdi:alert-circle-outline"

    def test_icon_when_off(self, sensor):
        """Test icon when state is off."""
        sensor._state = False
        assert sensor.icon == "mdi:check-circle-outline"

    def test_icon_when_none(self, sensor):
        """Test icon when state is None."""
        sensor._state = None
        assert sensor.icon == "mdi:check-circle-outline"


class TestStatusMonitorStateAttributes:
    """Tests for Status Monitor state attributes."""

    def test_attributes_no_problems(self, sensor):
        """Test attributes when no problems detected."""
        sensor._status_sensors = {
            "Plant Count Status": False,
            "Soil Moisture Status": False,
            "Temperature Status": False,
        }
        sensor._state = False

        attrs = sensor.extra_state_attributes
        assert attrs["message"] == "0 Issues"
        assert attrs["problem_sensors"] == []
        assert attrs["total_sensors_monitored"] == 3
        assert attrs["master_tag"] == "Zone A"

    def test_attributes_with_problems(self, sensor):
        """Test attributes when problems detected."""
        sensor._status_sensors = {
            "Plant Count Status": False,
            "Soil Moisture Status": True,
            "Temperature Status": True,
        }
        sensor._state = True

        attrs = sensor.extra_state_attributes
        assert attrs["message"] == "2 Issues"
        assert len(attrs["problem_sensors"]) == 2
        assert "Soil Moisture Status" in attrs["problem_sensors"]
        assert "Temperature Status" in attrs["problem_sensors"]
        assert attrs["total_sensors_monitored"] == 3
        assert attrs["master_tag"] == "Zone A"

    def test_attributes_mixed_states(self, sensor):
        """Test attributes with mixed sensor states."""
        sensor._status_sensors = {
            "Plant Count Status": False,
            "Soil Moisture Status": None,
            "Temperature Status": True,
        }
        sensor._state = True

        attrs = sensor.extra_state_attributes
        assert attrs["message"] == "1 Issue"
        assert attrs["problem_sensors"] == ["Temperature Status"]
        assert attrs["master_tag"] == "Zone A"

    def test_master_tag_attribute(self, sensor):
        """Test that master_tag attribute contains irrigation zone name."""
        sensor._status_sensors = {
            "Plant Count Status": False,
        }
        attrs = sensor.extra_state_attributes
        assert "master_tag" in attrs
        assert attrs["master_tag"] == "Zone A"
        assert attrs["master_tag"] == sensor.irrigation_zone_name

    def test_master_tag_attribute_different_zone(self, mock_hass):
        """Test master_tag attribute with different irrigation zone name."""
        config = StatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry_123",
            location_name="Test Garden",
            irrigation_zone_name="Zone B",
            location_device_id="test_location_456",
        )
        sensor = StatusMonitorBinarySensor(config)
        sensor._status_sensors = {"Plant Count Status": False}

        attrs = sensor.extra_state_attributes
        assert attrs["master_tag"] == "Zone B"


class TestStatusMonitorAvailability:
    """Tests for Status Monitor availability."""

    def test_available_with_sensors(self, sensor):
        """Test sensor is available when status sensors found."""
        sensor._status_sensors = {"Plant Count Status": False}
        assert sensor.available is True

    def test_unavailable_without_sensors(self, sensor):
        """Test sensor is unavailable when no status sensors found."""
        sensor._status_sensors = {}
        assert sensor.available is False


class TestStatusMonitorDeviceInfo:
    """Tests for Status Monitor device info."""

    def test_device_info_with_device_id(self, sensor):
        """Test device info when device_id is set."""
        device_info = sensor.device_info
        assert device_info is not None
        assert (DOMAIN, "test_location_456") in device_info["identifiers"]

    def test_device_info_without_device_id(self, mock_hass):
        """Test device info when device_id is not set."""
        config = StatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry_123",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            location_device_id=None,
        )
        sensor = StatusMonitorBinarySensor(config)
        assert sensor.device_info is None


class TestStatusMonitorStateLogic:
    """Tests for Status Monitor state logic."""

    def test_update_state_no_problems(self, sensor):
        """Test state update when no problems detected."""
        sensor._status_sensors = {
            "Plant Count Status": False,
            "Soil Moisture Status": False,
            "Temperature Status": False,
        }
        sensor._update_state()
        assert sensor.is_on is False

    def test_update_state_one_problem(self, sensor):
        """Test state update when one sensor has problem."""
        sensor._status_sensors = {
            "Plant Count Status": False,
            "Soil Moisture Status": True,
            "Temperature Status": False,
        }
        sensor._update_state()
        assert sensor.is_on is True

    def test_update_state_multiple_problems(self, sensor):
        """Test state update when multiple sensors have problems."""
        sensor._status_sensors = {
            "Plant Count Status": True,
            "Soil Moisture Status": True,
            "Temperature Status": False,
        }
        sensor._update_state()
        assert sensor.is_on is True

    def test_update_state_all_problems(self, sensor):
        """Test state update when all sensors have problems."""
        sensor._status_sensors = {
            "Plant Count Status": True,
            "Soil Moisture Status": True,
            "Temperature Status": True,
        }
        sensor._update_state()
        assert sensor.is_on is True

    def test_update_state_with_none_values(self, sensor):
        """Test state update with None values (unavailable sensors)."""
        sensor._status_sensors = {
            "Plant Count Status": None,
            "Soil Moisture Status": True,
            "Temperature Status": None,
        }
        sensor._update_state()
        assert sensor.is_on is True

    def test_update_state_all_none_values(self, sensor):
        """Test state update when all sensors are None."""
        sensor._status_sensors = {
            "Plant Count Status": None,
            "Soil Moisture Status": None,
            "Temperature Status": None,
        }
        sensor._update_state()
        assert sensor.is_on is False


class TestStatusMonitorFindStatusSensors:
    """Tests for Status Monitor finding status sensors."""

    @pytest.mark.asyncio
    async def test_find_status_sensors_empty(self, sensor, mock_entity_registry):
        """Test finding status sensors when none exist."""
        mock_entity_registry.entities.values.return_value = []
        result = await sensor._find_status_sensors()
        assert result == {}

    @pytest.mark.asyncio
    async def test_find_status_sensors_finds_plant_count(
        self, sensor, mock_entity_registry
    ):
        """Test finding plant count status sensor."""
        mock_entity = MagicMock()
        mock_entity.platform = DOMAIN
        mock_entity.domain = "binary_sensor"
        mock_entity.unique_id = (
            "plant_assistant_test_entry_123_test_garden_plant_count_status"
        )
        mock_entity.entity_id = "binary_sensor.test_garden_plant_count_status"

        mock_entity_registry.entities.values.return_value = [mock_entity]
        result = await sensor._find_status_sensors()
        assert "Plant Count Status" in result
        assert (
            result["Plant Count Status"]
            == "binary_sensor.test_garden_plant_count_status"
        )

    @pytest.mark.asyncio
    async def test_find_status_sensors_finds_soil_moisture_status(
        self, sensor, mock_entity_registry
    ):
        """Test finding soil moisture status sensor."""
        mock_entity = MagicMock()
        mock_entity.platform = DOMAIN
        mock_entity.domain = "binary_sensor"
        mock_entity.unique_id = (
            "plant_assistant_test_entry_123_test_garden_soil_moisture_status"
        )
        mock_entity.entity_id = "binary_sensor.test_garden_soil_moisture_status"

        mock_entity_registry.entities.values.return_value = [mock_entity]
        result = await sensor._find_status_sensors()
        assert "Soil Moisture Status" in result

    @pytest.mark.asyncio
    async def test_find_status_sensors_excludes_ignored_statuses(
        self, sensor, mock_entity_registry
    ):
        """Test that ignored statuses sensor is excluded."""
        mock_entity = MagicMock()
        mock_entity.platform = DOMAIN
        mock_entity.domain = "binary_sensor"
        mock_entity.unique_id = (
            "plant_assistant_test_entry_123_test_garden_ignored_statuses"
        )
        mock_entity.entity_id = "binary_sensor.test_garden_ignored_statuses"

        mock_entity_registry.entities.values.return_value = [mock_entity]
        result = await sensor._find_status_sensors()
        assert result == {}

    @pytest.mark.asyncio
    async def test_find_status_sensors_multiple_sensors(
        self, sensor, mock_entity_registry
    ):
        """Test finding multiple status sensors."""
        mock_entities = []

        # Plant Count Status
        entity1 = MagicMock()
        entity1.platform = DOMAIN
        entity1.domain = "binary_sensor"
        entity1.unique_id = (
            "plant_assistant_test_entry_123_test_garden_plant_count_status"
        )
        entity1.entity_id = "binary_sensor.test_garden_plant_count_status"
        mock_entities.append(entity1)

        # Soil Moisture Status
        entity2 = MagicMock()
        entity2.platform = DOMAIN
        entity2.domain = "binary_sensor"
        entity2.unique_id = (
            "plant_assistant_test_entry_123_test_garden_soil_moisture_status"
        )
        entity2.entity_id = "binary_sensor.test_garden_soil_moisture_status"
        mock_entities.append(entity2)

        # Temperature Status
        entity3 = MagicMock()
        entity3.platform = DOMAIN
        entity3.domain = "binary_sensor"
        entity3.unique_id = (
            "plant_assistant_test_entry_123_test_garden_temperature_status"
        )
        entity3.entity_id = "binary_sensor.test_garden_temperature_status"
        mock_entities.append(entity3)

        # Ignored Statuses (should be excluded)
        entity4 = MagicMock()
        entity4.platform = DOMAIN
        entity4.domain = "binary_sensor"
        entity4.unique_id = (
            "plant_assistant_test_entry_123_test_garden_ignored_statuses"
        )
        entity4.entity_id = "binary_sensor.test_garden_ignored_statuses"
        mock_entities.append(entity4)

        mock_entity_registry.entities.values.return_value = mock_entities
        result = await sensor._find_status_sensors()

        assert len(result) == 3
        assert "Plant Count Status" in result
        assert "Soil Moisture Status" in result
        assert "Temperature Status" in result
        # Ignored Statuses should not be in result
        assert not any("Ignored" in key for key in result)
