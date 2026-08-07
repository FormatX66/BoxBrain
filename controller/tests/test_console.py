from fastapi.testclient import TestClient

from boxbrain_controller.app import create_app


def test_console_is_available_at_root_and_console_path():
    client = TestClient(create_app())

    for path in ("/", "/console"):
        response = client.get(path)
        assert response.status_code == 200
        assert "BOXBRAIN ONE" in response.text
        assert "Universal Control Console" in response.text
        assert "/api/v1/remote-targets" not in response.text
        assert "remote-targets" in response.text
