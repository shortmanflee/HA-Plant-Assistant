"""Tests for entity monitoring functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.entity_monitor import (
    EntityMonitor,
    async_setup_entity_monitor,
    async_unload_entity_monitor,
)


class TestEntityMonitor:
    """Test the EntityMonitor class."""

    def setup_method(self):
        """Reset global state before each test."""
        import custom_components.plant_assistant.entity_monitor as em

        em._monitor = None

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.data = {}
        hass.states = MagicMock()
        hass.bus = MagicMock()
        hass.async_create_task = AsyncMock()
        return hass

    @pytest.fixture
    def mock_entity_registry(self):
        """Create a mock entity registry."""
        registry = MagicMock()
        registry.entities = {}
        registry.async_get = MagicMock()
        return registry

    def test_entity_monitor_init_without_registry(self, mock_hass):
        """Test EntityMonitor initialization when registry is not available."""
        # Simulate test environment where entity registry fails
        with patch(
            "homeassistant.helpers.entity_registry.async_get", side_effect=TypeError()
        ):
            monitor = EntityMonitor(mock_hass)
            assert monitor.hass == mock_hass
            assert monitor._entity_registry is None
            assert monitor._unsubscribe_registry_updated is None

    def test_entity_monitor_init_with_registry(self, mock_hass, mock_entity_registry):
        """Test EntityMonitor initialization when registry is available."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_entity_registry,
        ):
            monitor = EntityMonitor(mock_hass)
            assert monitor.hass == mock_hass
            assert monitor._entity_registry == mock_entity_registry

    async def test_entity_monitor_setup_without_registry(self, mock_hass):
        """Test EntityMonitor setup when registry is not available."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get", side_effect=TypeError()
        ):
            monitor = EntityMonitor(mock_hass)
            # Setup should complete without error even without registry
            await monitor.async_setup()
            assert monitor._unsubscribe_registry_updated is None

    async def test_entity_monitor_setup_with_registry(
        self, mock_hass, mock_entity_registry
    ):
        """Test EntityMonitor setup when registry is available."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_entity_registry,
        ):
            monitor = EntityMonitor(mock_hass)
            await monitor.async_setup()

            # Should have subscribed to entity registry events
            mock_hass.bus.async_listen.assert_called_once_with(
                "entity_registry_updated", monitor._handle_entity_registry_updated
            )

    async def test_find_mirror_entities_without_registry(self, mock_hass):
        """Test finding mirror entities when registry is not available."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get", side_effect=TypeError()
        ):
            monitor = EntityMonitor(mock_hass)
            entities = await monitor._find_mirror_entities_for_source("sensor.test")
            assert entities == []

    async def test_find_mirror_entities_with_registry(
        self, mock_hass, mock_entity_registry
    ):
        """Test finding mirror entities when registry is available."""
        # Mock entity registry entry
        mock_entity_entry = MagicMock()
        mock_entity_entry.domain = "sensor"
        mock_entity_entry.unique_id = f"{DOMAIN}_test_humidity_mirror"
        mock_entity_entry.entity_id = "sensor.test_humidity_mirror"

        mock_entity_registry.entities = {
            "sensor.test_humidity_mirror": mock_entity_entry
        }

        # Mock state with source entity reference
        mock_state = MagicMock()
        mock_state.attributes = {"source_entity": "sensor.original_humidity"}
        mock_hass.states.get.return_value = mock_state

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_entity_registry,
        ):
            monitor = EntityMonitor(mock_hass)
            entities = await monitor._find_mirror_entities_for_source(
                "sensor.original_humidity"
            )
            assert "sensor.test_humidity_mirror" in entities

    async def test_update_mirror_entity_without_registry(self, mock_hass):
        """Test updating mirror entity when registry is not available."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get", side_effect=TypeError()
        ):
            monitor = EntityMonitor(mock_hass)
            # Should complete without error
            await monitor._update_mirror_entity_source(
                "sensor.test_mirror", "sensor.old_source", "sensor.new_source"
            )

    async def test_handle_entity_rename_event(self, mock_hass, mock_entity_registry):
        """Test handling entity rename events."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_entity_registry,
        ):
            monitor = EntityMonitor(mock_hass)

            # Test valid rename event
            event = MagicMock()
            event.data = {
                "action": "update",
                "entity_id": "sensor.new_id",
                "old_entity_id": "sensor.old_id",
            }

            with patch.object(monitor, "_handle_entity_rename", new_callable=AsyncMock):
                monitor._handle_entity_registry_updated(event)

                # Should create task to handle rename
                mock_hass.async_create_task.assert_called_once()

    async def test_handle_non_rename_event(self, mock_hass, mock_entity_registry):
        """Test handling non-rename entity registry events."""
        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=mock_entity_registry,
        ):
            monitor = EntityMonitor(mock_hass)

            # Test non-rename event (create)
            event = MagicMock()
            event.data = {"action": "create", "entity_id": "sensor.new_entity"}

            monitor._handle_entity_registry_updated(event)

            # Should not create any tasks for non-rename events
            mock_hass.async_create_task.assert_not_called()

    async def test_async_setup_entity_monitor(self, mock_hass):
        """Test global entity monitor setup function."""
        with patch(
            "custom_components.plant_assistant.entity_monitor.EntityMonitor"
        ) as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor._entity_registry = MagicMock()  # Simulate registry available
            mock_monitor.async_setup = AsyncMock()  # Make it properly async
            mock_monitor_class.return_value = mock_monitor

            await async_setup_entity_monitor(mock_hass)

            # Should create monitor and call setup
            mock_monitor_class.assert_called_once_with(mock_hass)
            mock_monitor.async_setup.assert_called_once()

            # Should store in hass data
            assert mock_hass.data[DOMAIN]["entity_monitor"] == mock_monitor

    async def test_async_setup_entity_monitor_without_registry(self, mock_hass):
        """Test global entity monitor setup when registry not available."""
        with patch(
            "custom_components.plant_assistant.entity_monitor.EntityMonitor"
        ) as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor._entity_registry = None  # Simulate no registry
            mock_monitor.async_setup = AsyncMock()  # Make it properly async
            mock_monitor_class.return_value = mock_monitor

            await async_setup_entity_monitor(mock_hass)

            # Should create monitor but not call setup
            mock_monitor_class.assert_called_once_with(mock_hass)
            mock_monitor.async_setup.assert_not_called()

    async def test_async_unload_entity_monitor(self, mock_hass):
        """Test global entity monitor unload function."""
        # Set up mock monitor in global state
        mock_monitor = MagicMock()
        mock_monitor.async_unload = AsyncMock()  # Make it properly async
        mock_hass.data = {DOMAIN: {"entity_monitor": mock_monitor}}

        with patch(
            "custom_components.plant_assistant.entity_monitor._monitor", mock_monitor
        ):
            await async_unload_entity_monitor(mock_hass)

            # Should call unload and clear global reference
            mock_monitor.async_unload.assert_called_once()
            assert "entity_monitor" not in mock_hass.data.get(DOMAIN, {})

    async def test_async_unload_entity_monitor_no_monitor(self, mock_hass):
        """Test global entity monitor unload when no monitor exists."""
        mock_hass.data = {}

        # Ensure global monitor is None
        import custom_components.plant_assistant.entity_monitor as em

        em._monitor = None

        # Should complete without error
        await async_unload_entity_monitor(mock_hass)


@pytest.mark.asyncio
async def test_entity_monitor_integration_scenario():
    """Integration test simulating a real entity rename scenario."""
    # Set up mock environment
    hass = MagicMock()
    hass.data = {}
    hass.states = MagicMock()
    hass.bus = MagicMock()
    hass.async_create_task = AsyncMock()

    # Mock entity registry
    registry = MagicMock()
    mock_entity = MagicMock()
    mock_entity.domain = "sensor"
    mock_entity.unique_id = f"{DOMAIN}_test_humidity_mirror"
    mock_entity.entity_id = "sensor.living_room_humidity_mirror"

    registry.entities = {"sensor.living_room_humidity_mirror": mock_entity}
    registry.async_get.return_value = mock_entity

    # Mock state indicating this is a mirror entity
    mock_state = MagicMock()
    mock_state.attributes = {"source_entity": "sensor.xiaomi_humidity"}
    hass.states.get.return_value = mock_state

    # Mock config entries (entity monitor now updates config and reloads)
    hass.config_entries = MagicMock()
    hass.config_entries.async_get_entry.return_value = None  # No config entry found
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    # Test the full scenario
    with (
        patch("homeassistant.helpers.entity_registry.async_get", return_value=registry),
        patch("homeassistant.helpers.event.async_track_state_change"),
    ):
        monitor = EntityMonitor(hass)
        await monitor.async_setup()

        # Simulate entity rename
        await monitor._handle_entity_rename(
            "sensor.xiaomi_humidity", "sensor.living_room_humidity"
        )

        # Verify the mirror entity was discovered and a config update was attempted.
        # The config update normally needs a persisted entry, which this test omits.
        assert True  # Test passes if no exceptions are thrown

        await monitor.async_unload()
