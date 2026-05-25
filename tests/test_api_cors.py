from fastapi.testclient import TestClient

from apps.api import main as api_main


def test_default_cors_origins_preserve_local_dev_ports(monkeypatch):
    monkeypatch.delenv("NEUROWEAVE_CORS_ORIGINS", raising=False)

    assert api_main._cors_origins_from_env() == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]


def test_cors_origins_can_be_overridden_from_env(monkeypatch):
    monkeypatch.setenv(
        "NEUROWEAVE_CORS_ORIGINS",
        " http://localhost:3000,https://research.example.test ,,",
    )

    assert api_main._cors_origins_from_env() == [
        "http://localhost:3000",
        "https://research.example.test",
    ]


def test_empty_cors_origin_override_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("NEUROWEAVE_CORS_ORIGINS", " , ")

    assert api_main._cors_origins_from_env() == api_main.DEFAULT_CORS_ORIGINS


def test_localhost_cors_regex_is_opt_in(monkeypatch):
    monkeypatch.delenv("NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS", raising=False)
    assert api_main._cors_allow_origin_regex_from_env() is None

    monkeypatch.setenv("NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS", "true")
    assert (
        api_main._cors_allow_origin_regex_from_env()
        == api_main.LOCALHOST_CORS_REGEX
    )


def test_default_cors_preflight_allows_existing_vite_port():
    client = TestClient(api_main.app)

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_default_cors_preflight_rejects_unconfigured_vite_port():
    client = TestClient(api_main.app)

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5175",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
