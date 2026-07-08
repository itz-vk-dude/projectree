# 🌿 PROJECTREE - Full Setup Guide

## Prerequisites
- Python 3.9+
- MySQL running with database `projectree_db`
- DB credentials: root / M..sanjai@2546

## Step-by-Step Setup

### 1. Install dependencies
```
pip install -r requirements.txt
```

### 2. Setup the database
Open MySQL and run:
```sql
CREATE DATABASE IF NOT EXISTS projectree_db;
```
Then import the SQL file:
```
mysql -u root -p projectree_db < projects_setup.sql
```

### 3. (Optional) Load CSV data
```
python load_csv_to_db.py
```

### 4. Run the app
```
python app.py
```

### 5. Open browser
Go to: http://127.0.0.1:5000

## Features
- 🔍 Discovery Quiz (ML-powered project recommender)
- 🤖 AI Project Idea Generator
- 💬 AI Career Chatbot (Groq Llama-3)
- 🌱 Personal Greenhouse (Dashboard)
- 📁 Portfolio Export
- 🌍 Global Forest Feed
