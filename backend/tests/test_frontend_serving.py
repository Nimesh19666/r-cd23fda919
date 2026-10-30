from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import mount_frontend


def make_client(build_dir: Path) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    assert mount_frontend(app, build_dir)
    return TestClient(app)


def make_build(tmp_path: Path) -> Path:
    build = tmp_path / "build"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<html>the app</html>", encoding="utf-8")
    (build / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return build


def test_root_serves_the_app(tmp_path: Path) -> None:
    client = make_client(make_build(tmp_path))
    assert "the app" in client.get("/").text


def test_assets_are_served(tmp_path: Path) -> None:
    client = make_client(make_build(tmp_path))
    assert client.get("/assets/app.js").text == "console.log(1)"


def test_unknown_page_falls_back_to_the_app(tmp_path: Path) -> None:
    client = make_client(make_build(tmp_path))
    assert "the app" in client.get("/accuracy").text


def test_api_routes_still_win(tmp_path: Path) -> None:
    client = make_client(make_build(tmp_path))
    assert client.get("/api/ping").json() == {"ok": "yes"}


def test_unknown_api_path_is_a_404_not_the_app(tmp_path: Path) -> None:
    client = make_client(make_build(tmp_path))
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert "the app" not in response.text


def test_files_outside_the_build_are_never_served(tmp_path: Path) -> None:
    client = make_client(make_build(tmp_path))
    for url in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
        assert "top secret" not in client.get(url).text


def test_missing_build_mounts_nothing(tmp_path: Path) -> None:
    assert mount_frontend(FastAPI(), tmp_path / "does-not-exist") is False
