import requests
from dotenv import load_dotenv
load_dotenv()
import os

BASE_URL = "http://localhost:8065/api/v4"
ADMIN_EMAIL = os.getenv("MM_ADMIN_EMAIL", "test@mail.com")
ADMIN_PASS = os.getenv("MM_ADMIN_PASS")  # never hardcode this      # Cambiar por tu contraseña admin

# Datos ficticios a inyectar
NEW_USER = {
    "email": "victima@test.com",
    "username": "usuario_test",
    "password": "Password123!",
    "first_name": "Usuario",
    "last_name": "Prueba"
}
NEW_TEAM = {
    "name": "equipo-tesina",
    "display_name": "Equipo Tesina",
    "type": "O" # O = Open (Público)
}
NEW_CHANNEL = {
    "name": "canal-analisis",
    "display_name": "Canal de Análisis",
    "type": "O"
}
MESSAGE = "¡Hola! Este es un mensaje semilla inyectado por el orquestador Python."

def seed_mattermost():
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