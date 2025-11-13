"""
Buttons for the Plant Assistant integration.

This module provides buttons for controlling irrigation zone functionality,
including reset buttons for error count tracking.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Set up buttons for a config entry.

    Creates reset error count buttons for irrigation zones with esphome devices.
    """
    _LOGGER.debug(
        "Setting up buttons for entry: %s (%s)",
        entry.title,
        entry.entry_id,
    )

    buttons: list[ButtonEntity] = []

    # Skip individual subentry processing - they are handled by main entry
    if "device_id" in entry.data and not entry.subentries:
        _LOGGER.debug(
            "Skipping individual subentry processing for %s - handled by main entry",
            entry.entry_id,
        )
        return

    # Create irrigation zone error count reset buttons for zones with esphome devices
    device_registry = dr.async_get(hass)
    zones = entry.options.get("irrigation_zones", {})
    for zone_id, zone in zones.items():
        if linked_device_id := zone.get("linked_device_id"):
            zone_name = zone.get("name") or f"Zone {zone_id}"
            zone_device = device_registry.async_get(linked_device_id)
            if zone_device and zone_device.identifiers:
                zone_device_identifier = next(iter(zone_device.identifiers))

                # Create reset error count button
                reset_button = IrrigationZoneErrorCountResetButton(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    zone_id=zone_id,
                )
                buttons.append(reset_button)
                _LOGGER.debug(
                    "Created error count reset button for irrigation zone %s",
                    zone_name,
                )

    _LOGGER.info("Adding %d buttons for entry %s", len(buttons), entry.entry_id)
    async_add_entities(buttons)


class IrrigationZoneErrorCountResetButton(ButtonEntity, RestoreEntity):
    """
    Button that resets the error count for an irrigation zone.

    When pressed, this button sets the error count sensor value to 0.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone error count reset button.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Error Count Reset"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:restart"

        # Create unique ID
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "error_count_reset",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

    async def async_press(self) -> None:
        """Handle button press - reset the error count to 0."""
        try:
            # Construct the error count sensor entity_id
            zone_name_safe = self.zone_name.lower().replace(" ", "_")

            # The error count sensor entity_id follows the pattern:
            # sensor.zone_name_error_count
            error_count_entity_id = f"sensor.{zone_name_safe}_error_count"

            # Set the state to 0
            self.hass.states.async_set(error_count_entity_id, "0")

            _LOGGER.debug(
                "Reset error count for zone %s (entity: %s)",
                self.zone_name,
                error_count_entity_id,
            )
        except Exception as exc:  # noqa: BLE001 - Defensive
            _LOGGER.warning(
                "Error resetting error count for %s: %s",
                self.zone_name,
                exc,
            )
