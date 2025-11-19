"""Tests for temperature below threshold weekly duration sensor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.sensor import (
    TemperatureBelowThresholdHoursSensor,
)


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
        "custom_components.plant_assistant.sensor.er.async_get",
        return_value=registry,
    ):
        yield registry


async def test_temperature_below_threshold_sensor_init(mock_hass):
    """Test initialization of TemperatureBelowThresholdHoursSensor."""
    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_device_id="test_location_456",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    assert (
        sensor._attr_name == "Test Garden Temperature Below Threshold Weekly Duration"
    )
    expected = (
        f"{DOMAIN}_test_entry_123_test_garden_"
        "temperature_below_threshold_weekly_duration"
    )
    assert sensor._attr_unique_id == expected
    assert sensor._attr_native_unit_of_measurement == "hours"
    assert sensor._attr_icon == "mdi:thermometer-alert"
    assert sensor._temperature_entity_id == "sensor.test_temperature"


async def test_temperature_below_threshold_sensor_available(mock_hass):
    """Test sensor availability based on temperature entity."""
    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Test when temperature entity is available
    mock_state = MagicMock()
    mock_state.state = "20.5"
    mock_hass.states.get.return_value = mock_state
    assert sensor.available is True

    # Test when temperature entity is unavailable
    mock_hass.states.get.return_value = None
    assert sensor.available is False


async def test_temperature_below_threshold_no_min_temp_entity(mock_hass):
    """Test calculation when no minimum temperature entity exists."""
    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # No min temperature entity in registry
    result = await sensor._calculate_hours_below_threshold()
    assert result is None


async def test_temperature_below_threshold_min_temp_unavailable(
    mock_hass, mock_entity_registry
):
    """Test calculation when minimum temperature threshold is unavailable."""
    # Set up mock entity registry with min_temperature entity
    mock_min_temp_entity = MagicMock()
    mock_min_temp_entity.platform = DOMAIN
    mock_min_temp_entity.domain = "sensor"
    mock_min_temp_entity.unique_id = f"{DOMAIN}_test_entry_min_temperature"
    mock_min_temp_entity.entity_id = "sensor.test_garden_min_temperature"
    mock_entity_registry.entities.values.return_value = [mock_min_temp_entity]

    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Mock min temp state as unavailable
    mock_min_temp_state = MagicMock()
    mock_min_temp_state.state = STATE_UNAVAILABLE
    mock_hass.states.get.return_value = mock_min_temp_state

    result = await sensor._calculate_hours_below_threshold()
    assert result is None


async def test_temperature_below_threshold_no_statistics(
    mock_hass, mock_entity_registry
):
    """Test calculation when no statistics are available."""
    # Set up mock entity registry with min_temperature entity
    mock_min_temp_entity = MagicMock()
    mock_min_temp_entity.platform = DOMAIN
    mock_min_temp_entity.domain = "sensor"
    mock_min_temp_entity.unique_id = f"{DOMAIN}_test_entry_min_temperature"
    mock_min_temp_entity.entity_id = "sensor.test_garden_min_temperature"
    mock_entity_registry.entities.values.return_value = [mock_min_temp_entity]

    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Mock min temp state
    mock_min_temp_state = MagicMock()
    mock_min_temp_state.state = "5.0"
    mock_hass.states.get.return_value = mock_min_temp_state

    # Mock recorder instance
    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(return_value={})

    with (
        patch(
            "custom_components.plant_assistant.sensor.get_instance",
            return_value=mock_recorder,
        ),
        patch(
            "custom_components.plant_assistant.sensor.statistics_during_period"
        ) as mock_stats_fn,
    ):
        mock_stats_fn.return_value = {}
        result = await sensor._calculate_hours_below_threshold()
        assert result is None


async def test_temperature_below_threshold_calculation(mock_hass, mock_entity_registry):
    """Test calculation of hours below threshold."""
    # Set up mock entity registry with min_temperature entity
    mock_min_temp_entity = MagicMock()
    mock_min_temp_entity.platform = DOMAIN
    mock_min_temp_entity.domain = "sensor"
    mock_min_temp_entity.unique_id = f"{DOMAIN}_test_entry_min_temperature"
    mock_min_temp_entity.entity_id = "sensor.test_garden_min_temperature"
    mock_entity_registry.entities.values.return_value = [mock_min_temp_entity]

    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Mock min temp state (threshold is 5°C)
    mock_min_temp_state = MagicMock()
    mock_min_temp_state.state = "5.0"
    mock_hass.states.get.return_value = mock_min_temp_state

    # Mock statistics data
    mock_stats = {
        "sensor.test_temperature": [
            {"mean": 3.0},  # Below threshold
            {"mean": 4.5},  # Below threshold
            {"mean": 6.0},  # Above threshold
            {"mean": 2.0},  # Below threshold
            {"mean": 8.0},  # Above threshold
        ]
    }

    # Mock recorder instance
    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(return_value=mock_stats)

    # Patch both get_instance and statistics_during_period
    with (
        patch(
            "custom_components.plant_assistant.sensor.get_instance",
            return_value=mock_recorder,
        ),
        patch(
            "custom_components.plant_assistant.sensor.statistics_during_period"
        ) as mock_stats_fn,
    ):
        mock_stats_fn.return_value = mock_stats
        result = await sensor._calculate_hours_below_threshold()
        # Should count 3 hours below threshold (3.0, 4.5, 2.0)
        assert result == 3


async def test_temperature_state_changed_callback(mock_hass):
    """Test temperature state change callback."""
    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Trigger state change with a mock event
    event = MagicMock()
    sensor._temperature_state_changed(event)

    # Verify async_create_task was called to schedule the update
    mock_hass.async_create_task.assert_called_once()

    # Close the coroutine that was passed to async_create_task to avoid warnings
    coroutine = mock_hass.async_create_task.call_args[0][0]
    coroutine.close()


async def test_async_update_state(mock_hass, mock_entity_registry):
    """Test async state update recalculates and writes state."""
    # Set up mock entity registry with min_temperature entity
    mock_min_temp_entity = MagicMock()
    mock_min_temp_entity.platform = DOMAIN
    mock_min_temp_entity.domain = "sensor"
    mock_min_temp_entity.unique_id = f"{DOMAIN}_test_entry_min_temperature"
    mock_min_temp_entity.entity_id = "sensor.test_garden_min_temperature"
    mock_entity_registry.entities.values.return_value = [mock_min_temp_entity]

    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Mock async_write_ha_state
    sensor.async_write_ha_state = MagicMock()

    # Mock min temp state
    mock_min_temp_state = MagicMock()
    mock_min_temp_state.state = "5.0"
    mock_hass.states.get.return_value = mock_min_temp_state

    # Mock statistics data
    mock_stats = {
        "sensor.test_temperature": [
            {"mean": 3.0},  # Below threshold
            {"mean": 6.0},  # Above threshold
        ]
    }

    # Mock recorder instance
    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(return_value=mock_stats)

    with (
        patch(
            "custom_components.plant_assistant.sensor.get_instance",
            return_value=mock_recorder,
        ),
        patch(
            "custom_components.plant_assistant.sensor.statistics_during_period"
        ) as mock_stats_fn,
    ):
        mock_stats_fn.return_value = mock_stats

        # Execute the update
        await sensor._async_update_state()

        # Verify state was calculated
        assert sensor._state == 1  # One hour below threshold

        # Verify attributes were set
        assert sensor._attributes["source_entity"] == "sensor.test_temperature"
        assert sensor._attributes["period_days"] == 7

        # Verify state was written to HA
        sensor.async_write_ha_state.assert_called_once()


async def test_native_value_handling(mock_hass):
    """Test native_value property with different states."""
    sensor = TemperatureBelowThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Test with valid state
    sensor._state = 10
    assert sensor.native_value == 10

    # Test with unavailable state
    sensor._state = STATE_UNAVAILABLE
    assert sensor.native_value is None

    # Test with unknown state
    sensor._state = STATE_UNKNOWN
    assert sensor.native_value is None

    # Test with None state
    sensor._state = None
    assert sensor.native_value is None
