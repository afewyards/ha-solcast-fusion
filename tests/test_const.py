from custom_components.ha_solcast_fusion import const


def test_domain_and_quota_defaults():
    assert const.DOMAIN == "ha_solcast_fusion"
    assert const.DEFAULTS[const.CONF_SOLCAST_CAP] == 10
    assert const.DEFAULTS[const.CONF_SOLCAST_RESERVE] == 0


def test_bias_clamp_defaults_retained():
    assert const.DEFAULTS[const.CONF_K_MIN] == 0.5
    assert const.DEFAULTS[const.CONF_K_MAX] == 2.0


def test_blend_and_horizon_defaults():
    assert const.DEFAULTS[const.CONF_W_MAX] == 0.9
    assert const.DEFAULTS[const.CONF_W_MIN] == 0.5
    assert const.DEFAULTS[const.CONF_H_SHOULDER] == 6.0
    assert const.DEFAULTS[const.CONF_H_FLOOR] == 0.18
