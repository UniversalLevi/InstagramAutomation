# Instagram Warm-Up Automation

Account conditioning and assistance only. **No automated login; no auto-posting.** Posting is manual. This system behaves like a lazy human, not a growth bot.

## Requirements

- Python 3.9+
- Appium server (run separately, e.g. `appium`)
- Android device or emulator with Instagram installed; **log in once manually**, then run automation
- ADB connected to device (`adb devices`)

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Start Appium server: `appium`
3. Connect device/emulator and install Instagram; log in to your account **manually**
4. Copy `config/accounts/example.yaml` to `config/accounts/default.yaml` (or your account id) and set `device.adb_serial` (e.g. from `adb devices`)

## Usage

- **Start warm-up**: `python cli.py start [account_id]` (default account_id is `default`)
- **Status**: `python cli.py status [account_id]`
- **Stop current session**: `python cli.py stop`
- **List accounts**: `python cli.py list`

One session per day; daily limits apply (see plan). No automated login.
