# SJ Cash Mini App (FLAT)

Owner: **@sjnd88**

All files in **one folder** — no nested `static/` or `webapp/`.

## Files (root)

```
main.py  bot.py  server.py  swiggy_api.py  storage.py  config.py
index.html  app.css  app.js  brand.jpg
requirements.txt  render.yaml  README.md
data/   ← auto-created, accounts saved here
```

## Render

1. Upload **every file** as service root (flat).
2. Build: `pip install -r requirements.txt`
3. Start: `python main.py`
4. Env:
   - `WEBAPP_URL=https://YOUR-SERVICE.onrender.com` **required**
   - `BOT_TOKEN=9230441788:AAEGUm94Mb4J7bn_kj7kJW6BJpEtErRHz2Q`
   - `ADMIN_IDS=5427735251`
   - `DATA_DIR=/var/data` (optional — use with Render Persistent Disk so data survives redeploy)

Data file: `data/accounts.json`  
Accounts **stay saved** until user deletes them in the Mini App.

## Telegram

- Menu button: **Open App**
- Buttons: **Open App** · **Open Mini App** · Owner @sjnd88

## Local

```bash
pip install -r requirements.txt
export WEBAPP_URL=https://xxxx.ngrok-free.app
python main.py
```
