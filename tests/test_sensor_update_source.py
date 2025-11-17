"""Tests for sensor source entity update functionality."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.plant_assistant.sensor import (
    HumidityLinkedSensor,
    MonitoringSensor,
)


class TestMonitoringSensorUpdate:
    """Test MonitoringSensor async_update_source_entity method."""

    @pytest.mark.asyncio
    async def test_update_source_entity(self):
        """Test updating source entity ID for MonitoringSensor."""
        hass = Mock()
        hass.data = {}
        hass.states = MagicMock()
        hass.async_create_task = AsyncMock()

        # Create initial state
        initial_state = Mock()
        initial_state.state = "25.5"
        initial_state.attributes = {
            "unit_of_measurement": "°C",
            "device_class": "temperature",
        }

        # Create new state for renamed entity
        new_state = Mock()
        new_state.state = "26.0"
        new_state.attributes = {
            "unit_of_measurement": "°C",
            "device_class": "temperature",
        }

        hass.states.get = MagicMock(
            side_effect=lambda eid: {
                "sensor.old_temp": initial_state,
                "sensor.new_temp": new_state,
            }.get(eid)
        )

        config = {
            "entry_id": "test_entry",
            "source_entity_id": "sensor.old_temp",
            "source_entity_unique_id": "unique_temp_123",
            "device_name": "Test Device",
            "entity_name": "Temperature",
            "sensor_type": "temperature",
        }

        # Mock entity registry
        with patch(
            "custom_components.plant_assistant.sensor.er.async_get",
            return_value=None,
        ):
            sensor = MonitoringSensor(hass, config, location_device_id="test_location")

        # Verify initial setup
        assert sensor.source_entity_id == "sensor.old_temp"
        assert sensor._state == "25.5"

        # Mock async_write_ha_state to avoid Home Assistant internals
        sensor.async_write_ha_state = Mock()

        # Mock async_track_state_change_event
        with patch(
            "custom_components.plant_assistant.sensor.async_track_state_change_event",
            return_value=MagicMock(),
        ) as mock_track:
            # Update to new entity ID
            await sensor.async_update_source_entity("sensor.new_temp")

            # Verify the update
            assert sensor.source_entity_id == "sensor.new_temp"
            assert sensor._state == "26.0"
            assert sensor._attributes["source_entity"] == "sensor.new_temp"

            # Verify re-subscription
            mock_track.assert_called_once()


class TestHumidityLinkedSensorUpdate:
    """Test HumidityLinkedSensor async_update_source_entity method."""

    @pytest.mark.asyncio
    async def test_update_humidity_entity(self):
        """Test updating humidity entity ID for HumidityLinkedSensor."""
        hass = Mock()
        hass.data = {}
        hass.states = MagicMock()
        hass.async_create_task = AsyncMock()

        # Create initial state
        initial_state = Mock()
        initial_state.state = "45"
        initial_state.attributes = {
            "unit_of_measurement": "%",
            "device_class": "humidity",
        }

        # Create new state for renamed entity
        new_state = Mock()
        new_state.state = "50"
        new_state.attributes = {
            "unit_of_measurement": "%",
            "device_class": "humidity",
        }

        hass.states.get = MagicMock(
            side_effect=lambda eid: {
                "sensor.old_humidity": initial_state,
                "sensor.new_humidity": new_state,
            }.get(eid)
        )

        # Mock entity registry
        with patch(
            "custom_components.plant_assistant.sensor.er.async_get",
            return_value=None,
        ):
            sensor = HumidityLinkedSensor(
                hass=hass,
                entry_id="test_entry",
                location_device_id="test_location",
                location_name="Test Location",
                humidity_entity_id="sensor.old_humidity",
                humidity_entity_unique_id="unique_humidity_123",
            )

        # Verify initial setup
        assert sensor.humidity_entity_id == "sensor.old_humidity"
        assert sensor._state == "45"

        # Mock async_write_ha_state to avoid Home Assistant internals
        sensor.async_write_ha_state = Mock()

        # Mock async_track_state_change_event
        with patch(
            "custom_components.plant_assistant.sensor.async_track_state_change_event",
            return_value=MagicMock(),
        ) as mock_track:
            # Update to new entity ID
            await sensor.async_update_source_entity("sensor.new_humidity")

            # Verify the update
            assert sensor.humidity_entity_id == "sensor.new_humidity"
            assert sensor._state == "50"
            assert sensor._attributes["source_entity"] == "sensor.new_humidity"

            # Verify re-subscription
            mock_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_humidity_entity_not_found(self):
        """Test updating humidity entity when new entity doesn't exist."""
        hass = Mock()
        hass.data = {}
        hass.states = MagicMock()
        hass.async_create_task = AsyncMock()

        # Create initial state
        initial_state = Mock()
        initial_state.state = "45"
        initial_state.attributes = {
            "unit_of_measurement": "%",
            "device_class": "humidity",
        }

        hass.states.get = MagicMock(
            side_effect=lambda eid: {
                "sensor.old_humidity": initial_state,
            }.get(eid)
        )  # sensor.new_humidity doesn't exist

        # Mock entity registry
        with patch(
            "custom_components.plant_assistant.sensor.er.async_get",
            return_value=None,
        ):
            sensor = HumidityLinkedSensor(
                hass=hass,
                entry_id="test_entry",
                location_device_id="test_location",
                location_name="Test Location",
                humidity_entity_id="sensor.old_humidity",
                humidity_entity_unique_id="unique_humidity_123",
            )

        # Verify initial setup
        assert sensor.humidity_entity_id == "sensor.old_humidity"
        assert sensor._state == "45"

        # Mock async_write_ha_state to avoid Home Assistant internals
        sensor.async_write_ha_state = Mock()

        # Mock async_track_state_change_event
        with patch(
            "custom_components.plant_assistant.sensor.async_track_state_change_event",
            return_value=MagicMock(),
        ) as mock_track:
            # Update to non-existent entity ID
            await sensor.async_update_source_entity("sensor.new_humidity")

            # Verify the entity ID was updated even though state wasn't found
            assert sensor.humidity_entity_id == "sensor.new_humidity"

            # Verify re-subscription was attempted
            mock_track.assert_called_once()
