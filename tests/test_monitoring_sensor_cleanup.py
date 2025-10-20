"""Tests for monitoring sensor cleanup functionality."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.sensor import (
    _cleanup_orphaned_monitoring_sensors,
)


@pytest.mark.asyncio
async def test_cleanup_orphaned_monitoring_sensors_removes_disassociated_sensors():
    """Test that orphaned monitoring sensors are removed when device disassociates."""
    # Create mock hass
    mock_hass = MagicMock()

    # Create mock entity registry with orphaned monitoring sensors
    mock_entity_registry = MagicMock()

    # Create orphaned sensor entities (from a device that's no longer associated)
    orphaned_entity_1 = MagicMock()
    orphaned_entity_1.platform = DOMAIN
    orphaned_entity_1.domain = "sensor"
    orphaned_entity_1.unique_id = (
        f"{DOMAIN}_old_subentry_test_location_illuminance_mirror"
    )
    orphaned_entity_1.config_entry_id = "main_entry_123"

    orphaned_entity_2 = MagicMock()
    orphaned_entity_2.platform = DOMAIN
    orphaned_entity_2.domain = "sensor"
    orphaned_entity_2.unique_id = (
        f"{DOMAIN}_old_subentry_test_location_soil_conductivity_mirror"
    )
    orphaned_entity_2.config_entry_id = "main_entry_123"

    # Non-mirrored entity (should not be removed)
    non_mirror_entity = MagicMock()
    non_mirror_entity.platform = DOMAIN
    non_mirror_entity.domain = "sensor"
    non_mirror_entity.unique_id = f"{DOMAIN}_old_subentry_plant_count"
    non_mirror_entity.config_entry_id = "main_entry_123"

    # Entity from different entry (should not be removed)
    other_entry_entity = MagicMock()
    other_entry_entity.platform = DOMAIN
    other_entry_entity.domain = "sensor"
    other_entry_entity.unique_id = f"{DOMAIN}_other_entry_illuminance_mirror"
    other_entry_entity.config_entry_id = "other_entry_456"

    mock_entity_registry.entities = {
        "sensor.orphaned_1": orphaned_entity_1,
        "sensor.orphaned_2": orphaned_entity_2,
        "sensor.non_mirror": non_mirror_entity,
        "sensor.other_entry": other_entry_entity,
    }

    mock_entity_registry.async_remove = MagicMock()

    # Mock er.async_get to return our mock registry
    with patch(
        "custom_components.plant_assistant.sensor.er.async_get",
        return_value=mock_entity_registry,
    ):
        # Create mock entry with no subentries (all devices disassociated)
        mock_entry = MagicMock()
        mock_entry.entry_id = "main_entry_123"
        mock_entry.subentries = {}

        # Run cleanup
        await _cleanup_orphaned_monitoring_sensors(mock_hass, mock_entry)

        # Verify orphaned sensors were removed
        assert mock_entity_registry.async_remove.call_count == 2
        mock_entity_registry.async_remove.assert_any_call("sensor.orphaned_1")
        mock_entity_registry.async_remove.assert_any_call("sensor.orphaned_2")


@pytest.mark.asyncio
async def test_cleanup_orphaned_monitoring_sensors_preserves_current_sensors():
    """Test that monitoring sensors for currently associated devices are preserved."""
    # Create mock hass
    mock_hass = MagicMock()

    # Mock device and entity registries
    mock_device_registry = MagicMock()
    mock_entity_registry = MagicMock()

    # Create monitoring device
    monitoring_device = MagicMock()
    monitoring_device.id = "device_123"
    mock_device_registry.async_get = MagicMock(return_value=monitoring_device)

    # Create sensor entity on monitoring device
    source_sensor = MagicMock()
    source_sensor.device_id = "device_123"
    source_sensor.domain = "sensor"
    source_sensor.entity_id = "sensor.monitoring_device_illuminance"
    source_sensor.device_class = "illuminance"

    # Create expected mirror sensor
    expected_mirror_entity = MagicMock()
    expected_mirror_entity.platform = DOMAIN
    expected_mirror_entity.domain = "sensor"
    expected_mirror_entity.unique_id = (
        f"{DOMAIN}_subentry_123_test_location_illuminance_mirror"
    )
    expected_mirror_entity.config_entry_id = "main_entry_123"

    # Create orphaned mirror sensor (from another location/device that was removed)
    orphaned_mirror_entity = MagicMock()
    orphaned_mirror_entity.platform = DOMAIN
    orphaned_mirror_entity.domain = "sensor"
    orphaned_mirror_entity.unique_id = (
        f"{DOMAIN}_subentry_456_old_location_illuminance_mirror"
    )
    orphaned_mirror_entity.config_entry_id = "main_entry_123"

    mock_entity_registry.entities = {
        "sensor.monitoring_illuminance": source_sensor,
        "sensor.expected_mirror": expected_mirror_entity,
        "sensor.orphaned_mirror": orphaned_mirror_entity,
    }

    mock_entity_registry.async_remove = MagicMock()

    # Mock _get_monitoring_device_sensors to return the illuminance sensor
    mock_get_sensors = {
        "illuminance": "sensor.monitoring_device_illuminance",
    }

    # Mock helper functions
    with (
        patch(
            "custom_components.plant_assistant.sensor.er.async_get",
            return_value=mock_entity_registry,
        ),
        patch(
            "custom_components.plant_assistant.sensor.dr.async_get",
            return_value=mock_device_registry,
        ),
        patch(
            "custom_components.plant_assistant.sensor._get_monitoring_device_sensors",
            return_value=mock_get_sensors,
        ),
        patch(
            "custom_components.plant_assistant.sensor._detect_sensor_type_from_entity",
            return_value="illuminance",
        ),
    ):
        # Create mock entry with one subentry that has monitoring device
        mock_subentry = MagicMock()
        mock_subentry.subentry_id = "subentry_123"
        mock_subentry.data = {
            "device_id": "location_device_123",
            "monitoring_device_id": "device_123",
            "name": "Test Location",
        }

        mock_entry = MagicMock()
        mock_entry.entry_id = "main_entry_123"
        mock_entry.subentries = {"subentry_123": mock_subentry}

        # Run cleanup
        await _cleanup_orphaned_monitoring_sensors(mock_hass, mock_entry)

        # Verify only orphaned sensor was removed, not the expected one
        mock_entity_registry.async_remove.assert_called_once_with(
            "sensor.orphaned_mirror"
        )


@pytest.mark.asyncio
async def test_cleanup_orphaned_monitoring_sensors_with_no_subentries():
    """Test cleanup gracefully handles entry with no subentries."""
    # Create mock hass
    mock_hass = MagicMock()

    # Create mock entity registry
    mock_entity_registry = MagicMock()
    mock_entity_registry.entities = {}
    mock_entity_registry.async_remove = MagicMock()

    with patch(
        "custom_components.plant_assistant.sensor.er.async_get",
        return_value=mock_entity_registry,
    ):
        # Create mock entry with no subentries
        mock_entry = MagicMock()
        mock_entry.entry_id = "main_entry_123"
        mock_entry.subentries = {}

        # Run cleanup - should not raise any errors
        await _cleanup_orphaned_monitoring_sensors(mock_hass, mock_entry)

        # Verify no entities were removed
        mock_entity_registry.async_remove.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_orphaned_monitoring_sensors_ignores_other_domains():
    """Test cleanup doesn't remove sensors from other domains."""
    # Create mock hass
    mock_hass = MagicMock()

    # Create mock entity registry with sensors from other domains
    mock_entity_registry = MagicMock()

    # Entity from different domain
    other_domain_entity = MagicMock()
    other_domain_entity.platform = "other_integration"
    other_domain_entity.domain = "sensor"
    other_domain_entity.unique_id = "other_illuminance_mirror"
    other_domain_entity.config_entry_id = "main_entry_123"

    # Entity from different platform
    different_platform_entity = MagicMock()
    different_platform_entity.platform = "some_other_platform"
    different_platform_entity.domain = "sensor"
    different_platform_entity.unique_id = f"{DOMAIN}_subentry_123_illuminance_mirror"
    different_platform_entity.config_entry_id = "main_entry_123"

    mock_entity_registry.entities = {
        "sensor.other_domain": other_domain_entity,
        "sensor.different_platform": different_platform_entity,
    }

    mock_entity_registry.async_remove = MagicMock()

    with patch(
        "custom_components.plant_assistant.sensor.er.async_get",
        return_value=mock_entity_registry,
    ):
        # Create mock entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "main_entry_123"
        mock_entry.subentries = {}

        # Run cleanup
        await _cleanup_orphaned_monitoring_sensors(mock_hass, mock_entry)

        # Verify no entities from other domains/platforms were removed
        mock_entity_registry.async_remove.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_orphaned_monitoring_sensors_handles_exceptions():
    """Test cleanup handles exceptions gracefully."""
    # Create mock hass
    mock_hass = MagicMock()

    # Create mock entity registry that raises exception
    mock_entity_registry = MagicMock()
    mock_entity_registry.entities = {}

    with patch(
        "custom_components.plant_assistant.sensor.er.async_get",
        side_effect=AttributeError("Registry not available"),
    ):
        # Create mock entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "main_entry_123"
        mock_entry.subentries = {}

        # Run cleanup - should not raise any errors
        await _cleanup_orphaned_monitoring_sensors(mock_hass, mock_entry)

        # No exceptions should have been raised


