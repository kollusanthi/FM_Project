
import os
import mysql.connector
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

try:
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD",""),
        database=os.getenv("DB_NAME")
    )

    cursor = connection.cursor()
    cursor.execute("SELECT DATABASE()")

    print("Database connected successfully!")
    print("Connected database:", cursor.fetchone()[0])

    cursor.close()
    connection.close()

except Exception as error:
    print("Database connection failed!")
    print("Error:", error)
