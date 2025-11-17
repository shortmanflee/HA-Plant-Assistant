"""Entity monitoring for Plant Assistant integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class EntityMonitor:
    """Monitor entity registry changes and update mirrored entities accordingly."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the entity monitor."""
        self.hass = hass
        self._entity_registry: er.EntityRegistry | None
        try:
            self._entity_registry = er.async_get(hass)
        except (TypeError, AttributeError):
            # Handle mock environments during testing
            _LOGGER.debug("Failed to get entity registry - likely in test environment")
            self._entity_registry = None
        self._unsubscribe_registry_updated: Any = None

    async def async_setup(self) -> None:
        """Set up the entity monitor."""
        _LOGGER.debug("Setting up entity monitor")

        # Only subscribe if entity registry is available
        if self._entity_registry is not None:
            # Subscribe to entity registry updates
            self._unsubscribe_registry_updated = self.hass.bus.async_listen(
                "entity_registry_updated", self._handle_entity_registry_updated
            )

        _LOGGER.debug("Entity monitor setup complete")

    @callback
    def _handle_entity_registry_updated(self, event: Event) -> None:
        """Handle entity registry update events."""
        try:
            event_data = event.data
            action = event_data.get("action")
            entity_id = event_data.get("entity_id")
            old_entity_id = event_data.get("old_entity_id")

            _LOGGER.debug(
                "Entity registry event - Action: %s, Entity ID: %s, Old Entity ID: %s",
                action,
                entity_id,
                old_entity_id,
            )

            # Handle entity ID rename
            if (
                action == "update"
                and old_entity_id
                and entity_id
                and old_entity_id != entity_id
            ):
                _LOGGER.info(
                    "Entity renamed from %s to %s - checking for mirror entities"
                    " to update",
                    old_entity_id,
                    entity_id,
                )
                self.hass.async_create_task(
                    self._handle_entity_rename(old_entity_id, entity_id)
                )

        except Exception:
            _LOGGER.exception("Error handling entity registry update")

    async def _handle_entity_rename(
        self, old_entity_id: str, new_entity_id: str
    ) -> None:
        """Handle entity rename by updating mirror entities and config entries."""
        try:
            # Find all mirror entities that reference the old entity ID
            mirror_entities = await self._find_mirror_entities_for_source(old_entity_id)

            if mirror_entities:
                _LOGGER.info(
                    "Found %d mirror entities to update for renamed source "
                    "entity %s -> %s",
                    len(mirror_entities),
                    old_entity_id,
                    new_entity_id,
                )

                # Update each mirror entity's source reference
                for mirror_entity_id in mirror_entities:
                    await self._update_mirror_entity_source(
                        mirror_entity_id, old_entity_id, new_entity_id
                    )
            else:
                _LOGGER.debug(
                    "No mirror entities found for renamed entity %s", old_entity_id
                )

            # Update all config entries that reference the renamed entity
            # This ensures state change listeners are re-subscribed after reload
            await self._update_all_config_entries_for_rename(
                old_entity_id, new_entity_id
            )

        except Exception:
            _LOGGER.exception(
                "Error handling entity rename from %s to %s",
                old_entity_id,
                new_entity_id,
            )

    def _get_entity_id_from_unique_id(self, unique_id: str) -> str | None:
        """
        Look up the current entity_id for a given unique_id.

        This helps handle cases where the source entity was renamed but we only
        have its unique_id stored. Returns the current entity_id if found.
        """
        if not self._entity_registry or not unique_id:
            return None

        try:
            for entity_entry in self._entity_registry.entities.values():
                if entity_entry.unique_id == unique_id:
                    return entity_entry.entity_id
        except (TypeError, AttributeError, ValueError):
            pass

        return None

    def _get_unique_id_from_entity_id(self, entity_id: str) -> str | None:
        """
        Look up the unique_id for a given entity_id.

        Used to capture and store unique_ids when updating configurations.
        """
        if not self._entity_registry or not entity_id:
            return None

        try:
            entity_entry = self._entity_registry.async_get(entity_id)
            if entity_entry and entity_entry.unique_id:
                return entity_entry.unique_id
        except (TypeError, AttributeError, ValueError):
            pass

        return None

    async def _update_all_config_entries_for_rename(
        self, old_entity_id: str, new_entity_id: str
    ) -> None:
        """
        Update all config entries that reference the renamed entity.

        This method searches through all Plant Assistant config entries to find
        any that reference the old entity ID and updates them to use the new ID.
        After updating, it triggers a reload so state change listeners are
        re-subscribed with the correct entity IDs.
        """
        if not self._entity_registry:
            _LOGGER.debug(
                "Entity registry not available - skipping config entry updates"
            )
            return

        try:
            # Get all config entries for Plant Assistant
            config_entries = self.hass.config_entries.async_entries(DOMAIN)

            for config_entry in config_entries:
                try:
                    # Check if this entry references the renamed entity
                    await self._update_config_entry_source_entity(
                        config_entry, old_entity_id, new_entity_id
                    )
                except Exception:
                    _LOGGER.exception(
                        "Error updating config entry %s for renamed entity %s -> %s",
                        config_entry.entry_id,
                        old_entity_id,
                        new_entity_id,
                    )

        except Exception:
            _LOGGER.exception(
                "Error updating config entries for renamed entity %s -> %s",
                old_entity_id,
                new_entity_id,
            )

    async def _find_mirror_entities_for_source(
        self, source_entity_id: str
    ) -> list[str]:
        """Find all mirror entities that reference a specific source entity."""
        mirror_entities: list[str] = []

        if not self._entity_registry:
            _LOGGER.debug(
                "Entity registry not available - skipping mirror entity search"
            )
            return mirror_entities

        try:
            # First, get the unique_id of the source entity for reliable matching
            source_unique_id = None
            try:
                source_entry = self._entity_registry.async_get(source_entity_id)
                if source_entry and source_entry.unique_id:
                    source_unique_id = source_entry.unique_id
            except (TypeError, AttributeError, ValueError):
                pass

            # Get all entities for our domain
            for entity_entry in self._entity_registry.entities.values():
                if (
                    entity_entry.domain != "sensor"
                    or not entity_entry.unique_id.startswith(DOMAIN)
                ):
                    continue

                # Check if this is a mirror entity by looking at unique_id pattern
                if any(
                    suffix in entity_entry.unique_id
                    for suffix in [
                        "_humidity_mirror",
                        "_temperature_mirror",
                        "_illuminance_mirror",
                        "_soil_moisture_mirror",
                        "_soil_conductivity_mirror",
                        "_soil_conductivity_status",
                        "_humidity_linked",  # Humidity linked sensors
                        "_monitor_",  # Fallback for generic monitoring sensors
                        "_esphome_running_status",  # ESPHome running status monitor
                    ]
                ):
                    # Get the entity state to check source attributes
                    state = self.hass.states.get(entity_entry.entity_id)
                    if state:
                        # Primary: Match by source_unique_id (most reliable)
                        # Resilient to entity renames
                        source_unique_id_match = (
                            source_unique_id is not None
                            and state.attributes.get("source_unique_id")
                            == source_unique_id
                        )

                        if source_unique_id_match:
                            mirror_entities.append(entity_entry.entity_id)
                            _LOGGER.debug(
                                "Found mirror entity %s referencing source %s "
                                "(unique_id_match=%s)",
                                entity_entry.entity_id,
                                source_entity_id,
                                source_unique_id_match,
                            )
                    else:
                        _LOGGER.debug(
                            "Mirror entity %s not found in states",
                            entity_entry.entity_id,
                        )
        except Exception:
            _LOGGER.exception("Error finding mirror entities")

        return mirror_entities

    async def _update_mirror_entity_source(
        self,
        mirror_entity_id: str,
        old_source_entity_id: str,
        new_source_entity_id: str,
    ) -> None:
        """Update a mirror entity's source entity reference directly."""
        try:
            _LOGGER.info(
                "Updating mirror entity %s source from %s to %s",
                mirror_entity_id,
                old_source_entity_id,
                new_source_entity_id,
            )

            # Find the actual sensor object in stored sensors
            mirror_sensor = None

            # Look through all stored sensors
            sensors_data = self.hass.data.get(DOMAIN, {}).get("sensors", {})
            for sensors in sensors_data.values():
                if not isinstance(sensors, list):
                    continue

                for sensor in sensors:
                    if (
                        hasattr(sensor, "entity_id")
                        and sensor.entity_id == mirror_entity_id
                        and hasattr(sensor, "async_update_source_entity")
                    ):
                        mirror_sensor = sensor
                        break

                if mirror_sensor:
                    break

            if not mirror_sensor:
                _LOGGER.warning(
                    "Could not find mirror sensor object for %s", mirror_entity_id
                )
                return

            # Update the sensor's source entity directly
            await mirror_sensor.async_update_source_entity(new_source_entity_id)

            _LOGGER.info(
                "Successfully updated mirror sensor %s source entity to %s",
                mirror_entity_id,
                new_source_entity_id,
            )

        except Exception:
            _LOGGER.exception(
                "Error updating mirror entity %s",
                mirror_entity_id,
            )

    async def _update_config_entry_source_entity(  # noqa: PLR0912, PLR0915
        self,
        config_entry: ConfigEntry[dict[str, Any]],
        old_source_entity_id: str,
        new_source_entity_id: str,
    ) -> None:
        """Update the source entity ID in a config entry's options and reload."""
        try:
            # Get current options
            options = dict(config_entry.options)
            data = dict(config_entry.data)
            updated = False

            # Capture the unique_id of the new source entity for resilient tracking
            new_unique_id = self._get_unique_id_from_entity_id(new_source_entity_id)

            # Check if this is a main Plant Assistant entry with locations
            if "irrigation_zones" in options:
                zones = dict(options["irrigation_zones"])
                for zone_id, zone_data_raw in zones.items():
                    zone_data = dict(zone_data_raw)
                    zone_name = zone_data.get("name", f"Zone {zone_id}")

                    # Get the linked device ID for this zone
                    linked_device_id = zone_data.get("linked_device_id")

                    # If we have a linked device, discover switch entities from it
                    # instead of constructing entity IDs from zone name
                    if linked_device_id:
                        # Import helper to avoid circular imports
                        from .sensor import (  # noqa: PLC0415
                            find_device_entities_by_pattern,
                        )

                        switch_entities = find_device_entities_by_pattern(
                            self.hass,
                            linked_device_id,
                            "switch",
                            [
                                "schedule",
                                "sunrise_schedule",
                                "afternoon_schedule",
                                "sunset_schedule",
                                "allow_rain_water_delivery",
                                "allow_water_main_delivery",
                            ],
                        )

                        # Build field mappings from discovered entities
                        switch_field_mappings = {}
                        for keyword, (entity_id, _unique_id) in switch_entities.items():
                            if keyword == "schedule":
                                switch_field_mappings[entity_id] = (
                                    "master_schedule_switch_unique_id"
                                )
                            elif keyword == "sunrise_schedule":
                                switch_field_mappings[entity_id] = (
                                    "sunrise_switch_unique_id"
                                )
                            elif keyword == "afternoon_schedule":
                                switch_field_mappings[entity_id] = (
                                    "afternoon_switch_unique_id"
                                )
                            elif keyword == "sunset_schedule":
                                switch_field_mappings[entity_id] = (
                                    "sunset_switch_unique_id"
                                )
                            elif keyword == "allow_rain_water_delivery":
                                switch_field_mappings[entity_id] = (
                                    "allow_rain_water_delivery_switch_unique_id"
                                )
                            elif keyword == "allow_water_main_delivery":
                                switch_field_mappings[entity_id] = (
                                    "allow_water_main_delivery_switch_unique_id"
                                )
                    else:
                        # Fallback: no linked device, skip switch processing
                        switch_field_mappings = {}

                    # Check if any zone-level switch was renamed
                    for (
                        expected_entity_id,
                        unique_id_field,
                    ) in switch_field_mappings.items():
                        if (
                            expected_entity_id == old_source_entity_id
                            and new_unique_id
                            and unique_id_field not in zone_data
                        ):
                            # This zone's switch was renamed - store new unique_id
                            zone_data[unique_id_field] = new_unique_id
                            updated = True
                            _LOGGER.info(
                                "Captured %s for zone %s after rename: "
                                "%s -> %s (unique_id: %s)",
                                unique_id_field,
                                zone_name,
                                old_source_entity_id,
                                new_source_entity_id,
                                new_unique_id,
                            )

                    if "locations" in zone_data:
                        locations = dict(zone_data["locations"])
                        for location_id, location_data_raw in locations.items():
                            location_data = dict(location_data_raw)

                            # Update humidity entity reference
                            if (
                                location_data.get("humidity_entity_id")
                                == old_source_entity_id
                            ):
                                location_data["humidity_entity_id"] = (
                                    new_source_entity_id
                                )
                                # Also store unique_id for resilience
                                if new_unique_id:
                                    location_data["humidity_entity_unique_id"] = (
                                        new_unique_id
                                    )
                                updated = True
                                _LOGGER.info(
                                    "Updated humidity_entity_id in zone %s,"
                                    " location %s: %s -> %s (unique_id: %s)",
                                    zone_id,
                                    location_id,
                                    old_source_entity_id,
                                    new_source_entity_id,
                                    new_unique_id or "unknown",
                                )

                            locations[location_id] = location_data
                        zone_data["locations"] = locations
                    zones[zone_id] = zone_data
                options["irrigation_zones"] = zones

            # Check if this is a subentry with direct entity references
            elif "humidity_entity_id" in data:
                if data["humidity_entity_id"] == old_source_entity_id:
                    # Update the data (not options for subentries)
                    data["humidity_entity_id"] = new_source_entity_id
                    # Also store unique_id for resilience
                    if new_unique_id:
                        data["humidity_entity_unique_id"] = new_unique_id
                    updated = True
                    _LOGGER.info(
                        "Updated subentry data humidity_entity_id: %s -> %s"
                        " (unique_id: %s)",
                        old_source_entity_id,
                        new_source_entity_id,
                        new_unique_id or "unknown",
                    )

            # Check if the renamed entity belongs to a monitoring device
            monitoring_device_update_needed = (
                await self._check_monitoring_device_entity_update(
                    config_entry, old_source_entity_id, new_source_entity_id
                )
            )

            if updated or monitoring_device_update_needed:
                if updated:
                    # Update the config entry with new data/options
                    if "irrigation_zones" in options:
                        self.hass.config_entries.async_update_entry(
                            config_entry, options=options
                        )
                    else:
                        self.hass.config_entries.async_update_entry(
                            config_entry, data=data
                        )

                # Reload the config entry to apply changes
                _LOGGER.info(
                    "Reloading config entry %s to apply entity ID changes",
                    config_entry.entry_id,
                )
                await self.hass.config_entries.async_reload(config_entry.entry_id)

                _LOGGER.info(
                    "Successfully reloaded entry for source entity change: %s -> %s",
                    old_source_entity_id,
                    new_source_entity_id,
                )
            else:
                _LOGGER.debug(
                    "No configuration updates needed for source entity change:"
                    " %s -> %s",
                    old_source_entity_id,
                    new_source_entity_id,
                )

        except Exception:
            _LOGGER.exception(
                "Error updating config entry for source entity change %s -> %s",
                old_source_entity_id,
                new_source_entity_id,
            )

    async def _check_monitoring_device_entity_update(
        self,
        config_entry: ConfigEntry[dict[str, Any]],
        old_source_entity_id: str,
        new_source_entity_id: str,
    ) -> bool:
        """Check if the renamed entity belongs to a monitoring device."""
        try:
            if self._entity_registry is None:
                return False

            # Get the device that the renamed entity belongs to
            old_entity_entry = self._entity_registry.async_get(old_source_entity_id)
            if not old_entity_entry or not old_entity_entry.device_id:
                return False

            device_id = old_entity_entry.device_id

            # Check if this device is used as a monitoring device in the config entry
            options = config_entry.options
            data = config_entry.data

            # Check main entry locations
            if "irrigation_zones" in options:
                for zone_data in options["irrigation_zones"].values():
                    if "locations" in zone_data:
                        for location_data in zone_data["locations"].values():
                            if location_data.get("monitoring_device_id") == device_id:
                                _LOGGER.info(
                                    "Found monitoring device %s with renamed"
                                    " entity %s -> %s",
                                    device_id,
                                    old_source_entity_id,
                                    new_source_entity_id,
                                )
                                return True

            # Check subentry monitoring device
            elif (
                "monitoring_device_id" in data
                and data["monitoring_device_id"] == device_id
            ):
                _LOGGER.info(
                    "Found monitoring device %s in subentry with renamed"
                    " entity %s -> %s",
                    device_id,
                    old_source_entity_id,
                    new_source_entity_id,
                )
                return True
            return False  # noqa: TRY300

        except Exception:
            _LOGGER.exception(
                "Error checking monitoring device for entity %s",
                old_source_entity_id,
            )
            return False

    async def async_unload(self) -> None:
        """Unload the entity monitor."""
        if self._unsubscribe_registry_updated:
            self._unsubscribe_registry_updated()
            self._unsubscribe_registry_updated = None

        _LOGGER.debug("Entity monitor unloaded")


# Global instance
_monitor: EntityMonitor | None = None


async def async_setup_entity_monitor(hass: HomeAssistant) -> None:
    """Set up the global entity monitor."""
    global _monitor  # noqa: PLW0603

    if _monitor is None:
        _monitor = EntityMonitor(hass)

        # Only set up if entity registry is available (not in test environment)
        if _monitor._entity_registry is not None:  # noqa: SLF001
            await _monitor.async_setup()
            # Store reference in hass data for cleanup
            hass.data.setdefault(DOMAIN, {})["entity_monitor"] = _monitor
        else:
            _LOGGER.debug(
                "Entity registry not available - skipping entity monitor setup"
            )


async def async_unload_entity_monitor(hass: HomeAssistant) -> None:
    """Unload the global entity monitor."""
    global _monitor  # noqa: PLW0603

    if _monitor is not None:
        await _monitor.async_unload()
        _monitor = None

    # Remove reference from hass data
    domain_data = hass.data.get(DOMAIN, {})
    domain_data.pop("entity_monitor", None)
