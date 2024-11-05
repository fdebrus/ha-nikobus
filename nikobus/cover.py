import logging
import asyncio
import time
from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass,
    ATTR_POSITION,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from .const import DOMAIN, BRAND

_LOGGER = logging.getLogger(__name__)

STATE_STOPPED = 0x00
STATE_OPENING = 0x01
STATE_CLOSING = 0x02
FULL_OPERATION_BUFFER = 3

class PositionEstimator:
    """Estimates the current position of the cover based on elapsed time and direction."""

    def __init__(self, duration_in_seconds):
        self._duration_in_seconds = duration_in_seconds
        self._start_time = None
        self._direction = None
        self.position = None
        _LOGGER.debug("PositionEstimator initialized with duration: %s seconds", duration_in_seconds)

    def start(self, direction, position=None):
        """Start the movement in the given direction."""
        self._direction = 1 if direction == "opening" else -1
        self._start_time = time.monotonic()
        self.position = position if position is not None else (0 if self._direction == 1 else 100)
        _LOGGER.debug("Movement started in direction: %s, initial position: %s", direction, self.position)

    def get_position(self):
        """Calculate and return the current position estimate."""
        if self._start_time is None or self._direction is None or self.position is None:
            return None

        elapsed_time = time.monotonic() - self._start_time
        progress = (elapsed_time / self._duration_in_seconds) * 100 * self._direction
        new_position = max(0, min(100, self.position + progress))

        _LOGGER.debug("Position calculated to: %s based on elapsed time: %s seconds", new_position, elapsed_time)
        return int(new_position)

    def stop(self):
        """Stop the movement and finalize the position."""
        if self._start_time is not None:
            self.position = self.get_position()
        self._direction = None
        self._start_time = None
        _LOGGER.debug("Movement stopped. Current estimated position: %s", self.position)

    @property
    def duration_in_seconds(self):
        """Publicly expose the duration_in_seconds attribute."""
        return self._duration_in_seconds

async def async_setup_entry(hass, entry, async_add_entities) -> bool:
    dataservice = hass.data[DOMAIN].get(entry.entry_id)

    roller_modules = dataservice.api.dict_module_data.get('roller_module', {})

    entities = [
        NikobusCoverEntity(
            hass,
            dataservice,
            cover_module_data.get("description"),
            cover_module_data.get("model"),
            address,
            i,
            channel["description"],
            channel.get("operation_time", "30"),
        )
        for address, cover_module_data in roller_modules.items()
        for i, channel in enumerate(cover_module_data.get("channels", []), start=1)
        if not channel["description"].startswith("not_in_use")
    ]

    async_add_entities(entities)

class NikobusCoverEntity(CoordinatorEntity, CoverEntity, RestoreEntity):
    """Represents a Nikobus cover entity within Home Assistant."""

    def __init__(self, hass: HomeAssistant, dataservice, description, model, address, channel, channel_description, operation_time) -> None:
        """Initialize the cover entity with data from the Nikobus system configuration."""
        super().__init__(dataservice)
        self.hass = hass
        self._dataservice = dataservice
        self._description = description
        self._model = model
        self._address = address
        self._channel = channel
        self._direction = None
        self._previous_state = None

        self._operation_time = float(operation_time) if operation_time else None
        self._position_estimator = PositionEstimator(duration_in_seconds=float(operation_time))
        self._position = 100

        self._in_motion = False
        self._movement_task = None

        self._last_position_change_time = time.monotonic()

        self._attr_name = channel_description
        self._attr_unique_id = f"{DOMAIN}_{self._address}_{self._channel}"
        self._attr_device_class = CoverDeviceClass.SHUTTER

        _LOGGER.debug("NikobusCoverEntity initialized for %s (address: %s, channel: %s)", channel_description, address, channel)

    @property
    def device_info(self):
        """Provide device information for Home Assistant."""
        return {
            "identifiers": {(DOMAIN, self._address)},
            "name": self._description,
            "manufacturer": BRAND,
            "model": self._model,
        }

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = super().extra_state_attributes or {}
        attributes['position'] = self._position
        return attributes

    @property
    def current_cover_position(self):
        """Return the current position of the cover."""
        return self._position

    @property
    def is_open(self):
        """Return True if the cover is fully open."""
        return self._position == 100

    @property
    def is_closed(self):
        """Return True if the cover is fully closed."""
        return self._position == 0

    @property
    def is_opening(self):
        """Return True if the cover is currently opening."""
        return self._in_motion and self._direction == 'opening'

    @property
    def is_closing(self):
        """Return True if the cover is currently closing."""
        return self._in_motion and self._direction == 'closing'

    @property
    def supported_features(self):
        """Return supported features."""
        return (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.STOP |
            CoverEntityFeature.SET_POSITION
        )

    async def async_added_to_hass(self):
        """Register callbacks when entity is added to hass."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None:
            last_position = last_state.attributes.get(ATTR_POSITION)
            if last_position is not None:
                self._position = float(last_position)
                _LOGGER.debug("Restored position for %s to %s", self._attr_name, self._position)

        # Initialize previous state from current API state
        current_state = self._dataservice.api.get_cover_state(self._address, self._channel)
        self._previous_state = current_state

        # Subscribe to nikobus_button_pressed event
        self.hass.bus.async_listen('nikobus_button_pressed', self._handle_nikobus_button_event)

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        _LOGGER.debug("Opening cover %s", self._attr_name)
        await self._start_movement('opening')

    async def async_close_cover(self, **kwargs):
        """Close the cover."""
        _LOGGER.debug("Closing cover %s", self._attr_name)
        await self._start_movement('closing')

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        _LOGGER.debug("Stopping cover %s", self._attr_name)
        await self._dataservice.api.stop_cover(self._address, self._channel, self._direction)
        self._position_estimator.stop()
        self._position = self._position_estimator.position
        self._in_motion = False
        self._direction = None
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs):
        """Set the cover to a specific position."""
        target_position = kwargs.get(ATTR_POSITION)
        if target_position is not None:
            await self._start_movement('closing' if self._position > target_position else 'opening')
            await self._update_position_to_target(target_position)

    async def _start_movement(self, direction):
        """Start movement in the specified direction."""
        if self._in_motion:
            await self.async_stop_cover()

        self._direction = direction
        self._in_motion = True
        self._position_estimator.start(direction, self._position)
        await self._operate_cover()
        if not self._movement_task or self._movement_task.done():
            self._movement_task = self.hass.async_create_task(self._update_position_in_real_time())

    async def _operate_cover(self):
        """Send the command to operate the cover."""
        if self._direction == 'opening':
            await self._dataservice.api.open_cover(self._address, self._channel)
        elif self._direction == 'closing':
            await self._dataservice.api.close_cover(self._address, self._channel)
