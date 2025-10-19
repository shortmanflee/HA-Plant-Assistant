"""Unit tests for sensor entities."""

from unittest.mock import Mock

from custom_components.plant_assistant.const import ATTR_PLANT_DEVICE_IDS
from custom_components.plant_assistant.sensor import PlantCountLocationSensor


class TestPlantCountLocationSensor:
    """Test suite for PlantCountLocationSensor."""

    def test_plant_count_sensor_with_no_plants(self):
        """Test sensor returns 0 when no plants are assigned to slots."""
        hass = Mock()
        entry_id = "test_entry"
        location_name = "Test Location"
        location_device_id = "loc_device_123"
        plant_slots = {
            "slot_1": {"name": "Slot 1", "plant_device_id": None},
            "slot_2": {"name": "Slot 2", "plant_device_id": None},
            "slot_3": {"name": "Slot 3", "plant_device_id": None},
        }

        sensor = PlantCountLocationSensor(
            hass=hass,
            entry_id=entry_id,
            location_name=location_name,
            location_device_id=location_device_id,
            plant_slots=plant_slots,
        )

        assert sensor.native_value == 0
        assert sensor.extra_state_attributes[ATTR_PLANT_DEVICE_IDS] == []

    def test_plant_count_sensor_with_some_plants(self):
        """Test sensor counts plants correctly when some slots have plants."""
        hass = Mock()
        entry_id = "test_entry"
        location_name = "Test Location"
        location_device_id = "loc_device_123"
        plant_slots = {
            "slot_1": {"name": "Slot 1", "plant_device_id": "plant_001"},
            "slot_2": {"name": "Slot 2", "plant_device_id": None},
            "slot_3": {"name": "Slot 3", "plant_device_id": "plant_002"},
        }

        sensor = PlantCountLocationSensor(
            hass=hass,
            entry_id=entry_id,
            location_name=location_name,
            location_device_id=location_device_id,
            plant_slots=plant_slots,
        )

        assert sensor.native_value == 2
        assert set(sensor.extra_state_attributes[ATTR_PLANT_DEVICE_IDS]) == {
            "plant_001",
            "plant_002",
        }

    def test_plant_count_sensor_with_all_plants(self):
        """Test sensor when all slots have plants assigned."""
        hass = Mock()
        entry_id = "test_entry"
        location_name = "Test Location"
        location_device_id = "loc_device_123"
        plant_slots = {
            "slot_1": {"name": "Slot 1", "plant_device_id": "plant_001"},
            "slot_2": {"name": "Slot 2", "plant_device_id": "plant_002"},
            "slot_3": {"name": "Slot 3", "plant_device_id": "plant_003"},
        }

        sensor = PlantCountLocationSensor(
            hass=hass,
            entry_id=entry_id,
            location_name=location_name,
            location_device_id=location_device_id,
            plant_slots=plant_slots,
        )

        assert sensor.native_value == 3
        assert set(sensor.extra_state_attributes[ATTR_PLANT_DEVICE_IDS]) == {
            "plant_001",
            "plant_002",
            "plant_003",
        }

    def test_plant_count_sensor_with_empty_slots_dict(self):
        """Test sensor with empty plant slots dictionary."""
        hass = Mock()
        entry_id = "test_entry"
        location_name = "Test Location"
        location_device_id = "loc_device_123"
        plant_slots = {}

        sensor = PlantCountLocationSensor(
            hass=hass,
            entry_id=entry_id,
            location_name=location_name,
            location_device_id=location_device_id,
            plant_slots=plant_slots,
        )

        assert sensor.native_value == 0
        assert sensor.extra_state_attributes[ATTR_PLANT_DEVICE_IDS] == []

    def test_plant_count_sensor_attributes(self):
        """Test that sensor has correct attributes."""
        hass = Mock()
        entry_id = "test_entry"
        location_name = "Test Location"
        location_device_id = "loc_device_123"
        plant_slots = {
            "slot_1": {"name": "Slot 1", "plant_device_id": "plant_001"},
        }

        sensor = PlantCountLocationSensor(
            hass=hass,
            entry_id=entry_id,
            location_name=location_name,
            location_device_id=location_device_id,
            plant_slots=plant_slots,
        )

        # Check sensor name and unit
        assert sensor.name == "Plant Count"
        assert sensor.native_unit_of_measurement == "plants"
        assert sensor.icon == "mdi:flower-tulip"

        # Check attributes
        attrs = sensor.extra_state_attributes
        assert "location_device_id" in attrs
        assert attrs["location_device_id"] == location_device_id
        assert ATTR_PLANT_DEVICE_IDS in attrs

    def test_plant_count_sensor_device_info(self):
        """Test that sensor has correct device info."""
        hass = Mock()
        entry_id = "test_entry"
        location_name = "Test Location"
        location_device_id = "loc_device_123"
        plant_slots = {}

        sensor = PlantCountLocationSensor(
            hass=hass,
            entry_id=entry_id,
            location_name=location_name,
            location_device_id=location_device_id,
            plant_slots=plant_slots,
        )

        device_info = sensor.device_info
        assert device_info is not None
        assert device_info.get("identifiers") == {
            ("plant_assistant", location_device_id)
        }
        assert device_info.get("name") == location_name
        assert device_info.get("manufacturer") == "Plant Assistant"
        assert device_info.get("model") == "Plant Location Device"

    def test_plant_count_sensor_with_malformed_slots(self):
        """Test sensor handles malformed slot data gracefully."""
        hass = Mock()
        entry_id = "test_entry"
        location_name = "Test Location"
        location_device_id = "loc_device_123"
        plant_slots = {
            "slot_1": {"name": "Slot 1", "plant_device_id": "plant_001"},
            "slot_2": "not_a_dict",  # Invalid slot format
            "slot_3": None,  # Null slot
            "slot_4": {"name": "Slot 4"},  # Missing plant_device_id
        }

        sensor = PlantCountLocationSensor(
            hass=hass,
            entry_id=entry_id,
            location_name=location_name,
            location_device_id=location_device_id,
            plant_slots=plant_slots,
        )

        # Should only count the valid slot with a plant_device_id
        assert sensor.native_value == 1
        assert sensor.extra_state_attributes[ATTR_PLANT_DEVICE_IDS] == ["plant_001"]

    def test_plant_count_sensor_unique_id(self):
        """Test that sensor has a unique ID based on entry ID."""
        hass = Mock()
        entry_id = "my_unique_entry"
        location_name = "Test Location"
        location_device_id = "loc_device_123"
        plant_slots = {}

        sensor = PlantCountLocationSensor(
            hass=hass,
            entry_id=entry_id,
            location_name=location_name,
            location_device_id=location_device_id,
            plant_slots=plant_slots,
        )

        assert sensor.unique_id == "plant_assistant_my_unique_entry_plant_count"
