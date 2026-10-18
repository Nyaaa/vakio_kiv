import contextlib
import logging

from homeassistant.components import mqtt
from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    CONF_PREFIX,
    DEFAULT_PREFIX,
    GATE_ENDPOINT,
    KIV_STATE_ON,
    KIV_STATE_OFF,
    MODE_ENDPOINT,
    STATE_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vakio Kiv cover from a config entry."""
    config = hass.data[DOMAIN].get(config_entry.entry_id, {})
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


class VakioVentCover(CoverEntity, RestoreEntity):
    """Representation of a Vakio Kiv vent cover with 4 positions."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
    )
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
        self._workmode_topic = f"{prefix}/{MODE_ENDPOINT}"
        self._is_on = True
        self._target_position: int | None = None
        self._boot_detected: bool = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Vakio Kiv",
            manufacturer="Vakio",
            model="Kiv Smart",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT events and restore previous state."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            pos = last_state.attributes.get("current_position")
            if pos is not None:
                with contextlib.suppress(ValueError, TypeError):
                    self._attr_current_cover_position = int(pos)
                    self._target_position = self._attr_current_cover_position

        # Subscribe and auto-cleanup on unload
        for topic, handler, qos in (
            (self._gate_topic, self._handle_position_message, 0),
            (self._state_topic, self._handle_state_message, 1),
            (self._workmode_topic, self._handle_workmode_message, 0),
        ):
            self.async_on_remove(
                await mqtt.async_subscribe(self.hass, topic, handler, qos=qos)
            )

        self.async_write_ha_state()

    async def async_publish(self, topic: str, payload: str) -> None:
        """Publish a retained message to MQTT."""
        await mqtt.async_publish(self.hass, topic, payload, qos=1, retain=True)

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
        return not self._is_on or self._attr_current_cover_position == 0

    async def async_open_cover(self, **kwargs) -> None:
        """Open the vent fully (position 100)."""
        await self.async_set_cover_position(position=100)

    async def async_close_cover(self, **kwargs) -> None:
        """Close the vent (position 0)."""
        await self.async_set_cover_position(position=0)

    async def async_set_cover_position(self, position: int = 0, **kwargs) -> None:
        """Move the vent to a specific position (mapped to 0%, 25%, 50%, 75%, 100%)."""
        gate_val = round(position / 25)
        new_position = gate_val * 25
        self._target_position = new_position

        if gate_val == 0:
            await self.async_publish(self._state_topic, KIV_STATE_OFF)
            self._is_on = False
            self._attr_current_cover_position = 0
        else:
            if not self._is_on:
                await self.async_publish(self._state_topic, KIV_STATE_ON)
                self._is_on = True

            await self.async_publish(self._gate_topic, str(gate_val))
            self._attr_current_cover_position = new_position

        self.async_write_ha_state()

    @callback
    def _handle_position_message(self, msg) -> None:
        """Handle new position messages from MQTT."""
        try:
            position_value = int(msg.payload)
            if 1 <= position_value <= 4:
                # If device just cold-booted, re-assert the user's chosen target
                if self._boot_detected and self._target_position is not None:
                    self._boot_detected = False

                    if self._target_position == 0:
                        self.hass.async_create_task(
                            self.async_publish(self._state_topic, KIV_STATE_OFF)
                        )
                        self._is_on = False
                        self._attr_current_cover_position = 0
                        self.async_write_ha_state()
                        return

                    target_gate = self._target_position // 25
                    if position_value != target_gate:
                        _LOGGER.info(
                            "Device booted to %d, restoring user target %d",
                            position_value,
                            target_gate,
                        )
                        self.hass.async_create_task(
                            self.async_publish(self._gate_topic, str(target_gate))
                        )
                        self._attr_current_cover_position = self._target_position
                        self._is_on = True
                        self.async_write_ha_state()
                        return

                self._attr_current_cover_position = position_value * 25
                self._is_on = True
                self.async_write_ha_state()
        except ValueError:
            pass

    @callback
    def _handle_state_message(self, msg) -> None:
        """Handle new state messages from MQTT."""
        payload = msg.payload.lower()
        if payload == KIV_STATE_OFF:
            self._is_on = False
            self._attr_current_cover_position = 0
            self.async_write_ha_state()
        elif payload == KIV_STATE_ON:
            self._is_on = True
            self.async_write_ha_state()

    @callback
    def _handle_workmode_message(self, msg) -> None:
        """Handle device boot broadcast on workmode topic."""
        _LOGGER.debug("Device boot sequence started via workmode (%s)", msg.payload)
        self._boot_detected = True
