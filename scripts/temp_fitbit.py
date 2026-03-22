import base64
import requests

client_id = "23V6Z7"
client_secret = "753f48fdba52524af12550d6ba665ebf"
redirect_uri = "http://localhost:8001/callback"
code = "f7d8fb436eaf3bf6c84ae20ebba2754f8931dec7"

basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

response = requests.post(
    "https://api.fitbit.com/oauth2/token",
    headers={
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    data={
        "client_id": client_id,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code,
    },
    timeout=30,
)

print(response.status_code)
print(response.text)

