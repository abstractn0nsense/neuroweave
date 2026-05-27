from fastapi.testclient import TestClient

from apps.api.main import app


def test_health_reports_workers_and_data_directories():
    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["service"] == "neuroweave-api"
        assert payload["workers"] == {
            "preprocessing": True,
            "epoch": True,
            "erp": True,
            "batch": True,
        }
        assert set(payload["data_directories"]) == {
            "samples",
            "uploads",
            "runs",
            "templates",
            "batches",
            "processed",
            "epochs",
            "erp",
        }
