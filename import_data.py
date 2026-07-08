import pandas as pd
import mysql.connector

# 1. Load your own dataset
df = pd.read_csv('my_projects.csv')

# 2. Connect to MySQL
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Care@123",  # <--- YOUR PASSWORD
    database="projectree_db"
)
cursor = db.cursor()

# 3. Clear old data
cursor.execute("TRUNCATE TABLE projects")

# 4. Insert your data
query = """INSERT INTO projects (title, description, interest, type, level, language,
           status, expected_output, duration_days, steps)
           VALUES (%s, %s, %s, %s, %s, %s, 'Available', %s, %s, %s)"""

for _, row in df.iterrows():
    cursor.execute(
        query,
        (row['title'],
         row['description'],
         row['interest'],
         row['type'],
         row['level'],
         row['language'],
         row['expected_output'],
         row['duration_days'],
         row['steps']))

db.commit()
print(
    f"Successfully trained the database with {len(df)} of your own projects!")
