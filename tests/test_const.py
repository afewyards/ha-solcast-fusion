from custom_components.ha_solcast_fusion import const


def test_domain_and_defaults():
    assert const.DOMAIN == "ha_solcast_fusion"
    assert const.DEFAULTS[const.CONF_DIFFUSE] == 0.15
    assert const.DEFAULTS[const.CONF_K_MIN] == 0.5
    assert const.DEFAULTS[const.CONF_K_MAX] == 2.0
    assert const.DEFAULTS[const.CONF_SOLCAST_CAP] == 8
    assert const.DEFAULTS[const.CONF_SOLCAST_RESERVE] == 2
