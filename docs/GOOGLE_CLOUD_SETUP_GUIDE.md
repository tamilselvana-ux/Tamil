# 🌐 Google Cloud Setup Guide for Admin OAuth 2.0, Drive & Sheets API

This guide provides click-by-click instructions for setting up Google Cloud credentials so that the Super Admin can connect their Google account, allowing the application to automatically create and manage dedicated Google Sheets for each approved flower merchant.

---

## 1. Create a Google Cloud Project

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Log in with the **Admin's Google Account** (the account whose Google Drive will hold the merchant spreadsheets).
3. In the top navigation bar, click the **Project Dropdown** (next to the "Google Cloud" logo) and click **"New Project"**.
4. Enter the Project details:
   - **Project Name:** `AVT-Flower-Terminal-Sheets` (or any preferred name).
   - **Organization:** Select your organization or leave as **"No organization"**.
5. Click **"Create"** and wait a few seconds until the project is created.
6. Make sure your newly created project is selected in the top project dropdown.

---

## 2. Enable Google Sheets API & Google Drive API

1. In the Google Cloud Console, open the left navigation menu (☰) and navigate to:
   **APIs & Services > Library**.
2. Search for **"Google Sheets API"**:
   - Click on **Google Sheets API** in the search results.
   - Click the blue **"Enable"** button.
3. Return to the **Library** (or search from the top search bar) and search for **"Google Drive API"**:
   - Click on **Google Drive API** in the search results.
   - Click the blue **"Enable"** button.

---

## 3. Configure the OAuth Consent Screen

1. In the left navigation menu, go to **APIs & Services > OAuth consent screen**.
2. Select the **User Type**:
   - **Internal** *(Recommended if you are on Google Workspace)*: The app will only be available to users within your Google Workspace organization. **Refresh tokens will never expire.**
   - **External** *(For personal `@gmail.com` accounts)*:
     - *Important Note:* In "Testing" mode, Google refresh tokens expire after 7 days. To prevent token expiration, once configured, click **"Publish App"** to set the app status to **"In production"** (Verification is NOT required if you only use the narrow `drive.file` and `spreadsheets` scopes for your own administrative login).
3. Click **"Create"**.
4. Fill in the **App Information**:
   - **App name:** `AVT Flower Terminal`
   - **User support email:** Select your admin email.
   - **Developer contact information:** Enter your email.
5. Click **"Save and Continue"**.
6. On the **Scopes** page:
   - Click **"Add or Remove Scopes"**.
   - Search and select:
     - `.../auth/spreadsheets` (See, edit, create, and delete your Google Sheets spreadsheets).
     - `.../auth/drive.file` (See, edit, create, and delete only the specific Google Drive files you use with this app).
   - Click **"Update"**, then click **"Save and Continue"**.
7. If your app is External and in Testing status:
   - Add your Admin Gmail address under **"Test users"** so you are authorized to log in.
   - Click **"Save and Continue"**.
8. Go back to the **OAuth consent screen** tab. If you chose External, click **"Publish App"** to ensure your refresh token remains valid indefinitely.

---

## 4. Create OAuth 2.0 Web Client Credentials

1. In the left navigation menu, go to **APIs & Services > Credentials**.
2. At the top of the page, click **"+ Create Credentials"** and select **"OAuth client ID"**.
3. Fill in the Application details:
   - **Application type:** Select **"Web application"**.
   - **Name:** `AVT Flower Terminal Web Client`
   - **Authorized JavaScript origins:**
     - For local development: `http://localhost:8000`, `http://127.0.0.1:8000`, `http://localhost:8001`, `http://localhost:8002`, `http://localhost:8003`.
     - For production: Add your production domain (e.g., `https://your-domain.com`).
   - **Authorized redirect URIs** *(Crucial)*:
     - For local development:
       - `http://localhost:8000/super-admin/google/callback/`
       - `http://127.0.0.1:8000/super-admin/google/callback/`
       - `http://localhost:8001/super-admin/google/callback/`
       - `http://localhost:8002/super-admin/google/callback/`
       - `http://localhost:8003/super-admin/google/callback/`
     - For production:
       - `https://your-domain.com/super-admin/google/callback/`
4. Click **"Create"**.
5. A modal dialog will appear displaying:
   - **Your Client ID** (e.g. `1234567890-abcdefg.apps.googleusercontent.com`)
   - **Your Client Secret** (e.g. `GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx`)
6. Copy both values. You can also download the JSON file for your records.

---

## 5. Generate Fernet Token Encryption Key

The Admin's Google OAuth refresh token must be stored **encrypted at rest** in the database.

Generate an AES-128 / Fernet encryption key by running this command in your terminal:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Example output: `v2k8_UaXp9L0Y7M8q2WzE1V5s4d3f2g1h0j9k8l7m6n5=`

---

## 6. Configure Environment Variables (`.env`)

Add the following environment variables to your `.env` file (or system environment):

```env
# Google OAuth 2.0 Admin Credentials
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:8002/super-admin/google/callback/

# Google Drive Storage Folder
GOOGLE_DRIVE_FOLDER_NAME="AVT Flower Market - Merchant Sheets"

# Encryption key for storing Google OAuth tokens at rest
GOOGLE_OAUTH_ENCRYPTION_KEY=your-generated-fernet-key-here

# Optional: Share sheet with merchant Gmail as read-only Viewer (True/False)
GOOGLE_SHEET_SHARE_VIEWER=False
```

---

## 7. Connecting Your Admin Account in the App

Once the environment variables are set:
1. Log into the application as Super Admin (`/login/`).
2. Go to the Super Admin Command Center (`/super-admin/`).
3. Click the **"Connect Google Drive & Sheets"** button (or visit `/super-admin/google/connect/`).
4. Google will ask you to authorize access with `access_type=offline` and `prompt=consent`.
5. Grant permissions. You will be redirected back to `/super-admin/` with a confirmation badge:
   `🟢 Google Drive & Sheets Connected (admin@example.com)`.
6. From then on, whenever you approve a pending merchant, their personal spreadsheet is provisioned automatically!
