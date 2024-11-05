import logging
from homeassistant.components.scene import Scene
from homeassistant.core import HomeAssistant

from .const import DOMAIN, BRAND
from nikobusconnect import NikobusScene

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> bool:
    """Set up Nikobus scenes from config entry."""
    _LOGGER.debug("Setting up Nikobus scenes.")

    dataservice = hass.data[DOMAIN].get(entry.entry_id)
    api = dataservice.api
    scene_data = api.get_scene_data()  # Assume this method exists in the library

    entities = [
        NikobusSceneEntity(hass, api, scene['description'], scene['id'], scene['channels'])
        for scene in scene_data
    ]

    _LOGGER.debug(f"Adding {len(entities)} Nikobus scene entities.")
    async_add_entities(entities)

class NikobusSceneEntity(Scene):
    def __init__(self, hass, api, description, scene_id, channels):
        """Initialize Nikobus Scene Entity."""
        self._hass = hass
        self._api = api
        self._description = description
        self._scene_id = scene_id
        self._channels = channels

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"nikobus_scene_{self._scene_id}"

    @property
    def device_info(self):
        """Link the scene to the Nikobus integration."""
        return {
            "identifiers": {(DOMAIN, self._scene_id)},
            "name": self._description,
            "manufacturer": BRAND,
            "model": "Scene",
        }

    @property
    def name(self) -> str:
        """Return the name of the scene."""
        return self._description

    async def async_activate(self) -> None:
        """Activate the scene using nikobusconnect's scene activation."""
        try:
            _LOGGER.debug(f"Activating scene {self._description} with ID {self._scene_id}")
            await self._api.activate_scene(self._scene_id)  # Assuming activate_scene is in the library
            _LOGGER.info(f"Scene '{self._description}' activated.")
        except Exception as e:
            _LOGGER.error(f"Failed to activate scene '{self._description}': {e}")
