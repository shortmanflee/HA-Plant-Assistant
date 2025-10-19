"""Test for slot management in config flow - specifically slot removal functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.plant_assistant.config_flow import LocationSubentryFlowHandler


@pytest.mark.asyncio
async def test_slot_removal_preserves_empty_slots():
    """
    Test that removing a plant from a slot preserves the slot as empty.

    This test ensures that when a user clears a plant from a slot (by selecting
    empty in the UI), the slot is preserved in the data structure with
    plant_device_id = None, rather than being removed entirely.
    """
    # Create mock hass
    hass = Mock()
    hass.config_entries = Mock()

    # Create mock device registry with test plant devices
    device_registry = Mock()
    device_registry.devices = {
        "plant_123": Mock(
            id="plant_123",
            name="Test Plant 1",
            name_by_user=None,
            identifiers=[("openplantbook_ref", "123")],
        ),
        "plant_456": Mock(
            id="plant_456",
            name="Test Plant 2",
            name_by_user=None,
            identifiers=[("openplantbook_ref", "456")],
        ),
        "plant_789": Mock(
            id="plant_789",
            name="Test Plant 3",
            name_by_user=None,
            identifiers=[("openplantbook_ref", "789")],
        ),
    }
    device_registry.async_get = Mock(
        side_effect=lambda device_id: device_registry.devices.get(device_id)
    )

    with patch(
        "homeassistant.helpers.device_registry.async_get", return_value=device_registry
    ):
        # Create mock parent entry
        parent_entry = Mock()
        parent_entry.entry_id = "test_entry"

        # Create mock subentry with some existing slots
        subentry = Mock()
        subentry.entry_id = "test_subentry"
        subentry.data = {
            "name": "Test Location",
            "plant_slots": {
                "slot_1": {"name": "Slot 1", "plant_device_id": "plant_123"},
                "slot_2": {"name": "Slot 2", "plant_device_id": "plant_456"},
                "slot_3": {"name": "Slot 3", "plant_device_id": "plant_789"},
            },
        }

        # Create flow handler
        flow_handler = LocationSubentryFlowHandler()
        flow_handler.hass = hass

        # Mock the internal methods
        flow_handler._get_entry = Mock(return_value=parent_entry)
        flow_handler._get_reconfigure_subentry = Mock(return_value=subentry)
        flow_handler.async_update_and_abort = AsyncMock()
        flow_handler.async_show_form = AsyncMock()

        # Simulate user input where slot_2 is cleared (empty string)
        user_input = {
            "slot_1": "plant_123",  # Keep existing
            "slot_2": "",  # Remove plant (empty string)
            "slot_3": "plant_789",  # Keep existing
            # slots 4-10 are not provided (None values by default)
        }

        # Call the method
        await flow_handler.async_step_add_slot(user_input)

        # Verify async_update_and_abort was called
        flow_handler.async_update_and_abort.assert_called_once()

        # Get the call arguments
        call_args = flow_handler.async_update_and_abort.call_args
        data_updates = call_args[1]["data_updates"]

        # Verify the updated data
        updated_slots = data_updates["plant_slots"]

        # Verify slot_1 and slot_3 are preserved
        assert "slot_1" in updated_slots
        assert updated_slots["slot_1"]["plant_device_id"] == "plant_123"

        assert "slot_3" in updated_slots
        assert updated_slots["slot_3"]["plant_device_id"] == "plant_789"

        # Verify slot_2 is preserved but empty (this is the key fix)
        assert "slot_2" in updated_slots
        assert updated_slots["slot_2"]["plant_device_id"] is None

        # With the new approach, all 10 slots should always exist
        for i in range(1, 11):
            assert f"slot_{i}" in updated_slots

        # Verify empty slots have None as plant_device_id
        for i in range(4, 11):
            assert updated_slots[f"slot_{i}"]["plant_device_id"] is None


@pytest.mark.asyncio
async def test_slot_addition_creates_new_slot():
    """Test that adding a plant to a previously empty location creates the slot."""
    # Create mock hass
    hass = Mock()
    hass.config_entries = Mock()

    # Create mock device registry
    device_registry = Mock()
    device_registry.devices = {
        "plant_123": Mock(
            id="plant_123",
            name="Test Plant 1",
            name_by_user=None,
            identifiers=[("openplantbook_ref", "123")],
        ),
    }
    device_registry.async_get = Mock(
        side_effect=lambda device_id: device_registry.devices.get(device_id)
    )

    with patch(
        "homeassistant.helpers.device_registry.async_get", return_value=device_registry
    ):
        # Create mock parent entry
        parent_entry = Mock()
        parent_entry.entry_id = "test_entry"

        # Create mock subentry with no existing slots
        subentry = Mock()
        subentry.entry_id = "test_subentry"
        subentry.data = {"name": "Test Location", "plant_slots": {}}

        # Create flow handler
        flow_handler = LocationSubentryFlowHandler()
        flow_handler.hass = hass

        # Mock the internal methods
        flow_handler._get_entry = Mock(return_value=parent_entry)
        flow_handler._get_reconfigure_subentry = Mock(return_value=subentry)
        flow_handler.async_update_and_abort = AsyncMock()
        flow_handler.async_show_form = AsyncMock()

        # Simulate user input where slot_1 gets a new plant
        user_input = {
            "slot_1": "plant_123",  # Add new plant
            # All other slots empty
        }

        # Call the method
        await flow_handler.async_step_add_slot(user_input)

        # Verify async_update_and_abort was called
        flow_handler.async_update_and_abort.assert_called_once()

        # Get the call arguments
        call_args = flow_handler.async_update_and_abort.call_args
        data_updates = call_args[1]["data_updates"]

        # Verify the updated data
        updated_slots = data_updates["plant_slots"]

        # With the new approach, all 10 slots should always exist
        assert len(updated_slots) == 10
        assert "slot_1" in updated_slots
        assert updated_slots["slot_1"]["plant_device_id"] == "plant_123"

        # Verify all other slots exist but are empty
        for i in range(2, 11):
            assert f"slot_{i}" in updated_slots
            assert updated_slots[f"slot_{i}"]["plant_device_id"] is None


@pytest.mark.asyncio
async def test_slot_clearing_by_device_selector():
    """Test that clearing a device selector properly clears the slot."""
    # Create mock hass
    hass = Mock()
    hass.config_entries = Mock()

    # Create mock device registry
    device_registry = Mock()
    device_registry.devices = {
        "plant_123": Mock(
            id="plant_123",
            name="Test Plant 1",
            name_by_user=None,
            identifiers=[("openplantbook_ref", "123")],
        ),
        "plant_456": Mock(
            id="plant_456",
            name="Test Plant 2",
            name_by_user=None,
            identifiers=[("openplantbook_ref", "456")],
        ),
    }
    device_registry.async_get = Mock(
        side_effect=lambda device_id: device_registry.devices.get(device_id)
    )

    with patch(
        "homeassistant.helpers.device_registry.async_get", return_value=device_registry
    ):
        # Create mock parent entry
        parent_entry = Mock()
        parent_entry.entry_id = "test_entry"

        # Create mock subentry with some existing slots.
        # Start with 10 slots as per the new approach.
        subentry = Mock()
        subentry.entry_id = "test_subentry"
        subentry.data = {
            "name": "Test Location",
            "plant_slots": {
                f"slot_{i}": {
                    "name": f"Slot {i}",
                    "plant_device_id": "plant_123"
                    if i == 1
                    else ("plant_456" if i == 2 else None),
                }
                for i in range(1, 11)
            },
        }

        # Create flow handler
        flow_handler = LocationSubentryFlowHandler()
        flow_handler.hass = hass

        # Mock the internal methods
        flow_handler._get_entry = Mock(return_value=parent_entry)
        flow_handler._get_reconfigure_subentry = Mock(return_value=subentry)
        flow_handler.async_update_and_abort = AsyncMock()
        flow_handler.async_show_form = AsyncMock()

        # Simulate user input where slot_2 is cleared to emulate a removed device.
        user_input = {
            "slot_1": "plant_123",  # Keep existing
            # slot_2 is missing from input - simulates user clearing the device selector
            # Other slots not specified (None by default)
        }

        # Call the method
        await flow_handler.async_step_add_slot(user_input)

        # Verify async_update_and_abort was called
        flow_handler.async_update_and_abort.assert_called_once()

        # Get the call arguments
        call_args = flow_handler.async_update_and_abort.call_args
        data_updates = call_args[1]["data_updates"]

        # Verify the updated data
        updated_slots = data_updates["plant_slots"]

        # With new approach, all 10 slots should always exist
        assert len(updated_slots) == 10

        # Verify slot_1 is preserved
        assert "slot_1" in updated_slots
        assert updated_slots["slot_1"]["plant_device_id"] == "plant_123"

        # Verify slot_2 is cleared (this is the key test)
        assert "slot_2" in updated_slots
        assert updated_slots["slot_2"]["plant_device_id"] is None

        # Verify all other slots exist and are empty
        for i in range(3, 11):
            assert f"slot_{i}" in updated_slots
            assert updated_slots[f"slot_{i}"]["plant_device_id"] is None
