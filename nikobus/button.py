"""Nikobus Button entity"""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, BRAND

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> bool:
    """Set up Nikobus button entities from a config entry."""
    dataservice = hass.data[DOMAIN].get(entry.entry_id)

    entities = []

    # If the PyPI library provides an API method to fetch button data, replace `dict_button_data` with it
    if dataservice.api.dict_button_data:
        for button in dataservice.api.dict_button_data.get("nikobus_button", {}).values():
            impacted_modules_info = [
                {"address": impacted_module["address"], "group": impacted_module["group"]}
                for impacted_module in button.get("impacted_module", [])
            ]

            entity = NikobusButtonEntity(
                hass,
                dataservice,
                button.get("description"),
                button.get("address"),
                button.get("operation_time"),
                impacted_modules_info,
            )

            entities.append(entity)

    async_add_entities(entities)

class NikobusButtonEntity(CoordinatorEntity, ButtonEntity):
    """Representation of a Nikobus button entity within Home Assistant."""

    def __init__(self, hass: HomeAssistant, dataservice, description, address, operation_time, impacted_modules_info) -> None:
        """Initialize the button entity with data from the Nikobus configuration."""
        super().__init__(dataservice)
        self._hass = hass
        self._dataservice = dataservice
        self._description = description
        self._address = address
        self._operation_time = int(operation_time) if operation_time else None
        self.impacted_modules_info = impacted_modules_info

        self._attr_name = f"Nikobus Push Button {address}"
        self._attr_unique_id = f"{DOMAIN}_{address}"

    @property
    def device_info(self):
        """Return device information about this button entity."""
        return {
            "identifiers": {(DOMAIN, self._address)},
            "name": self._description,
            "manufacturer": BRAND,
            "model": "Push Button",
        }

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return extra state attributes of the button entity."""
        impacted_modules_str = ", ".join(
            f"{module['address']}_{module['group']}" for module in self.impacted_modules_info
        )
        return {"impacted_modules": impacted_modules_str}

    async def async_press(self) -> None:
        """Handle button press."""
        event_data = {
            "address": self._address,
            "operation_time": self._operation_time
        }

        # Pass both the address and operation_time to the async_event_handler
        await self._dataservice.async_event_handler("ha_button_pressed", event_data)
