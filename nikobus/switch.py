import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, BRAND

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities) -> bool:
    """Set up Nikobus switch entities from a config entry."""
    dataservice = hass.data[DOMAIN].get(entry.entry_id)
    api = dataservice.api  # Use the API provided by the PyPI library

    switch_modules = api.get_module_data('switch_module')  # Assuming this method exists

    entities = [
        NikobusSwitchEntity(
            hass,
            api,
            switch_data.get("description"),
            switch_data.get("model"),
            address,
            i,
            channel.get("description")
        )
        for address, switch_data in switch_modules.items()
        for i, channel in enumerate(switch_data.get("channels", []), start=1)
        if not channel.get("description", "").startswith("not_in_use")
    ]

    async_add_entities(entities)


class NikobusSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Represents a Nikobus switch entity within Home Assistant."""

    def __init__(self, hass: HomeAssistant, api, description, model, address, channel, channel_description) -> None:
        """Initialize the switch entity with data from the Nikobus system configuration."""
        super().__init__(dataservice)
        self._api = api
        self._state = None
        self._description = description
        self._model = model
        self._address = address
        self._channel = channel

        self._attr_name = channel_description
        self._attr_unique_id = f"{DOMAIN}_{self._address}_{self._channel}"

    @property
    def device_info(self):
        """Return device information about this switch."""
        return {
            "identifiers": {(DOMAIN, self._address)},
            "name": self._description,
            "manufacturer": BRAND,
            "model": self._model,
        }

    @property
    def is_on(self):
        """Return True if the switch is on."""
        return self._state or False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._state = self._api.get_switch_state(self._address, self._channel)
        self.async_write_ha_state()

    async def async_turn_on(self):
        """Turn the switch on."""
        try:
            await self._api.turn_on_switch(self._address, self._channel)
            self._state = True
        except Exception as e:
            _LOGGER.error(f"Failed to turn on switch at address {self._address}, channel {self._channel}: {e}")
            self._state = False  # Reset state if there was an error
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn the switch off."""
        try:
            await self._api.turn_off_switch(self._address, self._channel)
            self._state = False
        except Exception as e:
            _LOGGER.error(f"Failed to turn off switch at address {self._address}, channel {self._channel}: {e}")
            self._state = True  # Reset state if there was an error
        self.async_write_ha_state()
