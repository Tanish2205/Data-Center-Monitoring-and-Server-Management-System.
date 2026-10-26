# Data Center Monitor

A simple Flask + SQLite project that monitors basic system stats
(CPU, RAM, disk, network) for the computer it's running on, and lets
you keep a list of other servers to ping and check.

## Features

- Login page (single admin account)
- Live dashboard with CPU / RAM / Disk usage bars and a chart
- Add / edit / delete servers, and ping them to check if they're up
- Automatic alerts when CPU/RAM/Disk usage gets too high
- Activity log of logins, server changes, pings, and alerts

## How to run it

1. Install the requirements:

   ```
   pip install -r requirements.txt
   ```

2. Start the app:

   ```
   python app.py
   ```

3. Open your browser to `http://localhost:5000`

4. Log in with:

   - Username: `admin`
   - Password: `admin123`

## Project structure

```
app.py              -> all the Flask routes
db.py                -> database setup + connection helper
monitor.py            -> reads CPU/RAM/disk/network stats with psutil
templates/            -> HTML pages (Jinja2)
static/css/style.css  -> styling
static/js/main.js     -> dashboard live updates + chart
```

## Notes

- The database file `datacenter.db` is created automatically the first
  time you run the app.
- Alert thresholds (warning/critical %) can be changed at the top of `app.py`.
