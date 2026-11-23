"""Fork services for Spatial Context, registered after services.py's.

`get_map` is registered again here with optional fields (with none it is
exactly services.py's export); `query`, `update_settings` and `refresh_links`
are new. Kept out of services.py so that file stays as upstream has it.

Every service is admin-only, like the WebSocket API: the map holds the
whole floor plan and every placed device, `query` describes devices whatever
their exposure, `update_settings` changes the integration, and a mesh refresh
makes the Zigbee network re-scan itself. They are registered with Home
Assistant's `async_register_admin_service`, so a non-admin user's call is
refused (Unauthorized, or UnknownUser for a deleted user) while a call with no
user (an automation or script) is allowed. That helper takes
`supports_response` on every Home Assistant this integration supports
(minimum 2026.10).

`get_map`'s `floor`/`room` use the spatial engine (spatial/map_view.py): a
room matches by id or name, and devices are filed by where their pin sits.
The `GetSpatialMap` LLM tool uses upstream's filter (export.py), which files
them by their stored room.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .export import async_get_map_data
from .llm_api import async_sync_llm_api
from .spatial.ai import TOOLS, NotFound, async_run_tool
from .spatial.map_view import MapFilterError, async_get_map_view
from .storage import async_get_settings, async_save_settings

_GET_MAP_SCHEMA = vol.Schema(
    {
        vol.Optional("floor"): vol.All(str, vol.Length(max=256)),
        vol.Optional("room"): vol.All(str, vol.Length(max=256)),
        vol.Optional("compact"): bool,
        vol.Optional("include_links"): bool,
    }
)

_TEXT = vol.All(str, vol.Length(max=256))
_QUERY_SCHEMA = vol.Schema(
    {
        vol.Required("tool"): vol.In(TOOLS),
        vol.Optional("device"): _TEXT,
        vol.Optional("a"): _TEXT,
        vol.Optional("b"): _TEXT,
        vol.Optional("layer"): vol.In(["zigbee", "thread", "wifi", "bluetooth"]),
        vol.Optional("level"): _TEXT,
        vol.Optional("room"): _TEXT,
    }
)

# The settings the panel has no controls for, plus the AI switch (also in
# the panel's Settings > AI Assistants); same ranges as websocket_api.py's
# _SETTINGS_SCHEMA.
_UPDATE_SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional("llm_api_enabled"): bool,
        # The field's name before fork.10; same switch.
        vol.Optional("llm_tools_enabled"): bool,
        vol.Optional("floor_height_m"): vol.All(vol.Coerce(float), vol.Range(min=1.5, max=10)),
        vol.Optional("rf_path_loss_exponent"): vol.All(
            vol.Coerce(float), vol.Range(min=1.6, max=4.0)
        ),
        vol.Optional("rf_slab_loss_db"): vol.All(vol.Coerce(float), vol.Range(min=0, max=40)),
        vol.Optional("weak_link_threshold_db"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=60)
        ),
    }
)


async def async_setup_fork_services(hass: HomeAssistant) -> None:
    """Register the fork's services; call after services.async_setup_services,
    whose plain `get_map` this replaces."""

    async def get_map_service(call: ServiceCall) -> dict:
        """Return the spatial map data. With no fields, exactly the full
        export, as always; the optional fields narrow or compact it.
        Fields at their defaults count as none."""
        if not (
            call.data.get("floor")
            or call.data.get("room")
            or call.data.get("compact")
            or call.data.get("include_links")
        ):
            return await async_get_map_data(hass)
        try:
            return await async_get_map_view(
                hass,
                floor=call.data.get("floor"),
                room=call.data.get("room"),
                compact=call.data.get("compact", False),
                include_links=call.data.get("include_links", False),
            )
        except MapFilterError as err:
            raise HomeAssistantError(str(err)) from err

    async_register_admin_service(
        hass,
        DOMAIN,
        "get_map",
        get_map_service,
        _GET_MAP_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def query_service(call: ServiceCall) -> dict:
        """The spatial tools' outputs (spatial_tools.py), for ha-mcp, REST
        and scripts."""
        args = dict(call.data)
        tool = args.pop("tool")
        try:
            return await async_run_tool(hass, tool, args)
        except (NotFound, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    async_register_admin_service(
        hass,
        DOMAIN,
        "query",
        query_service,
        _QUERY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def update_settings_service(call: ServiceCall) -> None:
        """Change the AI and RF-model settings, which the panel has no
        controls for yet. Fields left out keep their value."""
        changes = dict(call.data)
        if "llm_tools_enabled" in changes:
            legacy = changes.pop("llm_tools_enabled")
            changes.setdefault("llm_api_enabled", legacy)
        settings = await async_get_settings(hass)
        await async_save_settings(hass, {**settings, **changes})
        await async_sync_llm_api(hass)

    async_register_admin_service(
        hass,
        DOMAIN,
        "update_settings",
        update_settings_service,
        _UPDATE_SETTINGS_SCHEMA,
    )

    async def refresh_links_service(call: ServiceCall) -> dict:
        """Re-read every radio-link provider (or the given layers) into the
        link store, for an automation that wants fresher data than the
        30-minute schedule. Returns a short per-network summary."""
        from .links.store import async_refresh

        snapshots = await async_refresh(hass, call.data.get("layers"))
        return {
            "snapshots": [
                {
                    "layer": s.layer,
                    "network": s.network,
                    "provider": s.provider,
                    "captured_at": s.captured_at,
                    "nodes": len(s.nodes),
                    "links": len(s.links),
                    "errors": s.errors,
                }
                for s in snapshots
            ]
        }

    async_register_admin_service(
        hass,
        DOMAIN,
        "refresh_links",
        refresh_links_service,
        vol.Schema(
            {
                vol.Optional("layers"): vol.All(
                    cv.ensure_list, [vol.In(("zigbee", "thread", "wifi", "bluetooth"))]
                )
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
