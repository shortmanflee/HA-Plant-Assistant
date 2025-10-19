"""Config flow for Plant Assistant integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import slugify

from .const import (
    ACTION_ADD_SLOT,
    CONF_ACTION,
    CONF_HUMIDITY_ENTITY_ID,
    CONF_LINKED_DEVICE_ID,
    CONF_MONITORING_DEVICE_ID,
    DOMAIN,
    OPENPLANTBOOK_DOMAIN,
    STEP_DEVICE_SELECTION,
    STEP_MANUAL_NAME,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# Global locks for options flow to prevent race conditions
_LOCKS: dict[str, asyncio.Lock] = {}

_LOGGER = logging.getLogger(__name__)


def _get_lock(entry_id: str) -> asyncio.Lock:
    """Get or create a lock for the given entry ID."""
    if entry_id not in _LOCKS:
        _LOCKS[entry_id] = asyncio.Lock()
    return _LOCKS[entry_id]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg,misc]
    """Handle a config flow for Plant Assistant."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._instance_name: str | None = None
        self._selected_device_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step - device selection."""
        return await self.async_step_device_selection(user_input)

    async def async_step_device_selection(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle device selection step."""
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_DEVICE_SELECTION,
                data_schema=vol.Schema(
                    {
                        vol.Optional(CONF_LINKED_DEVICE_ID): DeviceSelector(
                            DeviceSelectorConfig(integration="esphome")
                        ),
                    }
                ),
            )

        linked_device_id = user_input.get(CONF_LINKED_DEVICE_ID)

        if linked_device_id:
            # Device was selected, validate it and use its name
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get(linked_device_id)
            if not device:
                return self.async_show_form(
                    step_id=STEP_DEVICE_SELECTION,
                    data_schema=vol.Schema(
                        {
                            vol.Optional(CONF_LINKED_DEVICE_ID): DeviceSelector(
                                DeviceSelectorConfig(integration="esphome")
                            ),
                        }
                    ),
                    errors={CONF_LINKED_DEVICE_ID: "device_not_found"},
                )

            # Check if device is already in use
            used_devices = self._get_all_used_devices()
            if linked_device_id in used_devices:
                return self.async_show_form(
                    step_id=STEP_DEVICE_SELECTION,
                    data_schema=vol.Schema(
                        {
                            vol.Optional(CONF_LINKED_DEVICE_ID): DeviceSelector(
                                DeviceSelectorConfig(integration="esphome")
                            ),
                        }
                    ),
                    errors={CONF_LINKED_DEVICE_ID: "device_already_used"},
                )

            # Use device name as instance name
            self._instance_name = (
                device.name_by_user or device.name or "Plant Assistant"
            )
            self._selected_device_id = linked_device_id

            # Create unique ID and finalize setup
            return await self._finalize_setup()
        # No device selected, proceed to manual name entry
        return await self.async_step_manual_name()

    async def async_step_manual_name(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle manual name entry when no device is selected."""
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_MANUAL_NAME,
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_NAME): str,
                    }
                ),
            )

        # Validate the instance name
        title = user_input.get(CONF_NAME, "").strip()
        if not title:
            return self.async_show_form(
                step_id=STEP_MANUAL_NAME,
                data_schema=vol.Schema({vol.Required(CONF_NAME): str}),
                errors={"name": "Name cannot be empty"},
            )

        self._instance_name = title
        self._selected_device_id = None

        # Create unique ID and finalize setup
        return await self._finalize_setup()

    async def _finalize_setup(self) -> config_entries.ConfigFlowResult:
        """Finalize the setup by creating the config entry."""
        if not self._instance_name:
            msg = "Instance name must be set before finalizing setup"
            raise ValueError(msg)

        # Create a unique ID based on the instance name
        instance_name_clean = (
            self._instance_name.lower().replace(" ", "_").replace("-", "_")
        )
        unique_id = f"{DOMAIN}_{instance_name_clean}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # If no device was selected, we'll create a new device with the instance name
        zone_name = self._instance_name
        linked_device_id = self._selected_device_id

        # Create initial options with the zone
        initial_options = {
            "version": STORAGE_VERSION,
            "irrigation_zones": {
                "zone-1": {
                    "id": "zone-1",
                    "name": zone_name,
                    "linked_device_id": linked_device_id,
                    "locations": {},
                }
            },
        }

        # Store the data for device association if needed
        data = {"linked_device_id": linked_device_id} if linked_device_id else {}

        return self.async_create_entry(
            title=self._instance_name,
            data=data,
            options=initial_options,
        )

    def _get_all_used_devices(self) -> set[str]:
        """Get all devices currently in use across all Plant Assistant instances."""
        used_devices = set()

        # Check all Plant Assistant config entries
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            # Add devices from config entry data (main zone device)
            if entry.data and entry.data.get(CONF_LINKED_DEVICE_ID):
                used_devices.add(entry.data[CONF_LINKED_DEVICE_ID])

            # Add devices from options (zones, locations, slots)
            if entry.options and "irrigation_zones" in entry.options:
                zones = entry.options["irrigation_zones"]
                for zone_data in zones.values():
                    # Zone-linked devices
                    if zone_data.get(CONF_LINKED_DEVICE_ID):
                        used_devices.add(zone_data[CONF_LINKED_DEVICE_ID])

                    # Location monitoring devices
                    locations = zone_data.get("locations", {})
                    for location_data in locations.values():
                        if location_data.get("monitoring_device_id"):
                            used_devices.add(location_data["monitoring_device_id"])

                        # Plant devices in slots
                        slots = location_data.get("plant_slots", {})
                        for slot_data in slots.values():
                            if slot_data.get("plant_device_id"):
                                used_devices.add(slot_data["plant_device_id"])

        return used_devices

    @classmethod
    @callback  # type: ignore[misc]
    def async_get_supported_subentry_types(
        cls, _config_entry: config_entries.ConfigEntry[dict[str, Any]]
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "location": LocationSubentryFlowHandler,
        }


class LocationSubentryFlowHandler(config_entries.ConfigSubentryFlow):  # type: ignore[misc]
    """Handle subentry flow for adding and modifying plant locations."""

    def __init__(self) -> None:
        """Initialize the LocationSubentryFlowHandler."""
        self._location_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle the initial step where user configures the location."""
        errors = {}

        if user_input is not None:
            # Validate location name
            if not user_input.get(CONF_NAME):
                errors[CONF_NAME] = "name_required"

            # Validate monitoring device if provided
            if user_input.get(CONF_MONITORING_DEVICE_ID):
                device_registry = dr.async_get(self.hass)
                device = device_registry.async_get(
                    user_input[CONF_MONITORING_DEVICE_ID]
                )
                if not device:
                    errors[CONF_MONITORING_DEVICE_ID] = "device_not_found"

            # Validate humidity entity if provided
            if user_input.get(CONF_HUMIDITY_ENTITY_ID):
                entity_registry = er.async_get(self.hass)
                entity = entity_registry.async_get(user_input[CONF_HUMIDITY_ENTITY_ID])
                if not entity:
                    errors[CONF_HUMIDITY_ENTITY_ID] = "entity_not_found"

            if not errors:
                # Get parent entry to determine zone information
                parent_entry = self._get_entry()
                zones = parent_entry.options.get("irrigation_zones", {})
                zone_id = "zone-1"  # Default zone for now
                zone = zones.get(zone_id, {})

                location_name = user_input[CONF_NAME]

                # Create location data
                # Initialize 10 empty slots for the new location
                plant_slots = {}
                for i in range(1, 11):
                    plant_slots[f"slot_{i}"] = {
                        "name": f"Slot {i}",
                        "plant_device_id": None,
                    }

                location_data = {
                    "name": location_name,
                    "zone_id": zone_id,
                    "monitoring_device_id": user_input.get(CONF_MONITORING_DEVICE_ID),
                    "humidity_entity_id": user_input.get(CONF_HUMIDITY_ENTITY_ID),
                    "plant_slots": plant_slots,
                }

                # Generate unique device ID for this location
                device_id = (
                    f"plant_location_{parent_entry.entry_id}_{zone_id}_"
                    f"{slugify(location_name)}"
                )

                return self.async_create_entry(
                    title=f"{zone.get('name', 'Zone')} - {location_name}",
                    data={
                        "device_id": device_id,
                        "parent_entry_id": parent_entry.entry_id,
                        **location_data,
                    },
                )

        # Show form to configure location
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Optional(CONF_MONITORING_DEVICE_ID): DeviceSelector(
                        DeviceSelectorConfig(integration="xiaomi_ble")
                    ),
                    vol.Optional(CONF_HUMIDITY_ENTITY_ID): EntitySelector(
                        EntitySelectorConfig(domain="sensor", device_class="humidity")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Handle reconfiguring this location including plant slot management."""
        if user_input is not None:
            action = user_input.get(CONF_ACTION)
            if action == ACTION_ADD_SLOT:
                return await self.async_step_add_slot()
            if action == "edit_location":
                return await self.async_step_edit_location()

        # Get current subentry data
        subentry = self._get_reconfigure_subentry()
        plant_slots = subentry.data.get("plant_slots", {})

        # Create action options
        actions = [
            SelectOptionDict(value="edit_location", label="Edit Location Details"),
            SelectOptionDict(value=ACTION_ADD_SLOT, label="Manage Plant Slots"),
        ]

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACTION): SelectSelector(
                        SelectSelectorConfig(
                            options=actions,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            description_placeholders={
                "location_name": subentry.title,
                "slot_count": str(len(plant_slots)),
            },
        )

    async def async_step_edit_location(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Handle editing location details."""
        subentry = self._get_reconfigure_subentry()
        errors = {}

        if user_input is not None:
            errors = self._validate_location_input(user_input)
            if not errors:
                new_data, new_title = self._process_location_update(
                    subentry, user_input
                )
                return self.async_update_and_abort(
                    self._get_entry(), subentry, data_updates=new_data, title=new_title
                )

        return self._show_location_form(subentry, errors)

    def _validate_location_input(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Validate location input and return any errors."""
        errors = {}

        # Validate location name
        if not user_input.get(CONF_NAME):
            errors[CONF_NAME] = "name_required"

        # Validate monitoring device if provided
        if user_input.get(CONF_MONITORING_DEVICE_ID):
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get(user_input[CONF_MONITORING_DEVICE_ID])
            if not device:
                errors[CONF_MONITORING_DEVICE_ID] = "device_not_found"

        # Validate humidity entity if provided
        if user_input.get(CONF_HUMIDITY_ENTITY_ID):
            entity_registry = er.async_get(self.hass)
            entity = entity_registry.async_get(user_input[CONF_HUMIDITY_ENTITY_ID])
            if not entity:
                errors[CONF_HUMIDITY_ENTITY_ID] = "entity_not_found"

        return errors

    def _process_location_update(
        self, subentry: Any, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        """Process location update and return new data and title."""
        location_name = user_input[CONF_NAME]

        # Handle clearing of optional fields
        monitoring_device_id = self._normalize_optional_field(
            user_input, CONF_MONITORING_DEVICE_ID
        )
        humidity_entity_id = self._normalize_optional_field(
            user_input, CONF_HUMIDITY_ENTITY_ID
        )

        # Update subentry data
        new_data = dict(subentry.data)
        new_data.update(
            {
                "name": location_name,
                "monitoring_device_id": monitoring_device_id,
                "humidity_entity_id": humidity_entity_id,
            }
        )

        # Update title if name changed
        parent_entry = self._get_entry()
        zones = parent_entry.options.get("irrigation_zones", {})
        zone_id = subentry.data.get("zone_id", "zone-1")
        zone = zones.get(zone_id, {})
        new_title = f"{zone.get('name', 'Zone')} - {location_name}"

        return new_data, new_title

    def _normalize_optional_field(
        self, user_input: dict[str, Any], field_name: str
    ) -> str | None:
        """Normalize an optional field, handling empty strings and missing keys."""
        if field_name not in user_input:
            return None

        value = user_input.get(field_name)
        return None if value == "" else value

    def _show_location_form(
        self, subentry: Any, errors: dict[str, str]
    ) -> config_entries.SubentryFlowResult:
        """Show the location editing form."""
        schema_dict = {
            vol.Required(CONF_NAME): str,
            vol.Optional(CONF_MONITORING_DEVICE_ID): DeviceSelector(
                DeviceSelectorConfig(integration="xiaomi_ble")
            ),
            vol.Optional(CONF_HUMIDITY_ENTITY_ID): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="humidity")
            ),
        }

        # Use suggested values to show current assignments but allow clearing
        suggested_values = {CONF_NAME: subentry.data.get("name", "")}
        if subentry.data.get("monitoring_device_id"):
            suggested_values[CONF_MONITORING_DEVICE_ID] = subentry.data[
                "monitoring_device_id"
            ]
        if subentry.data.get("humidity_entity_id"):
            suggested_values[CONF_HUMIDITY_ENTITY_ID] = subentry.data[
                "humidity_entity_id"
            ]

        return self.async_show_form(
            step_id="edit_location",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema_dict), suggested_values
            ),
            errors=errors,
        )

    async def async_step_add_slot(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Handle adding/editing plant slots using 10 dropdown boxes."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = self._process_slot_user_input(subentry, user_input)
            if not errors:
                return self.async_update_and_abort(
                    self._get_entry(), subentry, data_updates=new_data
                )

        return self._show_slot_form(subentry, errors)

    def _process_slot_user_input(
        self, subentry: Any, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Process user input for slot management."""
        # DEBUG: Log what we received from Home Assistant
        _LOGGER.error("=== SLOT MANAGEMENT DEBUG ===")
        _LOGGER.error("Raw user_input received: %s", user_input)

        # Get current slots for comparison
        current_slots = subentry.data.get("plant_slots", {})
        _LOGGER.error("Current slots before processing: %s", current_slots)

        # Update subentry data with all slot assignments
        new_data = dict(subentry.data)
        if "plant_slots" not in new_data:
            new_data["plant_slots"] = {}

        # Start with current slots as base, then apply user changes
        new_data["plant_slots"] = dict(current_slots)

        # Process each slot
        for i in range(1, 11):
            slot_key = f"slot_{i}"
            self._process_individual_slot(
                i, slot_key, user_input, current_slots, new_data["plant_slots"]
            )

        _LOGGER.error("Final new_data['plant_slots']: %s", new_data["plant_slots"])
        _LOGGER.error("=== END SLOT MANAGEMENT DEBUG ===")
        return new_data

    def _process_individual_slot(
        self,
        slot_num: int,
        slot_key: str,
        user_input: dict[str, Any],
        current_slots: dict[str, Any],
        new_slots: dict[str, Any],
    ) -> None:
        """Process an individual slot assignment."""
        current_device = current_slots.get(slot_key, {}).get("plant_device_id")

        if slot_key not in user_input:
            # User didn't submit this slot = they want to clear it
            _LOGGER.error("Clearing %s: not in user input (user cleared it)", slot_key)
            new_slots[slot_key] = {"name": f"Slot {slot_num}", "plant_device_id": None}
            if current_device:
                _LOGGER.error("  CHANGE: %s -> None (CLEARED)", current_device)
        else:
            # User submitted this slot = process their choice
            plant_device_id = self._validate_slot_device(user_input.get(slot_key))
            new_slots[slot_key] = {
                "name": f"Slot {slot_num}",
                "plant_device_id": plant_device_id,
            }
            self._log_slot_change(slot_key, current_device, plant_device_id)

    def _validate_slot_device(self, device_id: str | None) -> str | None:
        """Validate and normalize a slot device ID."""
        # Normalize empty strings to None
        if device_id == "":
            _LOGGER.error("  Normalized empty string to None")
            return None

        # Validate device if one is selected
        if device_id:
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get(device_id)
            if not device:
                _LOGGER.error("  Invalid device %s, clearing to None", device_id)
                return None
            device_name = device.name_by_user or device.name or device_id[:8]
            _LOGGER.error("  Valid device: %s", device_name)

        return device_id

    def _log_slot_change(
        self, _slot_key: str, current_device: str | None, new_device: str | None
    ) -> None:
        """Log slot changes for debugging."""
        _LOGGER.error("  Final result: %s", new_device)
        if current_device != new_device:
            _LOGGER.error("  CHANGE: %s -> %s", current_device, new_device)
        else:
            _LOGGER.error("  NO CHANGE: %s", new_device)

    def _show_slot_form(
        self, subentry: Any, errors: dict[str, str]
    ) -> config_entries.SubentryFlowResult:
        """Show the slot assignment form."""
        plant_slots = subentry.data.get("plant_slots", {})
        current_assignments = self._build_current_assignments_list(plant_slots)
        schema_dict, suggested_values = self._build_slot_schema_and_values(plant_slots)
        description_text = self._build_slot_description(current_assignments)

        return self.async_show_form(
            step_id="add_slot",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema_dict), suggested_values
            ),
            errors=errors,
            description_placeholders={
                "location_name": subentry.title,
                "current_assignments": description_text,
            },
        )

    def _build_current_assignments_list(self, plant_slots: dict[str, Any]) -> list[str]:
        """Build a list of current slot assignments."""
        current_assignments = []
        device_registry = dr.async_get(self.hass)
        for i in range(1, 11):
            slot_data = plant_slots.get(f"slot_{i}", {})
            device_id = slot_data.get("plant_device_id")
            if device_id:
                device = device_registry.async_get(device_id)
                device_name = "Unknown Device"
                if device:
                    device_name = device.name_by_user or device.name or device_id[:8]
                current_assignments.append(f"Slot {i}: {device_name}")
        return current_assignments

    def _build_slot_schema_and_values(
        self, plant_slots: dict[str, Any]
    ) -> tuple[dict[Any, Any], dict[str, str]]:
        """Build schema and suggested values for slot form."""
        schema_dict: dict[Any, Any] = {}
        suggested_values: dict[str, str] = {}

        for i in range(1, 11):
            slot_key = f"slot_{i}"
            schema_dict[vol.Optional(slot_key)] = DeviceSelector(
                DeviceSelectorConfig(integration=OPENPLANTBOOK_DOMAIN)
            )

            slot_data = plant_slots.get(slot_key, {})
            current_assignment = slot_data.get("plant_device_id")
            if current_assignment:
                suggested_values[slot_key] = current_assignment

        return schema_dict, suggested_values

    def _build_slot_description(self, current_assignments: list[str]) -> str:
        """Build description text for slot form."""
        description_text = "Assign plants to slots. Leave empty to clear a slot."
        if current_assignments:
            description_text += "\n\nCurrent assignments:\n" + "\n".join(
                current_assignments
            )
        return description_text