@pytest.mark.asyncio
async def test_cleanup_orphaned_monitoring_sensors_removes_battery_sensors():
    """Test that orphaned battery sensors are removed with correct suffix."""
    # Create mock hass
    mock_hass = MagicMock()

    # Create mock entity registry with orphaned battery sensor
    mock_entity_registry = MagicMock()

    # Create orphaned battery sensor (uses battery_level suffix, not battery_mirror)
    orphaned_battery_entity = MagicMock()
    orphaned_battery_entity.platform = DOMAIN
    orphaned_battery_entity.domain = "sensor"
    orphaned_battery_entity.unique_id = (
        f"{DOMAIN}_old_subentry_test_location_battery_level"
    )
    orphaned_battery_entity.config_entry_id = "main_entry_123"

    mock_entity_registry.entities = {
        "sensor.orphaned_battery": orphaned_battery_entity,
    }

    mock_entity_registry.async_remove = MagicMock()

    # Mock er.async_get to return our mock registry
    with patch(
        "custom_components.plant_assistant.sensor.er.async_get",
        return_value=mock_entity_registry,
    ):
        # Create mock entry with no subentries (all devices disassociated)
        mock_entry = MagicMock()
        mock_entry.entry_id = "main_entry_123"
        mock_entry.subentries = {}

        # Run cleanup
        await _cleanup_orphaned_monitoring_sensors(mock_hass, mock_entry)

        # Verify orphaned battery sensor was removed
        mock_entity_registry.async_remove.assert_called_once_with(
            "sensor.orphaned_battery"
        )


