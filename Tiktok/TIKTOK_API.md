# TikTok Content Posting API – Setup

This project can post videos using **TikTok’s official Content Posting API** instead of device automation (Appium). No phone or emulator is required when using the API.

## How the TikTok API works

- **Content Posting API** has two flows:
  1. **Direct Post** – Video is published directly to the creator’s profile. Uses scope `video.publish`. Unaudited apps can only post as **private** (`SELF_ONLY`).
  2. **Inbox upload** – Video is sent to the creator’s TikTok inbox as a draft; they open the app and finish posting. Uses scope `video.upload`.

- **Flow (FILE_UPLOAD):**
  1. **Init** – `POST` to `/v2/post/publish/video/init/` (direct) or `/v2/post/publish/inbox/video/init/` (inbox) with video size and chunk info.
  2. **Upload** – `PUT` the video file to the returned `upload_url` (with `Content-Range`, `Content-Type: video/mp4`).
  3. **Status** – Poll `POST /v2/post/publish/status/fetch/` with `publish_id` until status is `PUBLISH_COMPLETE` or `FAILED`.

- **Auth:** You need a **user access token** (and optionally `open_id`) from TikTok OAuth. The token is valid ~24 hours; use `refresh_token` to get new access tokens for up to 365 days without asking the user again.

- **Limits:** 6 init requests per minute per access token; 30 status requests per minute. Unaudited clients can only post to private visibility.

References:
- [Content Posting API – Get started](https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content)
- [Upload video reference](https://developers.tiktok.com/doc/content-posting-api-reference-upload-video)
- [Direct Post reference](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- [OAuth & access token management](https://developers.tiktok.com/doc/oauth-user-access-token-management)

## 1. Create a TikTok app and get credentials

1. Go to [TikTok for Developers](https://developers.tiktok.com/).
2. Create an app and add the **Content Posting API** product.
3. Request the scopes you need:
   - **Direct Post:** `video.publish`
   - **Inbox upload only:** `video.upload`
4. Note your **Client Key** and **Client Secret** (in the app’s credentials section).

## 2. Get a user access token (OAuth)

You need the TikTok user (the account that will post) to authorize your app once:

1. **Authorization URL** (open in browser; replace `YOUR_CLIENT_KEY` and `YOUR_REDIRECT_URI`):

   ```
   https://www.tiktok.com/auth/authorize/?client_key=YOUR_CLIENT_KEY&scope=video.publish,video.upload&response_type=code&redirect_uri=YOUR_REDIRECT_URI&state=random_state
   ```

2. The user logs in and approves; TikTok redirects to your `redirect_uri` with a `code` in the query string.

3. **Exchange code for token** (replace placeholders):

   ```bash
   curl -X POST "https://open.tiktokapis.com/v2/oauth/token/" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "client_key=YOUR_CLIENT_KEY" \
     -d "client_secret=YOUR_CLIENT_SECRET" \
     -d "code=CODE_FROM_REDIRECT" \
     -d "grant_type=authorization_code" \
     -d "redirect_uri=YOUR_REDIRECT_URI"
   ```

4. Response includes `access_token`, `refresh_token`, `open_id`, `expires_in`. Store these for the account.

Your `redirect_uri` must be registered in the TikTok app settings (e.g. `http://localhost:5001/oauth/callback`). You can run a small Flask route that prints the `code` so you can paste it into the curl above, or implement a proper callback that saves the token.

## 3. Configure this project for API posting

1. **Use API as posting method**

   In `config/defaults.yaml` set:

   ```yaml
   posting:
     method: api
   ```

   Or override per account in `config/accounts/<account_id>.yaml`.

2. **Add TikTok API credentials for the account**

   In `config/accounts/<account_id>.yaml` (e.g. copy from `example.yaml` and fill):

   ```yaml
   account_id: my_account
   display_name: "My TikTok"

   tiktok_api:
     client_key: "your_client_key"
     client_secret: "your_client_secret"
     access_token: "user_access_token_from_oauth"
     refresh_token: "user_refresh_token"   # optional
     open_id: "user_open_id"               # optional
     post_mode: "direct"                   # "direct" or "inbox"
     privacy_level: "SELF_ONLY"            # SELF_ONLY | FOLLOWER_OF_CREATOR | MUTUAL_FOLLOW_FRIENDS | PUBLIC_TO_EVERYONE (audited only)
   ```

   - **post_mode**
     - `direct` – Publish directly to profile (scope `video.publish`). Unaudited apps are limited to private posts.
     - `inbox` – Send to creator’s inbox as draft (scope `video.upload`); they post from the app.
   - **privacy_level** – For direct post. Use `SELF_ONLY` until your app is audited; then you can use other options if the creator allows them.

3. **Install dependency**

   ```bash
   pip install -r requirements.txt   # includes requests
   ```

4. **Run as usual** – Queue videos via the web UI or scheduler; when `posting.method` is `api`, the app will use the TikTok API instead of Appium.

## 4. Refreshing the access token

Access tokens expire (e.g. after 24 hours). Use the refresh token:

```bash
curl -X POST "https://open.tiktokapis.com/v2/oauth/token/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_key=YOUR_CLIENT_KEY" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "refresh_token=USER_REFRESH_TOKEN" \
  -d "grant_type=refresh_token"
```

Update `access_token` (and optionally `refresh_token`) in the account config after each refresh. Automating refresh in this codebase is optional; you can add it in `tiktok_api_client` or a small script.

## 5. Switching back to device (Appium) posting

Set in config:

```yaml
posting:
  method: appium
```

Then posting will use the existing Appium flow (device/emulator and TikTok app) as before.
