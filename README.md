# 🌿 PROJECTREE - AI-Powered Project Discovery

An AI-driven platform for student project discovery, featuring personalized ML recommendations, interactive study guides, and an AI study assistant.

## 👥 Developers
* **Vasanthakumar S**
* **Suriya Prakash A**
* **Sanjai M**

---

## 🚀 Features
* 🔍 **Discovery Quiz:** ML-powered project recommendations based on student interest and skill level.
* 📖 **Expert Guides:** Beautifully styled masterclass tutorials generated dynamically using LLMs, complete with diagrams and printable PDF export.
* 🤖 **AI Study Assistant:** Context-aware floating chat widget assisting students step-by-step.
* 🌱 **Greenhouse (Dashboard):** Track progress, streak days, and user level.
* 🌍 **Global Forest Feed:** Share completed project trees with the community.
* 📁 **Portfolio Export:** Export all achievements and completed projects as a PDF portfolio.

---

## 🛠️ Local Setup Guide

### 1. Prerequisites
* Python 3.10+
* A PostgreSQL database (e.g., Supabase Postgres)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory and add the following keys:
```env
SECRET_KEY=your_secret_key
DATABASE_URL=postgresql+psycopg2://your_postgres_connection_string
GROQ_API_KEY=your_groq_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
```

### 4. Database Seeding
To initialize the database tables and populate the project data:
```bash
python load_csv_to_db.py
```

### 5. Run the Application
```bash
python app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## ☁️ Deployment (Vercel)
This project is configured to run serverless on Vercel. 
Ensure you configure the environment variables in your Vercel Dashboard, and deploy using the `api/index.py` serverless entrypoint.
