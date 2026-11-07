import os
import psycopg2
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# Connect to Neon database
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# Find old image filenames
cur.execute("""
    SELECT DISTINCT image_path
    FROM donations
    WHERE image_path IS NOT NULL
      AND image_path <> ''
      AND image_path NOT LIKE 'https://res.cloudinary.com/%'
""")

old_images = cur.fetchall()

for row in old_images:
    old_path = row[0]
    filename = os.path.basename(old_path)
    local_path = os.path.join("static", "uploads", filename)

    if not os.path.exists(local_path):
        print("Image file not found:", filename)
        continue

    try:
        result = cloudinary.uploader.upload(
            local_path,
            folder="food_rescue_connect"
        )

        image_url = result["secure_url"]

        cur.execute("""
            UPDATE donations
            SET image_path = %s
            WHERE image_path = %s
        """, (image_url, old_path))

        conn.commit()
        print("Uploaded successfully:", filename)

    except Exception as e:
        conn.rollback()
        print("Upload failed:", filename, e)

cur.close()
conn.close()

print("Old image upload process completed!")