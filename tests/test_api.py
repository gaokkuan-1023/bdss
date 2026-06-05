"""api_server pytest 测试"""
import json
import pytest
from api_server import app, CONFIG


@pytest.fixture
def client():
    CONFIG["token"] = None
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        data = json.loads(resp.data)
        assert data["success"] is True
        assert data["data"]["status"] == "ok"


class TestIndex:
    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"BDSS" in resp.data


class TestSearch:
    def test_empty_body(self, client):
        resp = client.post("/api/search", json={})
        data = json.loads(resp.data)
        assert resp.status_code == 400
        assert "不能为空" in data["error"]
    
    def test_non_json(self, client):
        resp = client.post("/api/search", data="not json", content_type="text/plain")
        data = json.loads(resp.data)
        assert data["success"] is False
    
    def test_empty_company(self, client):
        resp = client.post("/api/search", json={"company": ""})
        data = json.loads(resp.data)
        assert resp.status_code == 400


class TestBatch:
    def test_empty_companies(self, client):
        resp = client.post("/api/search/batch", json={"companies": []})
        data = json.loads(resp.data)
        assert data["success"] is False


class TestAuth:
    def test_disabled(self, client):
        CONFIG["token"] = None
        resp = client.get("/api/health")
        assert resp.status_code == 200
    
    def test_no_token_rejected(self, client):
        CONFIG["token"] = "secret123"
        resp = client.post("/api/search", json={"company": "test"})
        assert resp.status_code == 401
        CONFIG["token"] = None
    
    def test_wrong_token(self, client):
        CONFIG["token"] = "secret123"
        resp = client.post("/api/search", json={"company": "test"},
                          headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401
        CONFIG["token"] = None
    
    def test_correct_token(self, client):
        CONFIG["token"] = "secret123"
        resp = client.post("/api/search", json={"company": ""},
                          headers={"Authorization": "Bearer secret123"})
        # company为空返回400而非401
        assert resp.status_code == 400
        CONFIG["token"] = None
