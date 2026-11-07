"""Services for Spatial Context.

Both services are admin-only, like the WebSocket API: the map holds the
whole floor plan and every placed device, and a mesh refresh makes the
Zigbee network re-scan itself. A call with no user (an automation or
script) is allowed, the same rule as Home Assistant's own admin services.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import Unauthorized, UnknownUser

from .const import DOMAIN
from .export import async_get_map_data
from .zigbee_mesh import async_get_network_map


def _admin_only(
    hass: HomeAssistant, handler: Callable[[ServiceCall], Awaitable[Any]]
) -> Callable[[ServiceCall], Awaitable[Any]]:
    """The check `homeassistant.helpers.service.async_register_admin_service`
    makes, done here because that helper only takes `supports_response`
    from Home Assistant 2025.6, newer than this integration's minimum."""

    async def check_admin(call: ServiceCall) -> Any:
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            if user is None:
                raise UnknownUser(context=call.context)
            if not user.is_admin:
                raise Unauthorized(context=call.context)
        return await handler(call)

    return check_admin


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register services for the Spatial Context integration."""

    async def get_map_service(call: ServiceCall) -> dict:
        """Return the spatial map data."""
        return await async_get_map_data(hass)

    hass.services.async_register(
        DOMAIN,
        "get_map",
        _admin_only(hass, get_map_service),
        supports_response=SupportsResponse.ONLY,
    )

    async def refresh_zigbee_mesh_service(call: ServiceCall) -> None:
        """Force a fresh Zigbee mesh scan and populate the cache — meant to
        run from an automation (e.g. overnight) so the panel's own Load mesh
        click can serve an instant, pre-warmed cache instead of blocking for
        the 1-2+ minutes a real scan takes on a large mesh."""
        await async_get_network_map(hass, force_refresh=True)

    hass.services.async_register(
        DOMAIN,
        "refresh_zigbee_mesh",
        _admin_only(hass, refresh_zigbee_mesh_service),
    )
