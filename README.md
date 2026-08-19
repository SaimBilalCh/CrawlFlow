# ClipFlow: Download Videos from Facebook, TikTok, and YouTube & Upload to Google Drive

ClipFlow is a simple bot for downloading videos from **Facebook, TikTok, and YouTube** based on your configured search queries and uploading the downloaded videos to a selected Google Drive folder.

> **Important:** Search results are not guaranteed to be perfect. The bot may occasionally download videos that do not exactly match your intended query. Always review the downloaded videos and perform manual verification when necessary.

## Setup Instructions

### 1. Create a Virtual Environment

First, create a Python virtual environment in the project root:

```bash
python -m venv venv
```

### 2. Activate the Virtual Environment

**Windows:**

```bash
venv/Scripts/activate
```

or:

```bash
venv/Scripts/activate.bat
```

If necessary, switch to Command Prompt (`cmd`) first and run the command there.

**Linux:**

```bash
source .venv/bin/activate
```

### 3. Create the Required Folders and `.env` File

Create the following folders in the project root:

```text
cookies/
credentials/
logs/
metadata/
```

Also create a `.env` file in the project root.

Your project structure should initially look similar to:

```text
project-root/
│
├── cookies/
├── credentials/
├── logs/
├── metadata/
├── .env
└── ...
```

### 4. Create the Required Files

Inside the `cookies` folder, create these three files:

```text
facebook_cookies.txt
tiktok_cookies.txt
youtube_cookies.txt
```

Inside the `credentials` folder, add the `credentials.json` file downloaded from Google Cloud Console (see below). The `token.json` file is generated automatically the first time the bot authenticates — you do not need to create it manually.

The remaining files inside `logs/` and `metadata/` will be generated automatically by the bot as the process runs.

#### Get `credentials.json` from Google Cloud Console

`credentials.json` is your Google OAuth client file. It is **not** created manually — it is downloaded from Google Cloud Console. To get it:

