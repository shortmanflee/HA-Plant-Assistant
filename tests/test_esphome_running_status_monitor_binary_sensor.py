"""Tests for ESPHome Running Status Monitor binary sensor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import Event, EventStateChangedData, HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    ESPHomeRunningStatusMonitorBinarySensor,
    ESPHomeRunningStatusMonitorConfig,
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
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=lambda: None)
    return hass


@pytest.fixture
def sensor_config(mock_hass):
    """Create a default sensor configuration."""
    return ESPHomeRunningStatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Irrigation Zone A",
        irrigation_zone_name="Zone A",
        monitoring_device_id="esphome_device_abc123",
        zone_device_identifier=("esphome", "device_abc123"),
    )


class TestESPHomeRunningStatusMonitorBinarySensorInit:
    """Test initialization of ESPHomeRunningStatusMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Irrigation Zone A Status"
        expected_unique_id = (
            f"{DOMAIN}_test_entry_123_esphome_device_abc123_esphome_running_status"
        )
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.monitoring_device_id == "esphome_device_abc123"
        assert sensor.location_name == "Irrigation Zone A"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = ESPHomeRunningStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Zone",
            irrigation_zone_name="Zone A",
            monitoring_device_id="esphome_device",
            zone_device_identifier=("esphome", "device_123"),
        )
        sensor = ESPHomeRunningStatusMonitorBinarySensor(config)

        # BinarySensorDeviceClass.RUNNING has a value of 'running'
        assert sensor._attr_device_class == "running"

    def test_sensor_initial_state(self, sensor_config):
        """Test that sensor starts with None state."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        assert sensor._state is None
        assert sensor._running_sensor_entity_id is None


class TestESPHomeRunningStatusMonitorBinarySensorStateUpdate:
    """Test state update logic for ESPHomeRunningStatusMonitorBinarySensor."""

    def test_update_state_running_sensor_on(self, sensor_config):
        """Test state update when running sensor is ON."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = "binary_sensor.device_running"

        # Mock the running sensor state
        mock_state = MagicMock()
        mock_state.state = "on"
        sensor_config.hass.states.get.return_value = mock_state

        sensor._update_state()

        # When running sensor is on, state should be True (problem)
        assert sensor._state is True

    def test_update_state_running_sensor_off(self, sensor_config):
        """Test state update when running sensor is OFF."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = "binary_sensor.device_running"

        # Mock the running sensor state
        mock_state = MagicMock()
        mock_state.state = "off"
        sensor_config.hass.states.get.return_value = mock_state

        sensor._update_state()

        # When running sensor is off, state should be False (no problem)
        assert sensor._state is False

    def test_update_state_no_running_sensor_found(self, sensor_config):
        """Test state update when no running sensor is found."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = None

        sensor._update_state()

        # When no running sensor found, state should be None (unavailable)
        assert sensor._state is None

    def test_update_state_running_sensor_unavailable(self, sensor_config):
        """Test state update when running sensor is unavailable."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = "binary_sensor.device_running"

        # Mock unavailable state
        sensor_config.hass.states.get.return_value = None

        sensor._update_state()

        # When running sensor is unavailable, state should be None
        assert sensor._state is None


class TestESPHomeRunningStatusMonitorBinarySensorFindRunning:
    """Test finding running binary sensor on device."""

    def test_find_running_binary_sensor_found(self, sensor_config):
        """Test finding running binary sensor when it exists."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        # Mock entity registry
        mock_entity = MagicMock()
        mock_entity.device_id = "esphome_device_abc123"
        mock_entity.domain = "binary_sensor"
        mock_entity.entity_id = "binary_sensor.device_running"

        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {
            "binary_sensor.device_running": mock_entity,
        }

        # Mock entity state with running device class
        mock_state = MagicMock()
        mock_state.attributes = {"device_class": "running"}

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_entity_registry,
        ):
            sensor_config.hass.states.get.return_value = mock_state
            result = sensor._find_running_binary_sensor()

        assert result == "binary_sensor.device_running"

    def test_find_running_binary_sensor_not_found(self, sensor_config):
        """Test finding running binary sensor when it doesn't exist."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        # Mock entity registry with no running sensor
        mock_entity = MagicMock()
        mock_entity.device_id = "esphome_device_abc123"
        mock_entity.domain = "binary_sensor"
        mock_entity.entity_id = "binary_sensor.device_other"

        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {
            "binary_sensor.device_other": mock_entity,
        }

        # Mock entity state with different device class
        mock_state = MagicMock()
        mock_state.attributes = {"device_class": "connectivity"}

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_entity_registry,
        ):
            sensor_config.hass.states.get.return_value = mock_state
            result = sensor._find_running_binary_sensor()

        assert result is None

    def test_find_running_binary_sensor_multiple_sensors(self, sensor_config):
        """Test finding running binary sensor when multiple sensors exist."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        # Mock entity registry with multiple sensors
        mock_entity1 = MagicMock()
        mock_entity1.device_id = "esphome_device_abc123"
        mock_entity1.domain = "binary_sensor"
        mock_entity1.entity_id = "binary_sensor.device_other"

        mock_entity2 = MagicMock()
        mock_entity2.device_id = "esphome_device_abc123"
        mock_entity2.domain = "binary_sensor"
        mock_entity2.entity_id = "binary_sensor.device_running"

        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {
            "binary_sensor.device_other": mock_entity1,
            "binary_sensor.device_running": mock_entity2,
        }

        # Mock entity states
        def mock_states_get(entity_id: str) -> MagicMock:
            mock_state = MagicMock()
            if entity_id == "binary_sensor.device_running":
                mock_state.attributes = {"device_class": "running"}
            else:
                mock_state.attributes = {"device_class": "connectivity"}
            return mock_state

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_entity_registry,
        ):
            sensor_config.hass.states.get.side_effect = mock_states_get
            result = sensor._find_running_binary_sensor()

        assert result == "binary_sensor.device_running"

    def test_find_running_binary_sensor_wrong_device(self, sensor_config):
        """Test that only running sensor on correct device is found."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        # Mock entity registry with sensor on different device
        mock_entity = MagicMock()
        mock_entity.device_id = "different_device_id"
        mock_entity.domain = "binary_sensor"
        mock_entity.entity_id = "binary_sensor.other_device_running"

        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {
            "binary_sensor.other_device_running": mock_entity,
        }

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_entity_registry,
        ):
            result = sensor._find_running_binary_sensor()

        assert result is None


class TestESPHomeRunningStatusMonitorBinarySensorProperty:
    """Test properties of ESPHomeRunningStatusMonitorBinarySensor."""

    def test_is_on_property_when_running(self, sensor_config):
        """Test is_on property when device is running."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        assert sensor.is_on is True

    def test_is_on_property_when_not_running(self, sensor_config):
        """Test is_on property when device is not running."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        assert sensor.is_on is False

    def test_is_on_property_when_unknown(self, sensor_config):
        """Test is_on property when state is unknown."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = None
        assert sensor.is_on is None

    def test_icon_when_running(self, sensor_config):
        """Test icon when device is running."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        assert sensor.icon == "mdi:play-circle-outline"

    def test_icon_when_not_running(self, sensor_config):
        """Test icon when device is not running."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        assert sensor.icon == "mdi:stop-circle-outline"

    def test_icon_when_unknown_state(self, sensor_config):
        """Test icon when state is unknown."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = None
        assert sensor.icon == "mdi:stop-circle-outline"

    def test_available_property_when_running_sensor_found(self, sensor_config):
        """Test that sensor is available when running sensor is found."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = "binary_sensor.device_running"

        assert sensor.available is True

    def test_available_property_when_running_sensor_not_found(self, sensor_config):
        """Test that sensor is unavailable when running sensor is not found."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = None

        assert sensor.available is False

    def test_device_info(self, sensor_config):
        """Test device info property."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        device_info = sensor.device_info

        assert device_info is not None
        assert device_info.get("identifiers") == {("esphome", "device_abc123")}

    def test_extra_state_attributes_when_running(self, sensor_config):
        """Test extra state attributes when device is running."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        sensor._running_sensor_entity_id = "binary_sensor.device_running"

        attributes = sensor.extra_state_attributes

        assert attributes["type"] == "Warning"
        assert attributes["message"] == "Device Running"
        assert attributes["task"] is True
        assert attributes["device_id"] == "esphome_device_abc123"
        assert attributes["running_sensor_entity"] == "binary_sensor.device_running"
        assert "zone_a" in attributes["tags"]

    def test_extra_state_attributes_when_not_running(self, sensor_config):
        """Test extra state attributes when device is not running."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._running_sensor_entity_id = "binary_sensor.device_running"

        attributes = sensor.extra_state_attributes

        assert attributes["type"] == "Warning"
        assert attributes["message"] == "Device Stopped"
        assert attributes["task"] is False
        assert attributes["device_id"] == "esphome_device_abc123"

    def test_extra_state_attributes_tags(self, sensor_config):
        """Test that tags are correctly formatted."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._running_sensor_entity_id = "binary_sensor.device_running"

        attributes = sensor.extra_state_attributes

        # Tags should be lowercase with underscores
        assert "zone_a" in attributes["tags"]


class TestESPHomeRunningStatusMonitorBinarySensorStateChanges:
    """Test handling of state changes."""

    def test_running_sensor_state_changed_to_on(self, sensor_config):
        """Test handling running sensor state change to ON."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = "binary_sensor.device_running"
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "on"
        sensor_config.hass.states.get.return_value = new_state

        event = create_state_changed_event(new_state)
        sensor._running_sensor_state_changed(event)

        assert sensor._state is True
        sensor.async_write_ha_state.assert_called_once()

    def test_running_sensor_state_changed_to_off(self, sensor_config):
        """Test handling running sensor state change to OFF."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = "binary_sensor.device_running"
        sensor._state = True
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "off"
        sensor_config.hass.states.get.return_value = new_state

        event = create_state_changed_event(new_state)
        sensor._running_sensor_state_changed(event)

        assert sensor._state is False
        sensor.async_write_ha_state.assert_called_once()

    def test_running_sensor_state_changed_with_none(self, sensor_config):
        """Test handling running sensor state change with None value."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._running_sensor_entity_id = "binary_sensor.device_running"
        sensor._state = True
        sensor.async_write_ha_state = MagicMock()

        sensor_config.hass.states.get.return_value = None

        event = create_state_changed_event(None)
        sensor._running_sensor_state_changed(event)

        assert sensor._state is None
        sensor.async_write_ha_state.assert_called_once()


