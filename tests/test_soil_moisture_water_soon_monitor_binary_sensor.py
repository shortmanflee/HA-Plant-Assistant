"""Tests for Soil Moisture Water Soon Monitor binary sensor."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    SoilMoistureWaterSoonMonitorBinarySensor,
    SoilMoistureWaterSoonMonitorConfig,
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
    return SoilMoistureWaterSoonMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        soil_moisture_entity_id="sensor.test_moisture",
        location_device_id="test_location_456",
    )


class TestSoilMoistureWaterSoonMonitorBinarySensorInit:
    """Test initialization of SoilMoistureWaterSoonMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Soil Moisture Water Soon Monitor"
        expected_unique_id = (
            f"{DOMAIN}_test_entry_123_test_garden_soil_moisture_water_soon_monitor"
        )
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.soil_moisture_entity_id == "sensor.test_moisture"
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_icon(self, mock_hass):
        """Test that sensor has correct icon based on state."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # When state is True (warning detected), icon should be mdi:watering-can
        sensor._state = True
        assert sensor.icon == "mdi:watering-can"

        # When state is False (no warning), icon should be mdi:water-check
        sensor._state = False
        assert sensor.icon == "mdi:water-check"

        # When state is None (unavailable), icon should be mdi:water-check (default)
        sensor._state = None
        assert sensor.icon == "mdi:water-check"

    def test_sensor_device_info(self, mock_hass):
        """Test that sensor has correct device info."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location_123",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        device_info = sensor.device_info
        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, "test_location_123")}


class TestSoilMoistureWaterSoonMonitorBinarySensorStateLogic:
    """Test state calculation logic."""

    def test_parse_float_with_valid_value(self, mock_hass):
        """Test parsing valid float values."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        assert sensor._parse_float("45.5") == 45.5
        assert sensor._parse_float("0") == 0.0
        assert sensor._parse_float("100") == 100.0

    def test_parse_float_with_invalid_value(self, mock_hass):
        """Test parsing invalid values returns None."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        assert sensor._parse_float("invalid") is None
        assert sensor._parse_float(None) is None
        assert sensor._parse_float(STATE_UNAVAILABLE) is None
        assert sensor._parse_float(STATE_UNKNOWN) is None

    def test_update_state_when_in_water_soon_zone(self, mock_hass):
        """Test that state is ON when moisture is in water soon zone."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Low threshold is 10%, water soon threshold is 15%
        sensor._current_soil_moisture = 12.0
        sensor._min_soil_moisture = 10.0
        sensor._update_state()

        assert sensor._state is True

    def test_update_state_when_at_low_threshold(self, mock_hass):
        """Test that state is ON when moisture equals low threshold."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Low threshold is 10%
        sensor._current_soil_moisture = 10.0
        sensor._min_soil_moisture = 10.0
        sensor._update_state()

        assert sensor._state is True

    def test_update_state_when_at_water_soon_threshold(self, mock_hass):
        """Test that state is ON when moisture equals water soon threshold."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Low threshold is 10%, water soon threshold is 15%
        sensor._current_soil_moisture = 15.0
        sensor._min_soil_moisture = 10.0
        sensor._update_state()

        assert sensor._state is True

    def test_update_state_when_below_low_threshold(self, mock_hass):
        """Test that state is OFF when moisture is below low threshold."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Low threshold is 10%, moisture is 9%
        sensor._current_soil_moisture = 9.0
        sensor._min_soil_moisture = 10.0
        sensor._update_state()

        assert sensor._state is False

    def test_update_state_when_above_water_soon_threshold(self, mock_hass):
        """Test that state is OFF when moisture is above water soon threshold."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Low threshold is 10%, water soon threshold is 15%, moisture is 16%
        sensor._current_soil_moisture = 16.0
        sensor._min_soil_moisture = 10.0
        sensor._update_state()

        assert sensor._state is False

    def test_update_state_when_moisture_unavailable(self, mock_hass):
        """Test that state is None when moisture is unavailable."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        sensor._current_soil_moisture = None
        sensor._min_soil_moisture = 10.0
        sensor._update_state()

        assert sensor._state is None

    def test_update_state_when_threshold_unavailable(self, mock_hass):
        """Test that state is None when threshold is unavailable."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        sensor._current_soil_moisture = 12.0
        sensor._min_soil_moisture = None
        sensor._update_state()

        assert sensor._state is None

    def test_water_soon_threshold_calculation(self, mock_hass):
        """Test that water soon threshold is calculated as low threshold + 5."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Test various low thresholds
        test_cases = [
            (5.0, 10.0),  # 5% low threshold, 10% water soon
            (10.0, 15.0),  # 10% low threshold, 15% water soon
            (20.0, 25.0),  # 20% low threshold, 25% water soon
            (0.0, 5.0),  # 0% low threshold, 5% water soon
        ]

        for low_threshold, expected_water_soon in test_cases:
            sensor._min_soil_moisture = low_threshold
            sensor._current_soil_moisture = expected_water_soon
            sensor._update_state()
            assert sensor._state is True, f"Failed for low_threshold={low_threshold}"

            # One point above should be OFF
            sensor._current_soil_moisture = expected_water_soon + 1
            sensor._update_state()
            assert sensor._state is False, f"Failed for low_threshold={low_threshold}"