1. Go to the [Google Cloud Console](https://console.cloud.google.com) and sign in with your Google account.
2. Create a new project (or select an existing one) using the project dropdown at the top of the page.
3. Enable the **Google Drive API**:
   - Go to **APIs & Services → Library**.
   - Search for "Google Drive API".
   - Click **Google Drive API**, then click **Enable**.
4. Create an OAuth client ID:
   - Go to **APIs & Services → Credentials**.
   - Click **+ Create Credentials** and select **OAuth client ID**.
   - If prompted to configure the consent screen, click **Configure consent screen**, choose **External**, fill in the required fields (app name, email), and save.
   - Set **Application type** to **Desktop app**.
   - Click **Create**.
5. Download the JSON file:
   - On the next screen, click **Download JSON** next to the newly created client.
   - Rename the downloaded file to `credentials.json`.
6. Place `credentials.json` in the `credentials/` folder of this project.

> **Note:** On first run, the bot opens a browser to let you sign in with your Google account and automatically generates `credentials/token.json`. If you see a "Google hasn't verified this app" warning, click **Advanced → Go to {your project} (unsafe)** — this is normal for personal-use OAuth apps.

> **Security Warning:** `credentials.json` and `token.json` grant access to your Google Drive. Treat them like passwords. Never commit them, upload them publicly, or share them with anyone.

### 5. Get Cookies for Facebook, TikTok, and YouTube

The bot can use browser cookies from your **own logged-in accounts** when a platform requires an authenticated browser session.

You can use the following browser extensions:

* **Mozilla Firefox:** `cookies.txt` by Lennon Hill. It exports cookies in the Netscape HTTP Cookie File format. [Firefox cookies.txt extension](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/?utm_source=chatgpt.com)
* **Google Chrome:** `Get cookies.txt LOCALLY`. It supports exporting cookies in Netscape `cookies.txt` format. [Chrome Get cookies.txt LOCALLY extension](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc?hl=en&utm_source=chatgpt.com)

#### Mozilla Firefox

1. Open Firefox.
2. Open the Firefox Add-ons page.
3. Search for **cookies.txt** by Lennon Hill.
4. Select **Add to Firefox** and confirm the installation. Firefox's official add-on system will show the permissions requested by the extension.
5. Log in to your own **Facebook, TikTok, or YouTube** account in Firefox.
6. Open the website for which you want to export cookies.
7. Make sure you are logged in to the correct account.
8. Click the **cookies.txt** extension from the Firefox toolbar.
9. Use the extension's export/copy function to obtain the cookies for the current website. The current version supports copying the cookies file to the clipboard.
10. Open the corresponding file in your project's `cookies` folder.
11. Paste the exported cookie data into the appropriate file.

Use the following mapping:

```text
Facebook  → cookies/facebook_cookies.txt
TikTok    → cookies/tiktok_cookies.txt
YouTube   → cookies/youtube_cookies.txt
```

12. Save the file.
13. Repeat the same process for the other platforms.

#### Google Chrome

1. Open Google Chrome.
2. Open the Chrome Web Store.
3. Search for **Get cookies.txt LOCALLY**.
4. Select the extension and click **Add to Chrome**.
5. Confirm the installation when Chrome asks for permission. Google's official instructions recommend installing extensions through the Chrome Web Store and reviewing the permissions requested.
6. Log in to your own **Facebook, TikTok, or YouTube** account.
7. Open the corresponding website in Chrome.
8. Make sure you are logged in to the correct account.
9. Click the **Extensions** button in the Chrome toolbar.
10. Open **Get cookies.txt LOCALLY**.
11. Use its export/copy function to obtain the cookies for the current website. The extension supports Netscape `cookies.txt` format, which is the format required by this setup.
12. Open the corresponding file in your project's `cookies` folder.
13. Paste the exported cookie data into the appropriate file.

Use the following mapping:

```text
Facebook  → cookies/facebook_cookies.txt
TikTok    → cookies/tiktok_cookies.txt
YouTube   → cookies/youtube_cookies.txt
```

14. Save the file.
15. Repeat the process for the other platforms.

> **Security Warning:** Browser cookies can contain active login-session information. Treat these files like passwords. Only export cookies from accounts you own or are authorized to use. Never share them, upload them publicly, commit them to GitHub, or send them to anyone else.

### 6. Configure Categories and Search Queries

All categories and their search queries are defined in **`categories.json`** — a
single configuration file shared by the automated bot (`main.py`) and the bulk
upload GUI (`bulk_upload_gui.py`). You do **not** need to edit any Python code
to customize the content the bot collects.

The file is organized into two groups — `real` and `fake`. Each category
supports the following fields:

| Field           | Purpose                                                                   |
| --------------- | ------------------------------------------------------------------------- |
| `queries`       | Search terms used by the automated bot. One query is picked at random per category for each batch. |
| `hashtags`      | The bot occasionally appends one of these to the selected query.          |
| `platforms`     | Reserved for future use — the bot currently searches **YouTube** only.    |
| `short_queries` | Reserved for future use — not used by the bot yet.                        |

Example:

```json
{
  "real": {
    "vlog": {
      "queries": ["person vlog face", "daily vlog person"],
      "platforms": ["youtube"],
      "hashtags": ["#vlog", "#dailyvlog"],
      "short_queries": ["person vlog shorts"]
    }
  },
  "fake": {
    "face_swap": {
      "queries": ["deepfake face swap person", "AI face swap person"],
      "platforms": ["youtube"],
      "hashtags": ["#deepfake", "#faceswap"],
      "short_queries": ["person deepfake shorts"]
    }
  }
}
```

* **Add a category:** copy an existing category and give it a new key (e.g. `"gaming"`).
  It will automatically appear in the GUI's category dropdown and be used by the
  automated bot for searches.
* **Edit search queries:** change the `queries` list (and optionally `hashtags`)
  to match the type of videos you want the bot to find, download, and upload to
  Google Drive. If a query does not already contain the words "person" or "face",
  the bot appends them automatically.
* **Remove a category:** delete its entry from `categories.json`.

#### Categories in the Bulk Upload GUI

The GUI (`bulk_upload_gui.py`) does **not** run searches — you paste video links
manually. It loads the category **names** from `categories.json` to populate its
category dropdown, filtering by the selected label (`real` or `fake`). The field
is editable, so you can also type a custom category name.

> **Note:** Do not rely solely on the search results. Automated search can make
> mistakes. Thoroughly review the downloaded videos to ensure they match your
> intended content.

### 7. Create a Google Drive Folder

Create a new folder in Google Drive where you want the downloaded videos to be uploaded.

You will need the **Folder ID** of this Google Drive folder.

#### How to Get the Google Drive Folder ID

1. Open Google Drive.
2. Navigate to the folder where you want the videos to be uploaded.
3. Open the folder.
4. Look at the URL in your browser's address bar.

It will look similar to:

```text
https://drive.google.com/drive/folders/1AbCDeFGhijkLMNopQRsTUVwxyz123456
```

5. The text after `/folders/` is the **Folder ID**.

For example:

```text
https://drive.google.com/drive/folders/1AbCDeFGhijkLMNopQRsTUVwxyz123456
                                      ↑
                                Folder ID
```

The Folder ID is:

```text
1AbCDeFGhijkLMNopQRsTUVwxyz123456
```

6. Copy the Folder ID.
7. Open the `.env` file in your project.
8. Add:

```env
DRIVE_FOLDER_ID="YOUR_COPIED_DRIVE_FOLDER_ID"
```

For example:

```env
DRIVE_FOLDER_ID="1AbCDeFGhijkLMNopQRsTUVwxyz123456"
```

Make sure you copy only the Folder ID, not the complete Google Drive URL.

### 8. Start the Bot

Once you have completed the setup, configured your cookies and Google Drive credentials, and added the Drive Folder ID to `.env`, you are ready to run the bot.

The bot will:

1. Search for videos using your configured queries.
2. Download the selected videos.
3. Process the downloaded files.
4. Upload the videos to your configured Google Drive folder.
5. Generate logs and metadata as the process runs.

That's it. Your automated video collection and upload workflow is ready to go.

Good luck, and enjoy!

---

## Research & Legal Notice

ClipFlow was developed primarily for academic and educational research,
particularly for collecting social-media video samples for research into
AI-generated content and deepfake detection.

The tool is intended to assist researchers in organizing and collecting
content that they are legally permitted to access and use for their
research.

Users are responsible for ensuring that their use of ClipFlow complies with
applicable laws, copyright requirements, privacy requirements, and the Terms
of Service of the platforms they access.

ClipFlow does not grant users any rights to third-party content. Users should
not download, reproduce, redistribute, or otherwise use content unless they
have the necessary rights, permission, or other lawful basis to do so.

For research datasets, users should maintain appropriate source information
and attribution where required and should avoid publicly redistributing
copyrighted media collected from third-party platforms.

The developers of ClipFlow do not encourage copyright infringement,
unauthorized access, or violation of third-party platform policies.

---

## License

This project is licensed under the MIT License.

Copyright © 2026 Saim Bilal.

See the [LICENSE](LICENSE) file for the complete license text.

## Contact

**Email:** [developwithsaim@gmail.com](mailto:developwithsaim@gmail.com)

**Portfolio:** [developwithsaim.vercel.app](https://developwithsaim.vercel.app)
