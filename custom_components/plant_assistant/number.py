"""Number entities for the Plant Assistant integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


class IrrigationZoneNumber(NumberEntity, RestoreEntity):
    """
    Base class for irrigation zone number entities.

    This is a base class for all number entities associated with irrigation zones.
    The entity value is restored on Home Assistant restarts.
    """

    # Override in subclasses
    _number_type: str = "base_number"
    _number_name_suffix: str = "Number"
    _min_value: float = 0
    _max_value: float = 100
    _step_value: float = 1
    _unit_of_measurement: str | None = None
    _icon: str | None = None
    _initial_value: float | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        _zone_device: Any,
    ) -> None:
        """
        Initialize the irrigation zone number entity.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple
                (domain, device_id) for the irrigation zone.
            zone_name: The name of the irrigation zone.
            _zone_device: The zone device entry from device registry.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name

        # Set entity attributes
        self._attr_name = f"{zone_name} {self._number_name_suffix}"
        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            self._number_type,
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        # Use the zone device identifiers directly
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        # Set number entity specific attributes
        self._attr_native_min_value = self._min_value
        self._attr_native_max_value = self._max_value
        self._attr_native_step = self._step_value
        self._attr_native_unit_of_measurement = self._unit_of_measurement
        self._attr_icon = self._icon

        # Initialize value - default to None
        self._native_value: float | None = None
        self._restored = False

    @property
    def native_value(self) -> float | None:
        """Return the current native value."""
        return self._native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the native value."""
        self._native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set %s number %s to %f",
            self._number_type,
            self.entity_id,
            value,
        )

    async def async_added_to_hass(self) -> None:
        """Restore previous state when entity is added to Home Assistant."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (last_state := await self.async_get_last_state()) and not self._restored:
            self._restored = True
            if last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._native_value = float(last_state.state)
                except (ValueError, TypeError):
                    self._native_value = self._initial_value
            else:
                self._native_value = self._initial_value

            _LOGGER.debug(
                "Restored %s number %s with state: %s",
                self._number_type,
                self.entity_id,
                self._native_value,
            )
        elif not self._restored:
            # No previous state available, use initial value
            self._native_value = self._initial_value
            self._restored = True


class FertiliserInjectionDaysNumber(IrrigationZoneNumber):
    """
    Fertiliser Injection Days number for an irrigation zone.

    This number entity controls the number of days for fertiliser injection
    for irrigation zones associated with esphome devices.
    """

    _number_type = "fertiliser_injection_days"
    _number_name_suffix = "Fertiliser Injection Days"
    _min_value = 1
    _max_value = 30
    _step_value = 1
    _unit_of_measurement = "days"
    _icon = "mdi:calendar-plus"
    _initial_value = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for the Plant Assistant integration."""
    numbers: list[NumberEntity] = []
    device_registry = dr.async_get(hass)

    # Get the entry options containing irrigation zones
    entry_opts = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id, {})
    zones_dict = entry_opts.get("irrigation_zones", {})

    # List of number classes to create for each zone
    number_classes = [
        FertiliserInjectionDaysNumber,
    ]

    # Create number entities for each zone with esphome linked device
    for zone_id, zone in zones_dict.items():
        # Check if this zone has a linked esphome device
        if linked_device_id := zone.get("linked_device_id"):
            zone_name = zone.get("name") or f"Zone {zone_id}"

            # Get the zone device from device registry
            zone_device = device_registry.async_get(linked_device_id)
            if not zone_device:
                _LOGGER.warning(
                    "Could not find zone device with ID %s for zone %s",
                    linked_device_id,
                    zone_name,
                )
                continue

            # Get the first identifier from the zone device
            zone_device_identifier = (
                next(iter(zone_device.identifiers))
                if zone_device.identifiers
                else (DOMAIN, linked_device_id)
            )

            # Create all number entities for this zone
            for number_class in number_classes:
                number = number_class(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    _zone_device=zone_device,
                )

                numbers.append(number)

                _LOGGER.debug(
                    "Created %s number entity for irrigation zone %s (device: %s)",
                    number_class.__name__,
                    zone_name,
                    linked_device_id,
                )

    # Add entities to Home Assistant
    if numbers:
        async_add_entities(numbers)
