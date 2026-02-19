# Autopost

Instagram **warm-up** (account conditioning) on Android + **posting queue** via a web UI. You log in to Instagram once manually; the tool does not log in or post for you automatically—it assists with warm-up and lets you queue/schedule posts from the web app.

---

## What it does

- **Warm-up**: Runs light, human-like activity on your Android device (via Appium) to condition the account. One session per day; no automated login.
- **Posting**: Web interface to upload media (photos, videos, reels, carousels), add captions, and manage a queue. Actual posting is triggered from the app when you’re ready.

---

## Requirements

- **Python 3.9+**
- **Node.js** (for Appium; 20.x LTS or newer)
- **Appium 2.x** + **UiAutomator2** driver
- **Android** device or emulator with Instagram installed; log in once manually
- **ADB** (device visible in `adb devices`)

---

## Appium & Android Studio emulator setup

### 1. Android Studio & emulator

- **Install [Android Studio](https://developer.android.com/studio)**.
- Open **SDK Manager** (e.g. **More Actions** → **SDK Manager** from welcome screen, or **File** → **Settings** → **Languages & Frameworks** → **Android SDK**). Install:
  - **Android SDK Platform** (e.g. API 34)
  - **Android SDK Platform-Tools** (includes `adb`)
- **Create an AVD (emulator):** **Device Manager** → **Create Device** → pick a device → pick a system image (e.g. API 34) → finish. Start the AVD so the emulator is running.
- **Set environment variables** (Windows: System Properties → Environment Variables):
  - `ANDROID_HOME` = your Android SDK path (e.g. `C:\Users\<you>\AppData\Local\Android\Sdk`)
  - Add to **Path**: `%ANDROID_HOME%\platform-tools` (so `adb` works in any terminal)
- **Check:** in a new terminal run `adb devices`. Your emulator should appear (e.g. `emulator-5554`).

### 2. Java JDK

- Appium needs **Java (JDK 17+)**. Install [Eclipse Temurin](https://adoptium.net/) or use the JDK bundled with Android Studio.
- Set `JAVA_HOME` to the JDK install folder (e.g. `C:\Program Files\Eclipse Adoptium\jdk-17.x.x-hotspot`).

### 3. Appium 2.x + UiAutomator2

- **Node.js:** install from [nodejs.org](https://nodejs.org/) (LTS).
- **Install Appium and the Android driver:**
  ```bash
  npm install -g appium
  appium driver install uiautomator2
  ```
- **Check:** run `appium` in a terminal; you should see the Appium server start (default: `http://127.0.0.1:4723`).

### 4. Instagram on the emulator

- Install the **Instagram** APK on the emulator (drag APK onto the emulator window, or use **Google Play** if the AVD has Play Services). **Log in once manually**; this project does not automate login.

---

## Setup (this project)

1. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the emulator** (Android Studio Device Manager) and **start Appium** in a separate terminal:
   ```bash
   appium
   ```

3. **Configure account**
   - Copy `config/accounts/example.yaml` to `config/accounts/default.yaml` (or e.g. `myaccount.yaml`).
   - Set `device.adb_serial` to the value from `adb devices` (e.g. `emulator-5554`).

---

## How to use

**CLI (from project root)**

| Action | Command |
|--------|--------|
| Interactive menu | `python cli.py` |
| Start warm-up | `python cli.py start [account_id]` |
| Status | `python cli.py status [account_id]` |
| Stop session | `python cli.py stop` |
| List accounts | `python cli.py list` |
| Select default account | `python cli.py select <account_id>` |

**Web interface (posting queue)**

- From the menu: run `python cli.py` → choose option **8** (Launch Web Interface), or run:
  ```bash
  python -m web.app
  ```
- Open **http://127.0.0.1:5000** in your browser to upload media, edit captions, and manage the queue.

---

## Summary

- One warm-up session per day; daily limits apply (see config/plan).
- No automated login: always log in to Instagram yourself first.
- Posting is managed via the web UI; the app helps you queue and schedule, not auto-post without you.
