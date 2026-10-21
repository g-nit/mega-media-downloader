
# MEGA Media Downloader — Installation Guide

This guide explains how to install the Chrome extension and register its Windows native host so the extension can communicate with `MegaMediaNativeHost.exe`.

## Requirements

- Windows 10 or Windows 11
- Google Chrome
- MEGA Media Downloader extension
- The MEGA Media Downloader release ZIP downloaded and extracted
- `MegaMediaNativeHost.exe` included in the release ZIP
- `megatools.exe` configured separately if it is required by your downloader setup

**You do not need to install Python or PyInstaller.** The prebuilt native host executable is included in the release.

## Step 1: Download and extract the ZIP

1. Download the latest MEGA Media Downloader release ZIP.
2. Right-click the ZIP file and select **Extract All**.
3. Extract it to a folder you can access, such as your Downloads folder.

Keep the `dist` folder and `register-host.ps1` together in the `native-host` directory.

The expected structure is:

```text
MEGA-Media-Downloader/
├── extension/
└── native-host/
    ├── dist/
    │   └── MegaMediaNativeHost.exe
    └── register-host.ps1
```

Do not run the registration script from inside the ZIP without extracting it first.

## Step 2: Install the Chrome extension

If the extension is distributed as an unpacked folder:

1. Open Google Chrome.
2. Navigate to `chrome://extensions`.
3. Turn on **Developer mode**.
4. Click **Load unpacked**.
5. Select the `extension` folder extracted from the ZIP.


## Step 3: Copy your extension ID

1. Open `chrome://extensions`.
2. Find MEGA Media Downloader.
3. Locate the extension **ID**.
4. Copy the complete 32-character extension ID.

The ID typically contains lowercase letters from `a` through `p`.

**Important:** If you use an unpacked extension, its ID must remain consistent with the ID used during registration. If you reinstall the extension or change its ID, you may need to register the native host again.

## Step 4: Run the registration script

1. Open the extracted `native-host` folder.
2. Right-click an empty area inside the folder.
3. Select **Open in Terminal** or open PowerShell in that folder.
4. Run the following command, replacing the example ID with your actual extension ID:

```powershell
.\register-host.ps1 -ExtensionId "PASTE_YOUR_EXTENSION_ID_HERE"
```

If Windows blocks the script because of its execution policy, open PowerShell in the same folder and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\register-host.ps1" -ExtensionId "PASTE_YOUR_EXTENSION_ID_HERE"
```

Only run scripts obtained from a release source you trust. Review the script before running it if you are unsure what it does.

## Step 5: Confirm registration

When registration succeeds, PowerShell should display a success message and the installation paths.

The native host executable is copied to:

```text
%LOCALAPPDATA%\MegaMediaDownloader\MegaMediaNativeHost.exe
```

The Chrome Native Messaging manifest is created at:

```text
%LOCALAPPDATA%\MegaMediaDownloader\com.megamediadownloader.host.json
```

The script also registers the manifest in the current Windows user's Registry.

You can close PowerShell after the success message appears.

## Step 6: Start using the extension

1. Return to `chrome://extensions`.
2. Reload MEGA Media Downloader.
3. Open the extension's side panel.
4. Try connecting to the native host.

If the extension still reports that the native host is unavailable, confirm that the extension ID used during registration matches the currently installed extension ID.

## Troubleshooting

### "Cannot find dist/MegaMediaNativeHost.exe"

Make sure you extracted the ZIP and preserved this structure:

```text
native-host/
├── dist/
│   └── MegaMediaNativeHost.exe
└── register-host.ps1
```

### "Invalid Chrome extension ID"

Copy the complete ID from `chrome://extensions`. Do not include the extension name or any extra spaces.

### The extension cannot connect to the native host

- Confirm the registration script completed successfully.
- Confirm the extension ID matches the ID used during registration.
- Reload the extension.
- Confirm the EXE exists in `%LOCALAPPDATA%\MegaMediaDownloader`.
- Check whether Windows security software blocked the executable.

### The extension connects, but downloads fail

Native host registration does not itself configure MEGA downloads. Verify that `megatools.exe` is available at the configured path or through the system `PATH`, and check the downloader's settings and error message.

## Uninstalling the native host

To uninstall the native host, close the extension and remove the following Registry key:

```text
HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\com.megamediadownloader.host
```

Then delete the installation folder:

```text
%LOCALAPPDATA%\MegaMediaDownloader
```

Only remove these entries if they belong to MEGA Media Downloader.

---

**Need help?** When reporting a problem, include the exact error message from PowerShell or the extension so it can be diagnosed more easily.
