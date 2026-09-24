import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = f"{os.getenv('MM_URL', 'http://localhost:8065')}/api/v4"
ADMIN_EMAIL = os.getenv("MM_ADMIN_EMAIL", "test@mail.com")
ADMIN_PASS = os.getenv("MM_ADMIN_PASS")  # never hardcode this      # Cambiar por tu contraseña admin

def _require_env(name):
    """Identifiers and credentials come from .env (or SSM on the deployed box), never
    from this file: B4/B7 log in with these same variables, so seeding and logging in
    can't drift apart (found live 2026-09-23: a hardcoded seed email differed from the
    box's MM_USERNAME, and B4's login failed with a bare timeout)."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"[seed] {name} is not set - it defines the seeded account/team/channel.")
    return value


# Datos ficticios a inyectar: identifiers/credentials from the environment,
# purely fictitious sample content (names, display labels, post text) stays here.
def _seed_data():
    new_user = {
        "email": _require_env("MM_USERNAME"),
        "username": _require_env("MM_SEED_USERNAME"),
        "password": _require_env("MM_PASSWORD"),
        "first_name": "Usuario",
        "last_name": "Prueba"
    }
    new_team = {
        "name": _require_env("MM_TEAM"),
        "display_name": "Equipo Tesina",
        "type": "O" # O = Open (Público)
    }
    new_channel = {
        "name": _require_env("MM_CHANNEL"),
        "display_name": "Canal de Análisis",
        "type": "O"
    }
    return new_user, new_team, new_channel


MESSAGE = "¡Hola! Este es un mensaje semilla inyectado por el orquestador Python."

def seed_mattermost():
    NEW_USER, NEW_TEAM, NEW_CHANNEL = _seed_data()
    session = requests.Session()

    print("1. Autenticando como Admin...")
    login_res = session.post(f"{BASE_URL}/users/login", json={"login_id": ADMIN_EMAIL, "password": ADMIN_PASS})
    login_res.raise_for_status()
    token = login_res.headers.get("Token")
    headers = {"Authorization": f"Bearer {token}"}

    print("2. Creando usuario no-admin...")
    user_res = session.post(f"{BASE_URL}/users", json=NEW_USER, headers=headers)
    user_res.raise_for_status()
    user_id = user_res.json().get("id")

    print("3. Creando equipo de prueba...")
    team_res = session.post(f"{BASE_URL}/teams", json=NEW_TEAM, headers=headers)
    team_res.raise_for_status()
    team_id = team_res.json().get("id")

    print("4. Vinculando usuario al equipo...")
    member_res = session.post(f"{BASE_URL}/teams/{team_id}/members", json={"team_id": team_id, "user_id": user_id}, headers=headers)
    member_res.raise_for_status()

    print("5. Creando canal...")
    NEW_CHANNEL["team_id"] = team_id
    channel_res = session.post(f"{BASE_URL}/channels", json=NEW_CHANNEL, headers=headers)
    channel_res.raise_for_status()
    channel_id = channel_res.json().get("id")

    print("6. Vinculando usuario al canal...")
    channel_member_res = session.post(f"{BASE_URL}/channels/{channel_id}/members", json={"user_id": user_id}, headers=headers)
    channel_member_res.raise_for_status()

    print("7. Publicando post ficticio...")
    post_data = {"channel_id": channel_id, "message": MESSAGE}
    post_res = session.post(f"{BASE_URL}/posts", json=post_data, headers=headers)
    post_res.raise_for_status()

    print("Seed script finalizado con éxito. Entorno listo para Playwright.")

if __name__ == "__main__":
    seed_mattermost()