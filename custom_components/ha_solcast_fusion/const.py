DOMAIN = "ha_solcast_fusion"

CONF_LAT = "latitude"
CONF_LON = "longitude"
CONF_DECLINATION = "declination"
CONF_AZIMUTH = "azimuth"
CONF_DC_W = "dc_w"
CONF_AC_W = "ac_w"
CONF_DAMP_AM = "damp_am"
CONF_DAMP_PM = "damp_pm"
CONF_EFFICIENCY = "efficiency"
CONF_SOLCAST_KEY = "solcast_key"
CONF_SOLCAST_SITE = "solcast_site"
CONF_HORIZON_FILE = "horizon_file"
CONF_DIFFUSE = "diffuse"
CONF_K_MIN = "k_min"
CONF_K_MAX = "k_max"
CONF_DECAY_HALFLIFE_H = "decay_halflife_h"
CONF_OM_INTERVAL_MIN = "om_interval_min"
CONF_SOLCAST_CAP = "solcast_cap"
CONF_SOLCAST_RESERVE = "solcast_reserve"
CONF_SETUP_QUOTA_CALLS = "setup_quota_calls"
CONF_W_MAX = "w_max"
CONF_W_MIN = "w_min"
CONF_H_SHOULDER = "h_shoulder"
CONF_H_FLOOR = "h_floor"

DEFAULTS = {
    CONF_DIFFUSE: 0.15,
    CONF_K_MIN: 0.5,
    CONF_K_MAX: 2.0,
    CONF_W_MAX: 0.9,
    CONF_W_MIN: 0.5,
    CONF_H_SHOULDER: 6.0,
    CONF_H_FLOOR: 0.18,
    CONF_DECAY_HALFLIFE_H: 2,
    CONF_OM_INTERVAL_MIN: 20,
    CONF_SOLCAST_CAP: 10,
    CONF_SOLCAST_RESERVE: 0,
    CONF_DAMP_AM: 0.0,
    CONF_DAMP_PM: 0.0,
    CONF_EFFICIENCY: 0.93,
}
