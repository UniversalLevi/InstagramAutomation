# TikTok API posting – simple setup

Your project is already configured with your **Client Key** and **Client Secret** in `config/accounts/my_account.yaml`. Follow these steps to finish and start posting via the API.

---

## Step 1: Add redirect URI in TikTok Developer Portal

1. Go to [TikTok for Developers](https://developers.tiktok.com/) → **My Apps** → open your app.
2. Open **Login Kit** (or **OAuth** / **Redirect URI** section).
3. Add this **exact** Redirect URI:
   ```text
   http://127.0.0.1:8765/callback
   ```
4. Save.

If your app only allows HTTPS redirects, say so and we can switch to using ngrok.

---

## Step 2: Get your access token (one time)

1. Open a terminal in the **Tiktok** folder:
   ```bash
   cd Tiktok
   ```
2. Install dependencies if you haven’t:
   ```bash
   pip install -r requirements.txt
   ```
3. Run:
   ```bash
   python get_tiktok_token.py
   ```
4. The script will print a long URL. **Open that URL in your browser.**
5. Log in to TikTok (the account you want to post from) and approve access.
6. You’ll be redirected to a “Success” page. Go back to the terminal – the script will have saved your `access_token` into `config/accounts/my_account.yaml` and printed “Done.”

If you use a different account config file (e.g. `config/accounts/my_channel.yaml`), run:
```bash
python get_tiktok_token.py my_channel
```

---

## Step 3: Use the same account in the app

The app is set to use account **my_account** (saved in `data/current_account.txt`).  
If you use a different account file (e.g. `my_channel`), run once: `python cli.py select my_channel`.

---

## Step 4: Post a video

1. Start the web app (from the **Tiktok** folder):
   ```bash
   python -m web.app
   ```
   or run your usual command.
2. Open the upload page, add a video, set caption/hashtags, and add to queue.
3. Click **Post** on that item (or let the scheduler run).

Posting will use the **TikTok API** (no phone or Appium). The first time may take a bit while the video uploads and TikTok processes it.

---

## Summary

| Step | What you do |
|------|------------------|
| 1 | In TikTok Developer Portal, add Redirect URI: `http://127.0.0.1:8765/callback` |
| 2 | Run `python get_tiktok_token.py`, open the printed URL, log in and approve |
| 3 | Ensure the app uses account `my_account` |
| 4 | Queue a video and post from the web UI (or scheduler) |

---

## Already done for you

- **Posting method** is set to **api** in `config/defaults.yaml`.
- **Account config** is in `config/accounts/my_account.yaml` with your Client Key and Client Secret; `access_token` is filled when you complete Step 2.

## If something fails

- **“Invalid redirect_uri”** – The URI in the portal must match exactly: `http://127.0.0.1:8765/callback` (no trailing slash, same port).
- **“No authorization code”** – Make sure you opened the URL the script printed and approved access; then wait for the redirect back to the script.
- **Post fails with “access_token invalid”** – Tokens expire (~24 h). Run `python get_tiktok_token.py` again to get a new token (you’ll need to approve in the browser again unless you add refresh logic).