@pytest.mark.asyncio
async def test_cleanup_orphaned_monitoring_sensors_removes_signal_strength_sensors():
    """Test that orphaned signal strength sensors are removed with correct suffix."""
    # Create mock hass
    mock_hass = MagicMock()

    # Create mock entity registry with orphaned signal strength sensor
    mock_entity_registry = MagicMock()

    # Create orphaned signal strength sensor (uses signal_strength suffix)
    orphaned_signal_entity = MagicMock()
    orphaned_signal_entity.platform = DOMAIN
    orphaned_signal_entity.domain = "sensor"
    orphaned_signal_entity.unique_id = (
        f"{DOMAIN}_old_subentry_test_location_signal_strength"
    )
    orphaned_signal_entity.config_entry_id = "main_entry_123"

    mock_entity_registry.entities = {
        "sensor.orphaned_signal": orphaned_signal_entity,
    }

    mock_entity_registry.async_remove = MagicMock()

    # Mock er.async_get to return our mock registry
    with patch(
        "custom_components.plant_assistant.sensor.er.async_get",
        return_value=mock_entity_registry,
    ):
        # Create mock entry with no subentries (all devices disassociated)
        mock_entry = MagicMock()
        mock_entry.entry_id = "main_entry_123"
        mock_entry.subentries = {}

        # Run cleanup
        await _cleanup_orphaned_monitoring_sensors(mock_hass, mock_entry)

        # Verify orphaned signal strength sensor was removed
        mock_entity_registry.async_remove.assert_called_once_with(
            "sensor.orphaned_signal"
        )
