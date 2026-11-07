
import os
import mysql.connector
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Connect to local XAMPP MySQL
mysql_db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="food_rescue"
)

# Connect to Neon PostgreSQL
neon_db = psycopg2.connect(os.getenv("DATABASE_URL"))

my_cursor = mysql_db.cursor(dictionary=True)
pg_cursor = neon_db.cursor()

tables = {
    "users": [
        "id", "name", "email", "password", "role"
    ],
    "donations": [
        "id", "donor_id", "food_name", "quantity",
        "location", "pickup_time", "status",
        "hours_since_prepared", "latitude",
        "longitude", "image_path", "image"
    ],
    "requests": [
        "id", "donation_id", "ngo_id", "status"
    ]
}

try:
    for table, columns in tables.items():

        column_names = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))

        my_cursor.execute(f"SELECT {column_names} FROM {table}")
        rows = my_cursor.fetchall()

        if rows:
            update_columns = [
                f"{col}=EXCLUDED.{col}"
                for col in columns if col != "id"
            ]

            update_sql = ", ".join(update_columns)

            query = f"""
                INSERT INTO {table} ({column_names})
                VALUES ({placeholders})
                ON CONFLICT (id)
                DO UPDATE SET {update_sql}
            """

            values = [
                tuple(row[col] for col in columns)
                for row in rows
            ]

            pg_cursor.executemany(query, values)

        print(f"{table}: {len(rows)} records transferred")

    # Reset ID sequences
    for table in tables:
        pg_cursor.execute(f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE(MAX(id), 1),
                MAX(id) IS NOT NULL
            )
            FROM {table}
        """)

    neon_db.commit()
    print("\nAll records transferred successfully!")

except Exception as error:
    neon_db.rollback()
    print("Migration failed:", error)

finally:
    my_cursor.close()
    pg_cursor.close()
    mysql_db.close()
    neon_db.close()