class TestESPHomeRunningStatusMonitorBinarySensorAsyncMethods:
    """Test async methods."""

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_running_sensor(self, sensor_config):
        """Test async_added_to_hass when running sensor exists."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()
        sensor.async_get_last_state = AsyncMock(return_value=None)

        # Mock entity registry
        mock_entity = MagicMock()
        mock_entity.device_id = "esphome_device_abc123"
        mock_entity.domain = "binary_sensor"
        mock_entity.entity_id = "binary_sensor.device_running"

        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {
            "binary_sensor.device_running": mock_entity,
        }

        # Mock running sensor state
        mock_running_state = MagicMock()
        mock_running_state.state = "on"
        mock_running_state.attributes = {"device_class": "running"}

        def mock_states_get(entity_id: str) -> MagicMock | None:
            if entity_id == "binary_sensor.device_running":
                return mock_running_state
            return None

        sensor_config.hass.states.get.side_effect = mock_states_get

        with (
            patch(
                "custom_components.plant_assistant.binary_sensor.er.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "custom_components.plant_assistant.binary_sensor.async_track_state_change_event",
                return_value=MagicMock(),
            ),
        ):
            await sensor.async_added_to_hass()

        assert sensor._running_sensor_entity_id == "binary_sensor.device_running"
        assert sensor._state is True

    @pytest.mark.asyncio
    async def test_async_added_to_hass_no_running_sensor(self, sensor_config):
        """Test async_added_to_hass when running sensor not available."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()
        sensor.async_get_last_state = AsyncMock(return_value=None)

        # Mock empty entity registry
        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {}

        sensor_config.hass.states.get.return_value = None

        with (
            patch(
                "custom_components.plant_assistant.binary_sensor.er.async_get",
                return_value=mock_entity_registry,
            ),
            patch(
                "custom_components.plant_assistant.binary_sensor.async_track_state_change_event",
                return_value=MagicMock(),
            ),
        ):
            await sensor.async_added_to_hass()

        assert sensor._running_sensor_entity_id is None
        assert sensor._state is None

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass(self, sensor_config):
        """Test async_will_remove_from_hass method."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        mock_unsubscribe = MagicMock()
        sensor._unsubscribe = mock_unsubscribe

        await sensor.async_will_remove_from_hass()

        mock_unsubscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass_no_subscription(self, sensor_config):
        """Test async_will_remove_from_hass when no subscription exists."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        sensor._unsubscribe = None

        # Should not raise exception
        await sensor.async_will_remove_from_hass()

    @pytest.mark.asyncio
    async def test_restore_previous_state_from_on(self, sensor_config):
        """Test restoring previous state when it was on."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        last_state = MagicMock()
        last_state.state = "on"

        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor._restore_previous_state()

        assert sensor._state is True

    @pytest.mark.asyncio
    async def test_restore_previous_state_from_off(self, sensor_config):
        """Test restoring previous state when it was off."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        last_state = MagicMock()
        last_state.state = "off"

        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor._restore_previous_state()

        assert sensor._state is False

    @pytest.mark.asyncio
    async def test_restore_previous_state_unavailable(self, sensor_config):
        """Test restoring previous state when it was unavailable."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)
        last_state = MagicMock()
        last_state.state = "unavailable"

        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor._restore_previous_state()

        # State should remain None since we're restoring from unavailable
        assert sensor._state is None

    @pytest.mark.asyncio
    async def test_restore_previous_state_no_last_state(self, sensor_config):
        """Test restoring previous state when no last state exists."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        sensor.async_get_last_state = AsyncMock(return_value=None)

        await sensor._restore_previous_state()

        assert sensor._state is None


