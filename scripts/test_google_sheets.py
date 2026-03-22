import os
from pathlib import Path
import pandas as pd
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH)

CREDS_FILE = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

print("CREDS_FILE =", CREDS_FILE)
print("SHEET_NAME =", SHEET_NAME)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_path = PROJECT_ROOT / CREDS_FILE

creds = Credentials.from_service_account_file(str(creds_path), scopes=scope)

client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

data = sheet.get_all_records()
df = pd.DataFrame(data)

print("Connection successful")
print(df.head())
