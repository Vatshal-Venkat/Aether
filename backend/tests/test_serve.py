"""python -m scripts.serve — starts the backend on the configured port."""

from app.config import Settings
from scripts.serve import server_options


def test_server_options_use_the_configured_port():
    opts = server_options(Settings(_env_file=None, api_port=8001), reload=True)
    assert opts == {"app": "app.main:app", "host": "127.0.0.1", "port": 8001, "reload": True}


def test_port_can_be_overridden_on_the_command_line():
    assert server_options(Settings(_env_file=None, api_port=8001), reload=False, port=9000)["port"] == 9000
