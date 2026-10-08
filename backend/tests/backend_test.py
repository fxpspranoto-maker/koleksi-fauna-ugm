import csv
import io
import os
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    session = requests.Session()
    session.created = []
    yield session
    for cid in session.created:
        session.delete(f"{API}/collections/{cid}")


def payload(number=None, **overrides):
    data = {
        "nomor_koleksi": number or f"TEST-{uuid.uuid4().hex[:10]}",
        "nama_ilmiah": "Panthera tigris", "nama_umum": "Harimau",
        "kelompok": "Mammalia", "jenis_koleksi": "Kerangka",
        "lokasi_asal": "Jawa", "kondisi_spesimen": "Baik",
        "osteologi_kelengkapan": "Lengkap", "bagian_tulang": "Tengkorak dan rangka",
    }
    data.update(overrides)
    return data


def create(client, data):
    response = client.post(f"{API}/collections", json=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nomor_koleksi"] == data["nomor_koleksi"]
    client.created.append(body["id"])
    return body


def test_health_and_stats(client):
    assert client.get(f"{API}/").status_code == 200
    body = client.get(f"{API}/stats").json()
    assert body["total"] >= 0
    assert all(group in body for group in ("Mammalia", "Aves", "Reptilia", "Amphibia", "Pisces", "Invertebrata"))


def test_crud_duplicate_and_filters(client):
    data = payload()
    item = create(client, data)
    fetched = client.get(f"{API}/collections/{item['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["bagian_tulang"] == "Tengkorak dan rangka"
    duplicate = client.post(f"{API}/collections", json=payload(data["nomor_koleksi"]))
    assert duplicate.status_code == 409
    assert "sudah digunakan" in duplicate.json()["detail"]
    filtered = client.get(f"{API}/collections", params={"q": "Harimau", "kelompok": "Mammalia", "jenis": "Kerangka"})
    assert filtered.status_code == 200
    assert any(row["id"] == item["id"] for row in filtered.json())
    changed = client.put(f"{API}/collections/{item['id']}", json=dict(data, nama_umum="Harimau Jawa"))
    assert changed.status_code == 200
    assert changed.json()["nama_umum"] == "Harimau Jawa"


def test_import_duplicate_skipping_and_exports(client):
    number = f"TEST-IMP-{uuid.uuid4().hex[:8]}"
    lines = io.StringIO()
    writer = csv.DictWriter(lines, fieldnames=["nomor_koleksi", "nama_ilmiah", "kelompok", "jenis_koleksi"])
    writer.writeheader()
    writer.writerow({"nomor_koleksi": number, "nama_ilmiah": "Orcinus orca", "kelompok": "Mammalia", "jenis_koleksi": "Spesimen utuh"})
    writer.writerow({"nomor_koleksi": number, "nama_ilmiah": "Orca duplicate", "kelompok": "Mammalia", "jenis_koleksi": "Spesimen utuh"})
    response = client.post(f"{API}/import", files={"file": ("data.csv", lines.getvalue().encode(), "text/csv")})
    assert response.status_code == 200
    assert response.json()["added"] == 1 and number in response.json()["duplicates"]
    rows = client.get(f"{API}/collections", params={"q": number}).json()
    assert len(rows) == 1
    client.created.append(rows[0]["id"])
    for extension, content_type in (("csv", "text/csv"), ("xlsx", "spreadsheet"), ("pdf", "application/pdf")):
        exported = client.get(f"{API}/export/{extension}")
        assert exported.status_code == 200
        assert content_type in exported.headers.get("content-type", "")
        assert len(exported.content) > 10


def test_photo_upload_and_missing_collection(client):
    item = create(client, payload())
    photo = client.post(f"{API}/collections/{item['id']}/photo", files={"file": ("specimen.png", b"fake-image", "image/png")})
    assert photo.status_code == 200
    assert photo.json()["foto_url"].startswith("/api/files/")
    image = client.get(f"{BASE_URL}{photo.json()['foto_url']}")
    assert image.status_code == 200 and image.content == b"fake-image"
    assert client.delete(f"{API}/collections/{item['id']}").status_code == 200
    assert client.get(f"{API}/collections/{item['id']}").status_code == 404
    assert client.post(f"{API}/collections/{item['id']}/photo", files={"file": ("x.jpg", b"x", "image/jpeg")}).status_code == 404
    client.created.remove(item["id"])