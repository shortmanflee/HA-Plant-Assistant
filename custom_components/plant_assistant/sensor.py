"""
Sensors for the Plant Assistant integration.

This module provides a minimal set of sensors used by the integration and
keeps implementations test-friendly by only relying on `hass.data` and the
`hass.states` mapping where possible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change

from . import aggregation
from .const import ATTR_PLANT_DEVICE_IDS, DOMAIN, MONITORING_SENSOR_MAPPINGS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


class MonitoringSensorMapping(TypedDict, total=False):
    """Type definition for monitoring sensor mappings."""

    device_class: SensorDeviceClass | str | None
    suffix: str
    icon: str
    name: str
    unit: str | None


_LOGGER = logging.getLogger(__name__)


def _detect_sensor_type_from_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    """
    Detect the sensor type from a source entity's device_class or entity_id.

    Args:
        hass: The Home Assistant instance.
        entity_id: The entity ID to detect the type from.

    Returns:
        The sensor type key (e.g., 'temperature', 'illuminance') or
        None if not detected.

    """
    # Map device_class to sensor type
    device_class_mapping = {
        "temperature": "temperature",
        "illuminance": "illuminance",
        "moisture": "soil_moisture",
        "conductivity": "soil_conductivity",
        "battery": "battery",
        "signal_strength": "signal_strength",
    }

    # Map entity_id patterns to sensor type
    entity_id_patterns = {
        "temperature": "temperature",
        "illuminance": "illuminance",
        "light": "illuminance",
        "moisture": "soil_moisture",
        "conductivity": "soil_conductivity",
        "battery": "battery",
        "signal": "signal_strength",
        "rssi": "signal_strength",
    }

    try:
        ent_reg = er.async_get(hass)
        if entity := ent_reg.async_get(entity_id):
            device_class = entity.device_class
            if device_class in device_class_mapping:
                return device_class_mapping[device_class]

        # Fallback to entity_id pattern matching
        entity_id_lower = entity_id.lower()
        for pattern, sensor_type in entity_id_patterns.items():
            if pattern in entity_id_lower:
                return sensor_type

    except (AttributeError, KeyError, ValueError) as exc:
        _LOGGER.debug(
            "Error detecting sensor type for %s: %s",
            entity_id,
            exc,
        )

    return None


def _has_plants_in_slots(data: Mapping[str, Any]) -> bool:
    """
    Check if there are any plants assigned to slots in the data.

    Args:
        data: The subentry data containing plant_slots.

    Returns:
        True if at least one slot has a plant_device_id assigned, False otherwise.

    """
    plant_slots = data.get("plant_slots", {})
    for slot in plant_slots.values():
        if isinstance(slot, dict) and slot.get("plant_device_id"):
            return True
    return False


def _get_monitoring_device_sensors(
    hass: HomeAssistant, monitoring_device_id: str
) -> dict[str, str]:
    """
    Get sensor entity IDs for a monitoring device.

    Args:
        hass: The Home Assistant instance.
        monitoring_device_id: The device ID of the monitoring device.

    Returns:
        A dict mapping sensor type names (e.g., 'illuminance', 'soil_conductivity')
        to their entity IDs. Returns empty dict if device not found.

    """
    device_sensors: dict[str, str] = {}

    try:
        # Get device and entity registries
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)

        # Try to get the device by ID
        if not (device := dev_reg.async_get(monitoring_device_id)):
            return device_sensors

        # Get all sensor entities for this device
        for entity in ent_reg.entities.values():
            if entity.device_id == device.id and entity.domain == "sensor":
                # Map sensor entity to sensor type based on device class or entity name
                device_class = entity.device_class

                if device_class == "illuminance":
                    device_sensors["illuminance"] = entity.entity_id
                elif device_class == "soil_conductivity":
                    device_sensors["soil_conductivity"] = entity.entity_id
                elif device_class == "battery":
                    device_sensors["battery"] = entity.entity_id
                elif device_class == "signal_strength":
                    device_sensors["signal_strength"] = entity.entity_id
                elif "illuminance" in entity.entity_id.lower():
                    device_sensors["illuminance"] = entity.entity_id
                elif "conductivity" in entity.entity_id.lower():
                    device_sensors["soil_conductivity"] = entity.entity_id
                elif "battery" in entity.entity_id.lower():
                    device_sensors["battery"] = entity.entity_id
                elif (
                    "signal" in entity.entity_id.lower()
                    or "rssi" in entity.entity_id.lower()
                ):
                    device_sensors["signal_strength"] = entity.entity_id

    except (AttributeError, KeyError, ValueError, TypeError) as exc:
        _LOGGER.debug(
            "Error getting monitoring device sensors for %s: %s",
            monitoring_device_id,
            exc,
        )

    return device_sensors


def _create_location_mirrored_sensors(
    hass: HomeAssistant,
    entry_id: str,
    location_device_id: str,
    location_name: str,
    monitoring_device_id: str,
) -> list[SensorEntity]:
    """
    Create mirrored sensors at a plant location for a monitoring device's entities.

    Args:
        hass: The Home Assistant instance.
        entry_id: The config entry ID.
        location_device_id: The device ID of the location.
        location_name: The name of the location.
        monitoring_device_id: The device ID of the monitoring device.

    Returns:
        A list of SensorEntity objects that mirror the monitoring device's sensors.

    """
    mirrored_sensors: list[SensorEntity] = []

    try:
        # Get device and entity registries
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)

        # Get the monitoring device
        monitoring_device = dev_reg.async_get(monitoring_device_id)
        if not monitoring_device:
            _LOGGER.warning(
                "Monitoring device %s not found for location %s",
                monitoring_device_id,
                location_name,
            )
            return mirrored_sensors

        # Scan for all sensor entities on the monitoring device
        for entity_entry in ent_reg.entities.values():
            if (
                entity_entry.device_id == monitoring_device.id
                and entity_entry.domain == "sensor"
            ):
                # Detect sensor type to get proper naming
                sensor_type = _detect_sensor_type_from_entity(
                    hass, entity_entry.entity_id
                )

                # Get display name from mappings if available, otherwise use entity name
                if sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS:
                    mapping: MonitoringSensorMapping = MONITORING_SENSOR_MAPPINGS[
                        sensor_type
                    ]
                    display_name = mapping.get(
                        "name", entity_entry.name or entity_entry.entity_id
                    )
                else:
                    display_name = entity_entry.name or entity_entry.entity_id

                # Create a mirrored sensor for this entity
                config = {
                    "entry_id": entry_id,
                    "source_entity_id": entity_entry.entity_id,
                    "device_name": location_name,
                    "entity_name": display_name,
                    "sensor_type": sensor_type,
                }

                mirrored_sensor = MonitoringSensor(
                    hass=hass,
                    config=config,
                    location_device_id=location_device_id,
                )
                mirrored_sensors.append(mirrored_sensor)
                _LOGGER.debug(
                    "Created mirrored sensor for %s at location %s",
                    entity_entry.entity_id,
                    location_name,
                )

    except (AttributeError, KeyError, ValueError, TypeError) as exc:
        _LOGGER.warning(
            "Error creating location mirrored sensors for %s: %s",
            location_name,
            exc,
        )

    return mirrored_sensors


@dataclass
class SimplePlantSensorDescription:
    """Description for a simple plant sensor."""

    key: str
    name: str
    device_class: str | None = None
    unit: str | None = None


class PlantCountSensor(SensorEntity):
    """A minimal plant count sensor used for examples and tests."""

    _attr_name = "Plant Assistant Plant Count"
    _attr_unique_id = f"{DOMAIN}_plant_count_example"

    def __init__(self) -> None:
        """Initialize the plant count sensor."""
        self._state = 0

    @property
    def native_value(self) -> int:
        """Return the native value of the sensor."""
        return self._state

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return str(self._attr_name)

    def update(self) -> None:  # pragma: no cover - sync update not exercised
        """Update the sensor state."""
        self._state = 0


async def _cleanup_orphaned_monitoring_sensors(  # noqa: PLR0912
    hass: HomeAssistant, entry: ConfigEntry[Any]
) -> None:
    """
    Clean up monitoring sensors that are no longer configured.

    When a monitoring device is disassociated from a location, any monitoring
    sensors that were created for that device should be fully removed rather
    than being left in an unavailable state.
    """
    try:
        entity_registry = er.async_get(hass)
        expected_monitoring_entities = set()

        # Collect expected monitoring sensor entities from all subentries
        if entry.subentries:
            for subentry in entry.subentries.values():
                if "device_id" in subentry.data:
                    monitoring_device_id = subentry.data.get("monitoring_device_id")
                    if monitoring_device_id:
                        try:
                            device_sensors = _get_monitoring_device_sensors(
                                hass, monitoring_device_id
                            )
                            # For each sensor on the monitoring device, add the
                            # unique_id of the mirrored sensor to expected entities
                            for mapped_type, source_entity_id in device_sensors.items():
                                # Detect sensor type if needed
                                detected_type = _detect_sensor_type_from_entity(
                                    hass, source_entity_id
                                )
                                sensor_type = (
                                    detected_type if detected_type else mapped_type
                                )

                                # Build unique_id pattern for mirrored sensors
                                # Format: plant_assistant_<entry_id>_<device>_<suffix>
                                location_name = subentry.data.get(
                                    "name", "Plant Location"
                                )
                                device_name_safe = location_name.lower().replace(
                                    " ", "_"
                                )

                                if (
                                    sensor_type
                                    and sensor_type in MONITORING_SENSOR_MAPPINGS
                                ):
                                    mapping: MonitoringSensorMapping = (
                                        MONITORING_SENSOR_MAPPINGS[sensor_type]
                                    )
                                    suffix = mapping.get("suffix", sensor_type)
                                else:
                                    # Fallback to sanitized source entity id
                                    source_entity_safe = source_entity_id.replace(
                                        ".", "_"
                                    )
                                    suffix = f"monitor_{source_entity_safe}"

                                unique_id = (
                                    f"{DOMAIN}_{subentry.subentry_id}_"
                                    f"{device_name_safe}_{suffix}"
                                )
                                expected_monitoring_entities.add(unique_id)
                        except (
                            ValueError,
                            TypeError,
                        ) as discovery_error:  # pragma: no cover
                            _LOGGER.debug(
                                "Failed to discover monitoring device sensors "
                                "for %s during monitoring sensor cleanup: %s",
                                monitoring_device_id,
                                discovery_error,
                            )

        # Find and remove orphaned monitoring entities
        entities_to_remove = []
        for entity_id, entity_entry in entity_registry.entities.items():
            if (
                entity_entry.platform != DOMAIN
                or entity_entry.domain != "sensor"
                or not entity_entry.unique_id
                or entity_entry.config_entry_id != entry.entry_id
            ):
                continue

            # Check if this is a monitoring sensor (has monitoring sensor suffixes)
            unique_id = entity_entry.unique_id
            monitoring_suffixes = [
                "_temperature_mirror",
                "_illuminance_mirror",
                "_soil_moisture_mirror",
                "_soil_conductivity_mirror",
                "_battery_level",
                "_signal_strength",
                "_monitor_",  # Fallback pattern for custom sensors
            ]

            if any(suffix in unique_id for suffix in monitoring_suffixes) and (
                unique_id not in expected_monitoring_entities
            ):
                entities_to_remove.append(entity_id)

        # Remove orphaned monitoring entities
        for entity_id in entities_to_remove:
            entity_registry.async_remove(entity_id)
            _LOGGER.debug("Removed orphaned monitoring sensor entity: %s", entity_id)

        if entities_to_remove:
            _LOGGER.info(
                "Cleaned up %d orphaned monitoring sensor entities for entry %s",
                len(entities_to_remove),
                entry.entry_id,
            )

    except Exception as exc:  # noqa: BLE001 - Defensive logging
        _LOGGER.warning(
            "Failed to cleanup orphaned monitoring sensors: %s",
            exc,
        )


async def async_setup_platform(
    _hass: HomeAssistant,
    _config: dict[str, Any] | None,
    async_add_entities: AddEntitiesCallback,
    _discovery_info: Any = None,
) -> None:
    """Set up the sensor platform (legacy)."""
    async_add_entities([PlantCountSensor()])


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Set up sensors for a config entry.

    Create one AggregatedSensor per configured location (metric defaulted
    to `min_light` for initial implementation).

    For subentries with monitoring devices, also create monitoring sensors.
    For locations with monitoring devices, create mirrored sensors.
    """
    _LOGGER.debug(
        "Setting up sensors for entry: %s (%s)",
        entry.title,
        entry.entry_id,
    )

    sensors: list[SensorEntity] = []

    # Skip individual subentry processing - they are handled by main entry
    # A subentry has "device_id" in data but no subentries of its own
    if "device_id" in entry.data and not entry.subentries:
        _LOGGER.debug(
            "Skipping individual subentry processing for %s - handled by main entry",
            entry.entry_id,
        )
        return

    # Only process main entries - subentries are handled by main entry processing
    # This avoids duplicate device creation

    # Main entry - process subentries like openplantbook_ref
    if entry.subentries:
        _LOGGER.info("Processing main entry with %d subentries", len(entry.subentries))

        # Clean up orphaned monitoring sensors before creating new ones
        await _cleanup_orphaned_monitoring_sensors(hass, entry)

        for subentry_id, subentry in entry.subentries.items():
            _LOGGER.debug(
                "Processing subentry %s with data: %s",
                subentry.subentry_id,
                subentry.data,
            )
            if "device_id" in subentry.data:
                subentry_entities = []

                location_name = subentry.data.get("name", "Plant Location")
                location_device_id = (
                    subentry.subentry_id
                )  # Use subentry ID as device identifier

                # Create plant count entity for this location
                plant_slots = subentry.data.get("plant_slots", {})
                plant_count_entity = PlantCountLocationSensor(
                    hass=hass,
                    entry_id=subentry.subentry_id,
                    location_name=location_name,
                    location_device_id=location_device_id,
                    plant_slots=plant_slots,
                )
                subentry_entities.append(plant_count_entity)

                # Create mirrored sensors for monitoring device if present
                monitoring_device_id = subentry.data.get("monitoring_device_id")
                if monitoring_device_id:
                    mirrored_sensors = _create_location_mirrored_sensors(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        monitoring_device_id=monitoring_device_id,
                    )
                    subentry_entities.extend(mirrored_sensors)
                    _LOGGER.debug(
                        "Added %d mirrored sensors for monitoring device %s"
                        " at location %s",
                        len(mirrored_sensors),
                        monitoring_device_id,
                        location_name,
                    )

                # Add entities with proper subentry association (like openplantbook_ref)
                _LOGGER.debug(
                    "Adding %d entities for subentry %s",
                    len(subentry_entities),
                    subentry_id,
                )
                # Note: config_subentry_id exists in HA 2025.8.3+ but not in type hint
                async_add_entities(
                    subentry_entities,
                    config_subentry_id=subentry_id,  # type: ignore[call-arg]
                )
            else:
                _LOGGER.warning("Subentry %s missing device_id", subentry_id)
        return

    # Main entry aggregated sensors for locations (if no subentries)
    zones = entry.options.get("irrigation_zones", {})
    sensors.extend(
        [
            AggregatedSensor(hass, entry.entry_id, zone_id, loc_id, "min_light")
            for zone_id, zone in zones.items()
            for loc_id in zone.get("locations", {})
        ]
    )

    _LOGGER.info("Adding %d sensors for entry %s", len(sensors), entry.entry_id)
    async_add_entities(sensors)


