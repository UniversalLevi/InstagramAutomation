# How to Use This System

This project supports **two ways** to post to TikTok:

1. **TikTok Content Posting API** – No device needed. Uses your app’s Client Key/Secret and a user access token from OAuth.
2. **Appium (device automation)** – Uses an Android device/emulator and the TikTok app; you tap through the app via automation.

Your **TikTok Developer Portal** app (e.g. TikTok_Autopost / tiktokAutomation) is used **only for API posting**. The Client Key and Client Secret from the portal are not used when posting via Appium.

---

## Option A: Posting via TikTok API (no device)

**When to use:** You want to post without a phone/emulator. Good for scheduled posts from a server.

### 1. Developer Portal (you already have this)

- **Client Key** and **Client Secret** – In your app’s Credentials (e.g. Sandbox).
- **Redirect URI** – Must match exactly what you use in OAuth (e.g. your ngrok URL or `http://localhost:5001/oauth/callback`).
- **Content Posting API** – Enable **Direct Post** and/or **Upload to TikTok** (inbox).
- **Scopes** – At least `video.publish` (direct) and/or `video.upload` (inbox).
- **Sandbox** – Add the TikTok username(s) that are allowed to test (e.g. `user166800682`).

### 2. Get a user access token (one-time per account)

**Easiest: use the app (no ngrok, no curl).**

1. **Add this Redirect URI in the Developer Portal** (Login Kit → Redirect URI):
   ```
   http://127.0.0.1:5001/oauth/callback
   ```
   Save/Apply. No ngrok needed.

2. **Start the Web Interface** (CLI option 6). Open http://127.0.0.1:5001 in your browser.

3. **Click “Get TikTok API token”** on the Dashboard. You’ll be sent to TikTok to log in.

4. **Log in with your TikTok account** (for Sandbox, use an account added as Target User) and click **Authorize**.

5. You’ll be redirected back to the app. The app **exchanges the code for a token and saves it** to your account config. You’ll see “Access token saved. You can use API posting now.” No manual curl needed.

6. **API posting** – Ensure `config/defaults.yaml` has `posting.method: api`. Your `config/accounts/default.yaml` already has `client_key` and `client_secret`; the app fills in `access_token` (and `refresh_token`, `open_id`) after step 5.

Access tokens expire in about 24 hours; use the refresh token to get new ones (see [TIKTOK_API.md](TIKTOK_API.md)).

### 3. Configure this project for API

1. In **`config/defaults.yaml`** set:

   ```yaml
   posting:
     method: api
   ```

2. In **`config/accounts/default.yaml`** (or create it from `config/accounts/example.yaml`) add:

   ```yaml
   account_id: default
   display_name: "My TikTok"

   tiktok_api:
     client_key: "YOUR_CLIENT_KEY"        # from Developer Portal
     client_secret: "YOUR_CLIENT_SECRET"  # from Developer Portal
     access_token: "USER_ACCESS_TOKEN"     # from step 2 above
     refresh_token: "USER_REFRESH_TOKEN"  # optional
     open_id: "USER_OPEN_ID"              # optional
     post_mode: "direct"                  # "direct" or "inbox"
     privacy_level: "SELF_ONLY"           # required for unaudited apps
   ```

3. Run the app: queue videos via the **Web Interface** (option 6 in CLI) or scheduler. Posting will use the API; no device is needed.

Full API details: [TIKTOK_API.md](TIKTOK_API.md) and [SETUP_API.md](SETUP_API.md).

**Troubleshooting the auth page**

- **`POST ... mcs.tiktokw.us ... net::ERR_BLOCKED_BY_CLIENT`** or **`monitor_browser/collect ... ERR_BLOCKED_BY_CLIENT`** – Your browser or an extension (ad blocker, privacy tool) is blocking TikTok’s requests. Open the auth URL in **Incognito/Private mode** with extensions disabled, or whitelist `tiktok.com` in your ad blocker. The OAuth page can still work; if the “Authorize” button doesn’t work, try Incognito.
- **Content Security Policy / script blocked** – These come from TikTok’s page; you can’t fix them. Ignore unless the page never loads.
- **Redirect URI mismatch** – If TikTok says redirect_uri is wrong, the value in the URL must match the Developer Portal exactly (e.g. `https://c9e9-159-26-119-230.ngrok-free.app` with no trailing path or `?state=...`).

---

## Option B: Posting via Appium (device/emulator)

**When to use:** You prefer (or need) the real TikTok app on an Android device/emulator.

1. In **`config/defaults.yaml`** set:

   ```yaml
   posting:
     method: appium
   ```

2. Install and open the TikTok app on the device; log in once manually.
3. Start Appium, connect the device, then run this project (CLI or Web Interface). Posting will drive the app via automation.

---

## Web Interface and cleanup

- **Launch Web Interface:** From the CLI main menu, choose **6. Launch Web Interface (Posting Manager)**. It runs at `http://127.0.0.1:5001`.
- **Upload / Queue / Post:** Use the web UI to upload videos, add to queue, and post now or on schedule.
- **Debug file cleanup:** While the web app is running, a **scheduled job runs every 2 minutes** and deletes captured debug files from the project folder:
  - `post_stuck_*.txt`, `post_stuck_*.png`
  - `post_failed_*.png`
  - `post_debug_screen.txt`, `post_debug_screen.png`  
  These are created when posting gets stuck or fails (Appium flow). They are removed automatically so the folder does not fill up; no action needed from you.

---

## Summary: what you need to do

| Goal | What to do |
|------|------------|
| **Use API posting** | Set `posting.method: api`, add `tiktok_api` (client_key, client_secret, access_token, etc.) to your account config, get access_token via OAuth once. |
| **Use device posting** | Set `posting.method: appium`, run Appium + device, log in once in the TikTok app. |
| **Cleanup stuck/failed screenshots** | Nothing. With the Web Interface running, cleanup runs every 2 minutes. |
| **Developer Portal** | Only required for API posting. Keep Client Key/Secret and Redirect URI correct; add sandbox users for testing. |
