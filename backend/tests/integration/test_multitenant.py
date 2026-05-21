"""Cross-tenant access tests — user A must not see user B's data."""


def _create_profile(client, headers, name: str = "Default") -> str:
    r = client.post("/api/v1/profiles", headers=headers, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_profile_isolated_by_user(client, auth_a, auth_b):
    pa = _create_profile(client, auth_a, "Perfil A")
    pb = _create_profile(client, auth_b, "Perfil B")

    # A cannot read B's profile
    r = client.get(f"/api/v1/profiles/{pb}", headers=auth_a)
    assert r.status_code == 404

    # A's profile is visible to A
    r = client.get(f"/api/v1/profiles/{pa}", headers=auth_a)
    assert r.status_code == 200
    assert r.json()["name"] == "Perfil A"

    # Listing is scoped
    r = client.get("/api/v1/profiles", headers=auth_a)
    assert all(p["id"] != pb for p in r.json())


def test_criteria_nested_under_profile_isolated(client, auth_a, auth_b):
    pa = _create_profile(client, auth_a, "Perfil A")
    r = client.post(
        f"/api/v1/profiles/{pa}/criteria",
        headers=auth_a,
        json={
            "name": "Senior HRBP CABA",
            "keywords": ["hrbp"],
            "locations": ["CABA"],
            "portals_enabled": ["bumeran"],
        },
    )
    assert r.status_code == 201, r.text
    crit_id = r.json()["id"]

    # B does not see it on the flat /criteria endpoint
    r = client.get("/api/v1/criteria", headers=auth_b)
    assert r.status_code == 200
    assert all(c["id"] != crit_id for c in r.json())

    # B cannot update / delete it
    assert (
        client.put(
            f"/api/v1/criteria/{crit_id}", headers=auth_b, json={"name": "hacked"}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/criteria/{crit_id}", headers=auth_b).status_code == 404


def test_admin_endpoints_forbidden_for_user(client, auth_a):
    r = client.get("/api/v1/admin/users", headers=auth_a)
    assert r.status_code == 403


def test_admin_can_list_users(client, auth_admin, user_a, user_b, admin):
    r = client.get("/api/v1/admin/users", headers=auth_admin)
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert {user_a.email, user_b.email, admin.email}.issubset(emails)
