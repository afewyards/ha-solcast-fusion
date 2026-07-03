from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_AC_W,
    CONF_AZIMUTH,
    CONF_DAMP_AM,
    CONF_DAMP_PM,
    CONF_DC_W,
    CONF_DECAY_HALFLIFE_H,
    CONF_DECLINATION,
    CONF_DIFFUSE,
    CONF_EFFICIENCY,
    CONF_HORIZON_FILE,
    CONF_K_MAX,
    CONF_K_MIN,
    CONF_LAT,
    CONF_LON,
    CONF_OM_INTERVAL_MIN,
    CONF_SOLCAST_CAP,
    CONF_SOLCAST_KEY,
    CONF_SOLCAST_RESERVE,
    CONF_SOLCAST_SITE,
    DEFAULTS,
    DOMAIN,
)
from .solcast import (
    SolcastAuthError,
    SolcastBusyError,
    SolcastError,
    SolcastSiteError,
    fetch_sites,
    site_to_config,
)

_DECAY_DESC = {"suffix": "0 = flat-hold (no decay)"}


def _site_label(site: dict) -> str:
    name = site.get("name") or site.get("resource_id")
    cap = site.get("capacity") or site.get("capacity_dc")
    cap_str = f"{cap} kW" if cap else "?"
    return f"{name} — {cap_str}"


class SolcastFusionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._data: dict = {}
        self._sites: list[dict] = []
        self._reconfigure_entry = None

    async def async_step_user(self, user_input=None):
        return await self._async_key_step(user_input)

    async def async_step_reconfigure(self, user_input=None):
        self._reconfigure_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self._async_key_step(user_input)

    async def _async_key_step(self, user_input):
        errors: dict = {}
        current_key = ""
        if self._reconfigure_entry is not None:
            current_key = self._reconfigure_entry.data.get(CONF_SOLCAST_KEY, "")

        if user_input is not None:
            key = user_input[CONF_SOLCAST_KEY]
            session = async_get_clientsession(self.hass)
            try:
                sites = await fetch_sites(session, key)
            except SolcastAuthError:
                errors["base"] = "invalid_auth"
            except SolcastBusyError:
                errors["base"] = "solcast_busy"
            except SolcastError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                if not sites:
                    errors["base"] = "no_sites"
                else:
                    self._data[CONF_SOLCAST_KEY] = key
                    self._sites = sites
                    if len(sites) == 1:
                        return await self.async_step_site(
                            {CONF_SOLCAST_SITE: sites[0]["resource_id"]}
                        )
                    return await self.async_step_site()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_SOLCAST_KEY, default=current_key): str}
            ),
            errors=errors,
        )

    async def async_step_site(self, user_input=None):
        errors: dict = {}
        if user_input is not None:
            rid = user_input[CONF_SOLCAST_SITE]
            site = next((s for s in self._sites if s["resource_id"] == rid), None)
            if site is None:
                errors["base"] = "no_sites"
            else:
                try:
                    self._data.update(site_to_config(site))
                except SolcastSiteError:
                    errors["base"] = "invalid_site"
                else:
                    return await self.async_step_confirm()

        options = {s["resource_id"]: _site_label(s) for s in self._sites}
        return self.async_show_form(
            step_id="site",
            data_schema=vol.Schema({vol.Required(CONF_SOLCAST_SITE): vol.In(options)}),
            errors=errors,
        )

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            if self._reconfigure_entry is not None:
                new_data = {**self._reconfigure_entry.data, **self._data}
                if CONF_AC_W not in self._data:
                    new_data.pop(CONF_AC_W, None)
                return self.async_update_reload_and_abort(
                    self._reconfigure_entry, data=new_data
                )
            return self.async_create_entry(title="SolcastFusion", data=self._data)

        placeholders = {
            CONF_LAT: str(self._data[CONF_LAT]),
            CONF_LON: str(self._data[CONF_LON]),
            CONF_DECLINATION: str(self._data[CONF_DECLINATION]),
            CONF_AZIMUTH: str(self._data[CONF_AZIMUTH]),
            CONF_DC_W: str(self._data[CONF_DC_W]),
            CONF_AC_W: str(self._data.get(CONF_AC_W, "—")),
        }
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=placeholders,
        )

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry):
        return SolcastFusionOptionsFlow(config_entry)


def _options_schema(opts: dict) -> vol.Schema:
    def _d(key):
        return opts.get(key, DEFAULTS[key])

    return vol.Schema(
        {
            vol.Optional(CONF_HORIZON_FILE, default=opts.get(CONF_HORIZON_FILE, "")): str,
            vol.Optional(CONF_DIFFUSE, default=_d(CONF_DIFFUSE)): vol.All(
                vol.Coerce(float), vol.Range(0.0, 1.0)
            ),
            vol.Optional(CONF_K_MIN, default=_d(CONF_K_MIN)): vol.All(
                vol.Coerce(float), vol.Range(0.0, 5.0)
            ),
            vol.Optional(CONF_K_MAX, default=_d(CONF_K_MAX)): vol.All(
                vol.Coerce(float), vol.Range(0.0, 5.0)
            ),
            vol.Optional(
                CONF_DECAY_HALFLIFE_H,
                default=_d(CONF_DECAY_HALFLIFE_H),
                description=_DECAY_DESC,
            ): vol.All(vol.Coerce(float), vol.Range(0.0, 100.0)),
            vol.Optional(CONF_DAMP_AM, default=_d(CONF_DAMP_AM)): vol.All(
                vol.Coerce(float), vol.Range(0.0, 1.0)
            ),
            vol.Optional(CONF_DAMP_PM, default=_d(CONF_DAMP_PM)): vol.All(
                vol.Coerce(float), vol.Range(0.0, 1.0)
            ),
            vol.Optional(CONF_EFFICIENCY, default=_d(CONF_EFFICIENCY)): vol.All(
                vol.Coerce(float), vol.Range(0.0, 1.0)
            ),
            vol.Optional(CONF_OM_INTERVAL_MIN, default=_d(CONF_OM_INTERVAL_MIN)): vol.All(
                vol.Coerce(int), vol.Range(1, 60)
            ),
            vol.Optional(CONF_SOLCAST_CAP, default=_d(CONF_SOLCAST_CAP)): vol.All(
                vol.Coerce(int), vol.Range(1, 50)
            ),
            vol.Optional(CONF_SOLCAST_RESERVE, default=_d(CONF_SOLCAST_RESERVE)): vol.All(
                vol.Coerce(int), vol.Range(0, 50)
            ),
        }
    )


class SolcastFusionOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.config_entry.options),
        )