def _metric_to_attr(metric: str) -> str:
    """
    Map a metric key like 'min_light' to an entity attribute name.

    The openplantbook provider exposes attributes with names like
    'minimum_light', 'maximum_light', 'minimum_moisture', etc. Use simple
    heuristics to translate the configured metric key to the attribute name.
    """
    if metric.startswith("min_"):
        return f"minimum_{metric[4:]}"
    if metric.startswith("max_"):
        return f"maximum_{metric[4:]}"
    if metric.startswith("avg_"):
        return f"minimum_{metric[4:]}"
    return metric


class PlantCountLocationSensor(SensorEntity):
    """A sensor that counts the number of plants assigned to slots in a location."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_name: str,
        location_device_id: str,
        plant_slots: dict[str, Any],
    ) -> None:
        """Initialize the plant count location sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._location_name = location_name
        self._plant_slots = plant_slots

        # Entity name includes device name for better entity_id formatting
        self._attr_name = f"{location_name} Plant Count"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_plant_count"
        self._attr_icon = "mdi:flower-tulip"
        self._attr_native_unit_of_measurement = "plants"

        # Set up device info - associate with the location device
        device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )

        self._attr_device_info = device_info

    @property
    def native_value(self) -> int:
        """Return the count of plants assigned to slots."""
        count = 0
        for slot in self._plant_slots.values():
            if isinstance(slot, dict) and slot.get("plant_device_id"):
                count += 1
        return count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes about the plants assigned to slots."""
        plant_device_ids = [
            plant_id
            for slot in self._plant_slots.values()
            if isinstance(slot, dict) and (plant_id := slot.get("plant_device_id"))
        ]
        return {
            ATTR_PLANT_DEVICE_IDS: plant_device_ids,
            "location_device_id": self.location_device_id,
        }


class MonitoringSensor(SensorEntity):
    """A sensor that mirrors data from a monitoring device under a subentry."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        location_device_id: str | None = None,
    ) -> None:
        """Initialize the monitoring sensor."""
        self.hass = hass
        self.entry_id = config["entry_id"]
        self.source_entity_id = config["source_entity_id"]
        self.location_device_id = location_device_id
        device_name = config["device_name"]
        entity_name = config["entity_name"]
        sensor_type = config.get("sensor_type")

        # Set entity name to include device name for better entity_id formatting
        self._attr_name = f"{device_name} {entity_name}"

        # Generate unique_id using device name and sensor type suffix
        # Format: plant_assistant_<entry_id>_<device_name>_<sensor_type_suffix>
        if sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS:
            mapping: MonitoringSensorMapping = MONITORING_SENSOR_MAPPINGS[sensor_type]
            suffix = mapping.get("suffix", sensor_type)
        else:
            # Fallback to sanitized source entity id
            source_entity_safe = self.source_entity_id.replace(".", "_")
            suffix = f"monitor_{source_entity_safe}"

        # Create a safe device name for the unique_id
        device_name_safe = device_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{self.entry_id}_{device_name_safe}_{suffix}"

        self._state = None
        self._attributes = {}
        self._unsubscribe = None

        # Set device_class, icon, and unit from mappings if available
        if sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS:
            mapping_config: MonitoringSensorMapping = MONITORING_SENSOR_MAPPINGS[
                sensor_type
            ]
            device_class_val = mapping_config.get("device_class")
            if device_class_val:
                try:
                    self._attr_device_class = SensorDeviceClass(device_class_val)
                except ValueError:
                    self._attr_device_class = None
            self._attr_icon = mapping_config.get("icon")
            # Use unit from mapping if available, otherwise get from source
            unit = mapping_config.get("unit")
            if unit:
                self._attr_native_unit_of_measurement = unit

        # Initialize with current state of source entity
        if source_state := hass.states.get(self.source_entity_id):
            self._state = source_state.state
            self._attributes = dict(source_state.attributes)
            self._attributes["source_entity"] = self.source_entity_id

            # If no unit was set from mapping, try to get it from source entity
            if not hasattr(self, "_attr_native_unit_of_measurement"):
                source_unit = source_state.attributes.get("unit_of_measurement")
                if source_unit:
                    self._attr_native_unit_of_measurement = source_unit

        # Subscribe to source entity state changes
        try:
            self._unsubscribe = async_track_state_change(
                hass, self.source_entity_id, self._source_state_changed
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to source entity %s: %s",
                self.source_entity_id,
                exc,
            )

    @callback
    def _source_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle source entity state changes."""
        if new_state is None:
            self._state = None
            self._attributes = {}
        else:
            self._state = new_state.state
            self._attributes = dict(new_state.attributes)
            # Add reference to source
            self._attributes["source_entity"] = self.source_entity_id

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Return None for unavailable/unknown states to avoid Home Assistant errors
        # when device_class expects numeric values
        if self._state in ("unavailable", "unknown", None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        source_state = self.hass.states.get(self.source_entity_id)
        return source_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the subentry device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class AggregatedSensor(SensorEntity):
    """Aggregated sensor for a location metric (e.g., min_light)."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, zone_id: str, loc_id: str, metric: str
    ) -> None:
        """Initialize the aggregated sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.zone_id = zone_id
        self.loc_id = loc_id
        self.metric = metric
        self._value: Any = None
        self._attr_name = f"Plant Assistant {zone_id} {loc_id} {metric}"
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_zone_{zone_id}_loc_{loc_id}_{metric}"
        )
        self._unsubscribe = None
        self._plant_entity_ids: list[str] | None = None

        # subscribe to a humidity entity if configured for this location
        entry_opts = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry_id, {})
        zones = entry_opts.get("irrigation_zones", {})
        target_humidity_entity = None
        if zone_id in zones:
            locations = zones[zone_id].get("locations", {})
            if loc_id in locations:
                target_humidity_entity = locations[loc_id].get("humidity_entity_id")

        if target_humidity_entity:
            try:
                self._unsubscribe = async_track_state_change(
                    hass, target_humidity_entity, self._state_changed
                )
            except (AttributeError, KeyError, ValueError):
                self._unsubscribe = None

    def update(self) -> None:  # pragma: no cover - sync update not exercised
        """Update the sensor state."""
        # If we have mapped plant entity ids, compute from their attributes.
        if getattr(self, "_plant_entity_ids", None):
            plants = _plants_from_entity_states(
                self.hass, list(self._plant_entity_ids or [])
            )
            # Map metric key (e.g., 'min_light') to provider attribute name
            attr_key = _metric_to_attr(self.metric)
            if self.metric.startswith("min"):
                self._value = aggregation.min_metric(plants, attr_key)
            elif self.metric.startswith("max"):
                self._value = aggregation.max_metric(plants, attr_key)
            elif self.metric.startswith("avg"):
                self._value = aggregation.avg_metric(plants, attr_key)
            else:
                self._value = None
            return

        # Fallback for tests/non-HA runtime
        all_plants = self.hass.data.get(DOMAIN, {}).get("mock_plants", {})
        plants = all_plants.get(self.loc_id, [])
        self._value = aggregation.min_metric(plants, self.metric)

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self._value

    @callback
    def _state_changed(self, _entity_id: str, _old_state: Any, _new_state: Any) -> None:
        """Recompute aggregation when a tracked plant entity changes."""
        if getattr(self, "_plant_entity_ids", None):
            plants = _plants_from_entity_states(
                self.hass, list(self._plant_entity_ids or [])
            )
            attr_key = _metric_to_attr(self.metric)
            if self.metric.startswith("min"):
                self._value = aggregation.min_metric(plants, attr_key)
            elif self.metric.startswith("max"):
                self._value = aggregation.max_metric(plants, attr_key)
            elif self.metric.startswith("avg"):
                self._value = aggregation.avg_metric(plants, attr_key)
            else:
                self._value = None
            return

        all_plants = self.hass.data.get(DOMAIN, {}).get("mock_plants", {})
        plants = all_plants.get(self.loc_id, [])
        self._value = aggregation.min_metric(plants, self.metric)

    async def async_added_to_hass(self) -> None:  # pragma: no cover - runtime-only
        """
        Add entity to hass and subscribe to plant sensors.

        Map the configured location to plant entity IDs. Strategy:
        - If the location has a `monitoring_device_id`, prefer sensors whose
          attributes include `device_id` matching that value.
        - Otherwise, scan for sensors exposing a `plant_id` attribute.
        """
        try:
            plant_entity_ids = await self._discover_plant_entities()
            self._subscribe_to_plant_entities(plant_entity_ids)
        except (AttributeError, KeyError, ValueError):
            self._unsubscribe = None

    async def _discover_plant_entities(self) -> list[str]:
        """Discover plant entity IDs for this sensor."""
        mon_device_id = self._get_monitoring_device_id()

        # Try device registry approach first
        plant_entity_ids = self._get_entities_from_device_registry(mon_device_id)

        # Fall back to state scanning if needed
        if not plant_entity_ids:
            plant_entity_ids = self._get_entities_from_state_scan(mon_device_id)

        return list(dict.fromkeys([p for p in plant_entity_ids if p]))

    def _get_monitoring_device_id(self) -> str | None:
        """Get monitoring device ID from configuration."""
        entry_opts = (
            self.hass.data.get(DOMAIN, {}).get("entries", {}).get(self.entry_id, {})
        )
        zones = entry_opts.get("irrigation_zones", {})

        if self.zone_id not in zones:
            return None

        locations = zones[self.zone_id].get("locations", {})
        if self.loc_id not in locations:
            return None

        device_id = locations[self.loc_id].get("monitoring_device_id")
        return device_id if isinstance(device_id, str) else None

    def _get_entities_from_device_registry(
        self, mon_device_id: str | None
    ) -> list[str]:
        """Get plant entities using device registry."""
        if not mon_device_id:
            return []

        plant_entity_ids: list[str] = []

        try:
            ent_reg = er.async_get(self.hass)
            dev_reg = dr.async_get(self.hass)
        except (AttributeError, KeyError):
            return plant_entity_ids

        try:
            device = dev_reg.async_get_device({("plant_assistant", mon_device_id)})
        except (AttributeError, KeyError, ValueError):
            return plant_entity_ids

        if not device:
            return plant_entity_ids

        plant_entity_ids.extend(
            eid
            for ent in getattr(ent_reg, "entities", {}).values()
            if self._is_matching_sensor_entity(ent, device.id)
            and (eid := getattr(ent, "entity_id", None))
        )

        return plant_entity_ids

    def _is_matching_sensor_entity(self, ent: Any, device_id: str) -> bool:
        """Check if entity matches our criteria for sensor entities."""
        return (
            getattr(ent, "device_id", None) == device_id
            and getattr(ent, "domain", None) == "sensor"
        )

    def _get_entities_from_state_scan(self, mon_device_id: str | None) -> list[str]:
        """Get plant entities by scanning states."""
        states_all = self._get_all_sensor_states()

        return [
            entity_id
            for st in states_all
            if self._state_matches_criteria(st, mon_device_id)
            and (entity_id := getattr(st, "entity_id", None))
        ]

    def _get_all_sensor_states(self) -> list[Any]:
        """Get all sensor states from Home Assistant."""
        if hasattr(self.hass.states, "async_all"):
            states = self.hass.states.async_all("sensor")
            return list(states)
        states_dict = getattr(self.hass.states, "_states", {})
        return list(states_dict.values()) if states_dict else []

    def _state_matches_criteria(self, st: Any, mon_device_id: str | None) -> bool:
        """Check if a state matches our plant sensor criteria."""
        attrs = getattr(st, "attributes", {}) or {}
        if not isinstance(attrs, dict):
            return False

        has_plant_id = attrs.get("plant_id") is not None
        has_matching_device = mon_device_id and attrs.get("device_id") == mon_device_id
        return bool(has_plant_id or has_matching_device)

    def _subscribe_to_plant_entities(self, plant_entity_ids: list[str]) -> None:
        """Subscribe to plant entity state changes."""
        if not plant_entity_ids:
            return

        self._plant_entity_ids = plant_entity_ids
        try:
            self._unsubscribe = async_track_state_change(
                self.hass, plant_entity_ids, self._state_changed
            )
        except (AttributeError, KeyError, ValueError):
            self._unsubscribe = None

    async def async_will_remove_from_hass(
        self,
    ) -> None:  # pragma: no cover - runtime cleanup
        """Remove entity from Home Assistant."""
        if self._unsubscribe:
            self._unsubscribe()


def _plants_from_entity_states(
    hass: HomeAssistant, entity_ids: list[str]
) -> list[dict[str, Any]]:
    """
    Build a list of plant dicts from entity states.

    Each plant dict will include keys like 'minimum_light' etc. based on the
    state attributes of the sensor entities. This mirrors the shape expected
    by the aggregation helpers.
    """
    out: list[dict[str, Any]] = []
    for ent in entity_ids:
        if not (st := hass.states.get(ent)):
            continue
        attrs = getattr(st, "attributes", {}) or {}
        out.append(dict(attrs))
    return out


class PlantMoistureSensor(SensorEntity):
    """
    A placeholder plant moisture sensor.

    This sensor reads a synthetic moisture value from `hass.data` water events
    for demonstration. Real implementation should subscribe to device/entity
    sensors or other hardware inputs.
    """

    def __init__(self, hass: HomeAssistant, zone_id: str, loc_id: str) -> None:
        """Initialize the plant moisture sensor."""
        self.hass = hass
        self.zone_id = zone_id
        self.loc_id = loc_id
        self._value = None

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self._value

    def update(self) -> None:  # pragma: no cover - sync update
        """Update the sensor state."""
        events = self.hass.data.get(DOMAIN, {}).get("water_events", [])
        # last event affecting this location sets moisture (demo logic)
        for ev in reversed(events):
            if (
                ev.get("zone_id") == self.zone_id
                and ev.get("location_id") == self.loc_id
            ):
                # demo mapping: larger amount increases moisture; match tests by
                # dividing by 15 so 150 ml -> 90
                self._value = max(0, 100 - int(ev.get("amount_ml", 0) / 15))
                return
        self._value = None
        # end of PlantMoistureSensor
