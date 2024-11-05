"""API for Nikobus"""

import asyncio
import logging

from nikobusconnect import NikobusConnect, NikobusConnectionError, NikobusDataError
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, DIMMER_DELAY
from .nkbconfig import NikobusConfig
from .nkblistener import NikobusEventListener
from .nkbcommand import NikobusCommandHandler

_LOGGER = logging.getLogger(__name__)

class Nikobus:
    def __init__(self, hass, config_entry: ConfigEntry, connection_string, async_event_handler):
        self._hass = hass
        self._config_entry = config_entry
        self._async_event_handler = async_event_handler
        self._nikobus_connection = NikobusConnect(connection_string)
        self._nikobus_config = NikobusConfig(self._hass)
        self._nikobus_listener = NikobusEventListener(self._hass, self._config_entry, self._nikobus_connection, self.button_discovery, self.process_feedback_data)
        self.nikobus_command_handler = NikobusCommandHandler(self._hass, self._nikobus_connection, self._nikobus_listener, {})

        self.dict_module_data = {}
        self.dict_button_data = {}
        self.dict_scene_data = {}

    @classmethod
    async def create(cls, hass, config_entry, connection_string, async_event_handler):
        """Create a new instance of Nikobus and establish a connection."""
        _LOGGER.debug(f"Creating Nikobus instance with connection string: {connection_string}")
        instance = cls(hass, config_entry, connection_string, async_event_handler)
        if await instance.connect():
            _LOGGER.info("Nikobus instance created and connected successfully")
            return instance
        _LOGGER.error("Failed to create Nikobus instance")
        return None

    async def connect(self) -> bool:
        """Connect to the Nikobus system and load module data."""
        if await self._nikobus_connection.connect():
            try:
                # Load module, button, and scene configuration data
                self.dict_module_data = await self._nikobus_config.load_json_data("nikobus_module_config.json", "module")
                self.dict_button_data = await self._nikobus_config.load_json_data("nikobus_button_config.json", "button")
                self.dict_scene_data = await self._nikobus_config.load_json_data("nikobus_scene_config.json", "scene")
                return True
            except HomeAssistantError as e:
                raise HomeAssistantError(f'An error occurred loading configuration files: {e}')
        return False

    async def listen_for_events(self):
        """Start listening for Nikobus events."""
        await self._nikobus_listener.start()

    async def command_handler(self):
        """Start processing Nikobus commands."""
        await self.nikobus_command_handler.start()

    async def refresh_nikobus_data(self) -> bool:
        """Refresh data for different module types in Nikobus."""
        for module_type in ['switch_module', 'dimmer_module', 'roller_module']:
            modules = self.dict_module_data.get(module_type)
            if modules:
                await self._refresh_module_type(modules)
        return True

    async def _refresh_module_type(self, modules_dict):
        """Refresh data for a given type of Nikobus module."""
        for address, module_data in modules_dict.items():
            _LOGGER.debug(f'Refreshing data for module address: {address}')
            state = ""
            channel_count = len(module_data.get("channels", []))
            groups_to_query = [1] if channel_count <= 6 else [1, 2]

            for group in groups_to_query:
                group_state = await self.nikobus_command_handler.get_output_state(address, group) or ""
                _LOGGER.debug(f'State for group {group}: {group_state} address: {address}')
                state += group_state

            self.nikobus_command_handler.set_bytearray_group_state(address, state)

    async def process_feedback_data(self, module_group, data):
        """Process feedback data from Nikobus."""
        try:
            module_address_raw = data[3:7]
            module_address = module_address_raw[2:] + module_address_raw[:2]
            module_state_raw = data[9:21]

            if module_address not in self.nikobus_command_handler._module_states:
                self.nikobus_command_handler._module_states[module_address] = bytearray(12)

            if module_group == 1:
                self.nikobus_command_handler._module_states[module_address][:6] = bytearray.fromhex(module_state_raw)
            elif module_group == 2:
                self.nikobus_command_handler._module_states[module_address][6:] = bytearray.fromhex(module_state_raw)

            await self._async_event_handler("nikobus_refreshed", {
                'impacted_module_address': module_address
            })

        except Exception as e:
            _LOGGER.error(f"Error processing feedback data: {e}", exc_info=True)

    async def button_discovery(self, address: str) -> None:
        """Discover button information and add to configuration if new."""
        _LOGGER.debug(f"Discovering button at address: {address}.")
        if "nikobus_button" not in self.dict_button_data:
            self.dict_button_data["nikobus_button"] = {}

        if address not in self.dict_button_data["nikobus_button"]:
            self.dict_button_data["nikobus_button"][address] = {
                "description": f"DISCOVERED - Nikobus Button #N{address}",
                "address": address,
                "impacted_module": [{"address": "", "group": ""}]
            }
            await self._nikobus_config.write_json_data("nikobus_button_config.json", "button", self.dict_button_data)

    async def turn_on_light(self, address: str, channel: int, brightness: int) -> None:
        """Turn on a light at the given brightness level."""
        await self.nikobus_command_handler.set_output_state(address, channel, brightness)

    async def turn_off_light(self, address: str, channel: int) -> None:
        """Turn off a light by setting brightness to 0."""
        await self.nikobus_command_handler.set_output_state(address, channel, 0)

    async def open_cover(self, address: str, channel: int) -> None:
        """Open a cover."""
        await self.nikobus_command_handler.set_output_state(address, channel, 0x01)

    async def close_cover(self, address: str, channel: int) -> None:
        """Close a cover."""
        await self.nikobus_command_handler.set_output_state(address, channel, 0x02)

    async def stop_cover(self, address: str, channel: int, direction: str) -> None:
        """Stop a cover in motion."""
        await self.nikobus_command_handler.set_output_state(address, channel, 0x00)

class NikobusConnectError(HomeAssistantError):
    """Custom exception for handling Nikobus connection errors."""
    pass

class NikobusDataError(HomeAssistantError):
    """Custom exception for handling Nikobus data retrieval errors."""
    pass
