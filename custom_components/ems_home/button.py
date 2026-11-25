"""Button platform for eMS Home: one click, one export link."""
from __future__ import annotations

import logging
from copy import deepcopy

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import EMSHomeCoordinator
from .export import async_announce, async_create_export, texts

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the history export button."""
    coordinator: EMSHomeCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([EMSHistoryExportButton(coordinator, entry)])


class EMSHistoryExportButton(CoordinatorEntity[EMSHomeCoordinator], ButtonEntity):
    """Write the stored sessions to a file and hand out a signed link.

    The button is the path for people who do not want to touch YAML: press it, get a
    notification with a download link. The service stays for automations.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "history_export"
    _attr_icon = "mdi:file-download-outline"

    def __init__(self, coordinator: EMSHomeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_history_export"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def available(self) -> bool:
        history = self.coordinator._history
        return history is not None and history.enabled

    async def async_press(self) -> None:
        hass = self.coordinator.hass  # the entity itself only has one once added
        history = self.coordinator._history
        sessions = deepcopy(history.sessions) if history is not None else []
        if not sessions:
            # An empty CSV would look like a broken export; say it instead.
            raise HomeAssistantError(texts(hass)["nothing"])
        try:
            ticket, url = await async_create_export(
                hass, [self.coordinator], sessions, "csv", {self._entry.entry_id}
            )
        except (OSError, ValueError, KeyError) as exc:
            raise HomeAssistantError(str(exc)) from exc
        if not ticket.rows:
            # Everything in the store was unusable; do not announce an empty file.
            raise HomeAssistantError(texts(hass)["nothing"])
        await async_announce(hass, ticket, url, self._entry.title)
