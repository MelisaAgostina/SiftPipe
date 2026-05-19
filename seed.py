import requests

# Configuración base
BASE_URL = "http://localhost:8065/api/v4"
ADMIN_EMAIL = "test@mail.com" # user TestUser
ADMIN_PASS = "tommy290310"          # Cambiar por tu contraseña admin

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
    user_id = user_res.json().get("id")

    print("3. Creando equipo de prueba...")
    team_res = session.post(f"{BASE_URL}/teams", json=NEW_TEAM, headers=headers)
    team_id = team_res.json().get("id")

    print("4. Vinculando usuario al equipo...")
    session.post(f"{BASE_URL}/teams/{team_id}/members", json={"team_id": team_id, "user_id": user_id}, headers=headers)

    print("5. Creando canal...")
    NEW_CHANNEL["team_id"] = team_id
    channel_res = session.post(f"{BASE_URL}/channels", json=NEW_CHANNEL, headers=headers)
    channel_id = channel_res.json().get("id")

    print("6. Vinculando usuario al canal...")
    session.post(f"{BASE_URL}/channels/{channel_id}/members", json={"user_id": user_id}, headers=headers)

    print("7. Publicando post ficticio...")
    post_data = {"channel_id": channel_id, "message": MESSAGE}
    session.post(f"{BASE_URL}/posts", json=post_data, headers=headers)

    print("Seed script finalizado con éxito. Entorno listo para Playwright.")

if __name__ == "__main__":
    seed_mattermost()