class TestSoilMoistureWaterSoonMonitorBinarySensorProperties:
    """Test binary sensor properties."""

    def test_is_on_returns_state(self, mock_hass):
        """Test is_on property returns current state."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        sensor._state = True
        assert sensor.is_on is True

        sensor._state = False
        assert sensor.is_on is False

        sensor._state = None
        assert sensor.is_on is None

    def test_extra_state_attributes(self, mock_hass):
        """Test that extra state attributes are set correctly."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        sensor._current_soil_moisture = 12.0
        sensor._min_soil_moisture = 10.0

        attrs = sensor.extra_state_attributes

        # Check required attributes
        assert attrs["type"] == "Warning"
        assert attrs["message"] == "Soil Moisture Water Soon"
        assert attrs["task"] is True
        assert attrs["tags"] == ["test_garden", "zone_a"]

        # Check internal attributes
        assert attrs["current_soil_moisture"] == 12.0
        assert attrs["minimum_soil_moisture_threshold"] == 10.0
        assert attrs["water_soon_threshold"] == 15.0
        assert attrs["source_entity"] == "sensor.test_moisture"

    def test_extra_state_attributes_without_threshold(self, mock_hass):
        """Test extra state attributes when threshold is None."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        sensor._current_soil_moisture = 12.0
        sensor._min_soil_moisture = None

        attrs = sensor.extra_state_attributes

        # Water soon threshold should not be present if min threshold is None
        assert "water_soon_threshold" not in attrs

    def test_available_when_entity_exists(self, mock_hass):
        """Test sensor is available when moisture entity exists."""
        mock_state = MagicMock()
        mock_state.state = "50"
        mock_hass.states.get.return_value = mock_state

        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        assert sensor.available is True

    def test_available_when_entity_missing(self, mock_hass):
        """Test sensor is unavailable when moisture entity is missing."""
        mock_hass.states.get.return_value = None

        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        assert sensor.available is False


class TestSoilMoistureWaterSoonMonitorBinarySensorCallbacks:
    """Test state change callbacks."""

    def test_soil_moisture_state_changed_callback(self, mock_hass):
        """Test soil moisture state change callback."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Mock async_write_ha_state to avoid Home Assistant runtime dependencies
        sensor.async_write_ha_state = MagicMock()

        sensor._min_soil_moisture = 10.0

        # Simulate moisture entering water soon zone
        old_state = MagicMock()
        old_state.state = "8"
        new_state = MagicMock()
        new_state.state = "12"

        sensor._soil_moisture_state_changed(
            "sensor.test_moisture",
            old_state,
            new_state,
        )

        assert sensor._current_soil_moisture == 12.0
        assert sensor._state is True
        sensor.async_write_ha_state.assert_called_once()

    def test_min_soil_moisture_state_changed_callback(self, mock_hass):
        """Test minimum soil moisture threshold change callback."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Mock async_write_ha_state to avoid Home Assistant runtime dependencies
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_moisture = 12.0

        # Simulate threshold changing (was 10%, now 8%)
        old_state = MagicMock()
        old_state.state = "10"
        new_state = MagicMock()
        new_state.state = "8"

        sensor._min_soil_moisture_state_changed(
            "sensor.min_soil_moisture",
            old_state,
            new_state,
        )

        assert sensor._min_soil_moisture == 8.0
        # 12 is now between 8 and 13 (8+5), so state should be True
        assert sensor._state is True
        sensor.async_write_ha_state.assert_called_once()

    def test_soil_moisture_state_changed_to_below_threshold(self, mock_hass):
        """Test moisture drops below low threshold (critical)."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        sensor._min_soil_moisture = 10.0

        # Simulate moisture dropping below critical threshold
        old_state = MagicMock()
        old_state.state = "12"
        new_state = MagicMock()
        new_state.state = "8"

        sensor._soil_moisture_state_changed(
            "sensor.test_moisture",
            old_state,
            new_state,
        )

        assert sensor._current_soil_moisture == 8.0
        # 8 is below 10 (low threshold), so state should be False
        assert sensor._state is False
        sensor.async_write_ha_state.assert_called_once()


