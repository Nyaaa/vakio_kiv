"""Sensor platform for Vakio Kiv."""
from __future__ import annotations

import logging

from homeassistant.components import mqtt
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_PREFIX, DEFAULT_PREFIX, DOMAIN, HUD_ENDPOINT, TEMP_ENDPOINT

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vakio Kiv sensor devices from a config entry."""
    entry_id = config_entry.entry_id
    config = hass.data[DOMAIN].get(entry_id, {})
    if not config:
        config = config_entry.data

    prefix = config.get(CONF_PREFIX, DEFAULT_PREFIX)
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Vakio Kiv",
        manufacturer="Vakio",
        model="Kiv Smart",
    )

    async_add_entities(
        [
            VakioTemperatureSensor(prefix, entry_id, device_info),
            VakioHumiditySensor(prefix, entry_id, device_info),
        ]
    )


class VakioTemperatureSensor(SensorEntity, RestoreEntity):
    """Representation of a Vakio Kiv temperature sensor."""

    _attr_has_entity_name = True
    _attr_name = "Temperature"
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, prefix: str, entry_id: str, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._attr_unique_id = f"{entry_id}_temperature"
        self._attr_device_info = device_info
        self._topic = f"{prefix}/{TEMP_ENDPOINT}"

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT events and restore previous state."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = float(last_state.state)
            except (ValueError, TypeError):
                self._attr_native_value = None

        self.async_on_remove(
            await mqtt.async_subscribe(self.hass, self._topic, self._handle_temp_message)
        )
        self.async_write_ha_state()

    @callback
    def _handle_temp_message(self, msg) -> None:
        """Handle new temperature messages."""
        try:
            self._attr_native_value = float(msg.payload)
            self.async_write_ha_state()
        except ValueError:
            _LOGGER.warning("Invalid temperature payload received: %s", msg.payload)


class VakioHumiditySensor(SensorEntity, RestoreEntity):
    """Representation of a Vakio Kiv humidity sensor."""

    _attr_has_entity_name = True
    _attr_name = "Humidity"
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, prefix: str, entry_id: str, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        self._attr_unique_id = f"{entry_id}_humidity"
        self._attr_device_info = device_info
        self._topic = f"{prefix}/{HUD_ENDPOINT}"

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT events and restore previous state."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = float(last_state.state)
            except (ValueError, TypeError):
                self._attr_native_value = None

        self.async_on_remove(
            await mqtt.async_subscribe(self.hass, self._topic, self._handle_hud_message)
        )
        self.async_write_ha_state()

    @callback
    def _handle_hud_message(self, msg) -> None:
        """Handle new humidity messages."""
        try:
            self._attr_native_value = float(msg.payload)
            self.async_write_ha_state()
        except ValueError:
            _LOGGER.warning("Invalid humidity payload received: %s", msg.payload)
