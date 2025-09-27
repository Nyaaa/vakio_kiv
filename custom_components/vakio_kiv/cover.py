"""Cover platform for Vakio Kiv."""
from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_PREFIX,
    DEFAULT_PREFIX,
    GATE_ENDPOINT,
    KIV_STATE_ON,
    KIV_STATE_OFF,
    STATE_ENDPOINT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vakio Kiv cover from a config entry."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    if not config:
        config = config_entry.data

    prefix = config.get(CONF_PREFIX, DEFAULT_PREFIX)

    async_add_entities(
        [
            VakioVentCover(
                hass=hass,
                prefix=prefix,
                entry_id=config_entry.entry_id,
            )
        ]
    )


class VakioVentCover(CoverEntity):
    """Representation of a Vakio Kiv vent cover with 4 positions."""

    _attr_supported_features = CoverEntityFeature.SET_POSITION
    _attr_current_cover_position = 0
    _attr_name = "Vent damper"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, prefix: str, entry_id: str) -> None:
        """Initialize the vent cover."""
        self.hass = hass
        self._prefix = prefix
        self._attr_unique_id = f"{entry_id}_damper"
        self._gate_topic = f"{prefix}/{GATE_ENDPOINT}"
        self._state_topic = f"{prefix}/{STATE_ENDPOINT}"

        # TODO deduplicate
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Vakio Kiv",
            manufacturer="Vakio",
            model="Kiv Smart"
        )

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""
        await super().async_added_to_hass()
        await mqtt.async_subscribe(
            self.hass, self._gate_topic, self._handle_position_message
        )
        await mqtt.async_subscribe(
            self.hass, self._state_topic, self._handle_state_message, 1
        )

    async def async_publish(self, topic, payload):
        """Publish a message to MQTT."""
        await mqtt.async_publish(self.hass, topic, payload, 1)

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        return self._attr_current_cover_position == 0

    async def async_open_cover(self, **kwargs):
        """Open the vent fully (position 100)."""
        await self.async_set_cover_position(position=100)

    async def async_close_cover(self, **kwargs):
        """Close the vent (position 0)."""
        await self.async_set_cover_position(position=0)

    async def async_set_cover_position(self, position: int = 0, **kwargs):
        """Move the vent to a specific position."""

        # Map to nearest of the 5 positions (0%, 25%, 50%, 75%, 100%)
        if position < 12:  # 0-12% → 0%
            new_position = 0
        elif position < 37:  # 12-37% → 25%
            new_position = 25
        elif position < 62:  # 37-62% → 50%
            new_position = 50
        elif position < 87:  # 62-87% → 75%
            new_position = 75
        else:  # 87-100% → 100%
            new_position = 100

        if self._attr_current_cover_position == 0 and new_position > 0:
            await self.async_publish(self._state_topic, KIV_STATE_ON)
        elif self._attr_current_cover_position > 0 and new_position == 0:
            await self.async_publish(self._state_topic, KIV_STATE_OFF)

        # Send command to set the vent position (1-4)
        await self.async_publish(self._gate_topic, str(new_position // 33 + 1))
        
        self._attr_current_cover_position = new_position
        self.async_write_ha_state()

    @callback
    async def _handle_position_message(self, msg):
        """Handle new position messages."""
        try:
            # Convert from 1-4 to 0-100 range (25%, 50%, 75%, 100%)
            position_value = int(msg.payload)
            if position_value < 1 or position_value > 4:
                await self.async_set_cover_position(self._attr_current_cover_position)
            else:
                self._attr_current_cover_position = position_value * 25
                self.async_write_ha_state()
        except ValueError:
            pass  # Invalid position received, ignore # TODO add logger

    @callback
    def _handle_state_message(self, msg):
        """Handle new state messages."""
        if msg.payload.lower() == KIV_STATE_OFF:
            self._attr_current_cover_position = 0
            self.async_write_ha_state()