class TestSoilMoistureWaterSoonMonitorBinarySensorCleanup:
    """Test resource cleanup."""

    async def test_async_will_remove_from_hass(self, mock_hass):
        """Test cleanup when entity is removed."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        # Mock the unsubscribe functions
        mock_unsubscribe = MagicMock()
        mock_unsubscribe_min = MagicMock()

        sensor._unsubscribe = mock_unsubscribe
        sensor._unsubscribe_min = mock_unsubscribe_min

        await sensor.async_will_remove_from_hass()

        # Verify both unsubscribe functions were called
        mock_unsubscribe.assert_called_once()
        mock_unsubscribe_min.assert_called_once()


class TestSoilMoistureWaterSoonMonitorRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_scenario_low_threshold_10_percent(self, mock_hass):
        """Test scenario: low threshold set to 10%."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        sensor._min_soil_moisture = 10.0

        # Test values
        test_cases = [
            (5.0, False, "Below low threshold - not water soon zone"),
            (10.0, True, "At low threshold - water soon zone"),
            (12.5, True, "Middle of water soon zone"),
            (15.0, True, "At water soon threshold"),
            (16.0, False, "Above water soon zone"),
            (50.0, False, "Well above water soon zone"),
        ]

        for moisture_value, expected_state, description in test_cases:
            sensor._current_soil_moisture = moisture_value
            sensor._update_state()
            assert sensor._state == expected_state, f"Failed for {description}"

    def test_scenario_low_threshold_20_percent(self, mock_hass):
        """Test scenario: low threshold set to 20%."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        sensor._min_soil_moisture = 20.0

        # Test values
        test_cases = [
            (15.0, False, "Below low threshold"),
            (20.0, True, "At low threshold"),
            (22.5, True, "Middle of water soon zone"),
            (25.0, True, "At water soon threshold (20+5)"),
            (26.0, False, "Above water soon zone"),
        ]

        for moisture_value, expected_state, description in test_cases:
            sensor._current_soil_moisture = moisture_value
            sensor._update_state()
            assert sensor._state == expected_state, f"Failed for {description}"

    def test_does_not_trigger_when_low_monitor_active(self, mock_hass):
        """Test that water soon does not trigger when low monitor is already active."""
        config = SoilMoistureWaterSoonMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureWaterSoonMonitorBinarySensor(config)

        sensor._min_soil_moisture = 10.0

        # When moisture is below low threshold (low monitor would be active)
        sensor._current_soil_moisture = 8.0
        sensor._update_state()

        # Water soon monitor should be OFF
        assert sensor._state is False
