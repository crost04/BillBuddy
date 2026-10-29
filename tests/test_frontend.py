"""Tests that the web app is served next to the API."""

import json

import pytest


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>BillBuddy</title>" in response.text


@pytest.mark.parametrize("path", ["/styles.css", "/js/app.js", "/sw.js", "/icons/icon-192.png", "/icons/icon-512.png"])
def test_static_files_are_served(client, path):
    assert client.get(path).status_code == 200


def test_manifest_makes_the_app_installable(client):
    manifest = json.loads(client.get("/manifest.json").text)
    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} >= {"192x192", "512x512"}


def test_api_still_works_next_to_the_frontend(client):
    assert client.get("/api/categories").status_code == 200
    assert client.get("/api/does-not-exist").status_code == 404
