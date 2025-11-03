"""Switch entities for the Plant Assistant integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


class MasterScheduleSwitch(SwitchEntity, RestoreEntity):
    """
    Master Schedule switch for an irrigation zone.

    This switch controls the master schedule for irrigation zones associated
    with esphome devices. The switch state is restored on Home Assistant restarts.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        _zone_device: Any,
    ) -> None:
        """
        Initialize the Master Schedule switch.

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
        self._attr_name = f"{zone_name} Master Schedule"
        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "master_schedule",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        # Use the zone device identifiers directly
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        # Initialize state - default to OFF
        self._is_on = False
        self._restored = False

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        return self._is_on

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn on the switch."""
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn off the switch."""
        self._is_on = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore previous state when entity is added to Home Assistant."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (last_state := await self.async_get_last_state()) and not self._restored:
            self._restored = True
            if last_state.state == STATE_ON:
                self._is_on = True
            elif last_state.state == STATE_OFF:
                self._is_on = False
            elif last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                # Try to parse as boolean
                try:
                    self._is_on = last_state.state.lower() == "true"
                except (AttributeError, ValueError):
                    self._is_on = False

            _LOGGER.debug(
                "Restored Master Schedule switch %s with state: %s",
                self.entity_id,
                self._is_on,
            )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities for the Plant Assistant integration."""
    switches: list[SwitchEntity] = []
    device_registry = dr.async_get(hass)

    # Get the entry options containing irrigation zones
    entry_opts = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id, {})
    zones_dict = entry_opts.get("irrigation_zones", {})

    # Create Master Schedule switch for each zone with esphome linked device
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

            # Create the Master Schedule switch for this zone
            master_schedule_switch = MasterScheduleSwitch(
                hass=hass,
                entry_id=entry.entry_id,
                zone_device_id=zone_device_identifier,
                zone_name=zone_name,
                _zone_device=zone_device,
            )

            switches.append(master_schedule_switch)

            _LOGGER.debug(
                "Created Master Schedule switch for irrigation zone %s (device: %s)",
                zone_name,
                linked_device_id,
            )

    # Add entities to Home Assistant
    if switches:
        async_add_entities(switches)