class TestESPHomeRunningStatusMonitorBinarySensorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_device_class_attribute(self, sensor_config):
        """Test handling entity with empty device_class attribute."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        # Mock entity registry
        mock_entity = MagicMock()
        mock_entity.device_id = "esphome_device_abc123"
        mock_entity.domain = "binary_sensor"
        mock_entity.entity_id = "binary_sensor.device_other"

        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {
            "binary_sensor.device_other": mock_entity,
        }

        # Mock entity state with missing device_class
        mock_state = MagicMock()
        mock_state.attributes = {}

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_entity_registry,
        ):
            sensor_config.hass.states.get.return_value = mock_state
            result = sensor._find_running_binary_sensor()

        assert result is None

    def test_entity_registry_error_handling(self, sensor_config):
        """Test handling of errors when accessing entity registry."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            side_effect=AttributeError("Test error"),
        ):
            result = sensor._find_running_binary_sensor()

        assert result is None

    def test_state_get_error_handling(self, sensor_config):
        """Test handling of errors when getting state."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        # Mock entity registry
        mock_entity = MagicMock()
        mock_entity.device_id = "esphome_device_abc123"
        mock_entity.domain = "binary_sensor"
        mock_entity.entity_id = "binary_sensor.device_running"

        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {
            "binary_sensor.device_running": mock_entity,
        }

        sensor_config.hass.states.get.side_effect = ValueError("Test error")

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_entity_registry,
        ):
            result = sensor._find_running_binary_sensor()

        assert result is None

    def test_multiple_devices_only_finds_correct_device(self, sensor_config):
        """Test that only running sensor from correct device is found."""
        sensor = ESPHomeRunningStatusMonitorBinarySensor(sensor_config)

        # Mock entity registry with sensors from multiple devices
        mock_entity1 = MagicMock()
        mock_entity1.device_id = "other_device_id"
        mock_entity1.domain = "binary_sensor"
        mock_entity1.entity_id = "binary_sensor.other_running"

        mock_entity2 = MagicMock()
        mock_entity2.device_id = "esphome_device_abc123"
        mock_entity2.domain = "binary_sensor"
        mock_entity2.entity_id = "binary_sensor.device_running"

        mock_entity_registry = MagicMock()
        mock_entity_registry.entities = {
            "binary_sensor.other_running": mock_entity1,
            "binary_sensor.device_running": mock_entity2,
        }

        def mock_states_get(_entity_id: str) -> MagicMock:
            mock_state = MagicMock()
            mock_state.attributes = {"device_class": "running"}
            return mock_state

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_entity_registry,
        ):
            sensor_config.hass.states.get.side_effect = mock_states_get
            result = sensor._find_running_binary_sensor()

        # Should find the running sensor from the correct device
        assert result == "binary_sensor.device_running"
