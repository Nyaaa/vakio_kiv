"""Constants for the Vakio Openair integration."""

# CONF consts
DOMAIN = "vakio_kiv"
CONF_PREFIX = "topic"
DEFAULT_PREFIX = "vakio"

# KIV
KIV_STATE_OFF = "off"
KIV_STATE_ON = "on"
KIV_MODE_MANUAL = "manual"
KIV_MODE_AUTO = "super_auto"

# Endpoints
GATE_ENDPOINT = "gate"
STATE_ENDPOINT = "state"
TEMP_ENDPOINT = "temp"
HUD_ENDPOINT = "hud"
MODE_ENDPOINT = "workmode"
ENDPOINTS = [GATE_ENDPOINT, STATE_ENDPOINT, TEMP_ENDPOINT, HUD_ENDPOINT]
