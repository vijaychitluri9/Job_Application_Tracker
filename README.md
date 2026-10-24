# Job Application Tracker
A Flask + SQLite app with registration/login, personal application management, reminders, and a Chart.js pie chart.

## Run on Windows PowerShell
From the directory containing `app.py`:
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py app.py
```
Open http://127.0.0.1:5000, then select **Create an account**.

Click **Load demo data** on the dashboard to populate example applications and the pie chart.

## Database note
The new app expects a `user_id` column in the applications table. If you have an older `jobs.db` from the earlier version, stop the server and back it up first. To start fresh, rename or move the old database file before running the updated app. Existing records in the old database are not automatically migrated.
Before deploying publicly, change `SECRET_KEY` and add CSRF protection, rate limiting, secure cookie settings, and a production server.
