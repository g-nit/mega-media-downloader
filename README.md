![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-ES6%2B-F7DF1E?logo=javascript&logoColor=black)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?logo=css3&logoColor=white)

[![Chrome Extension](https://img.shields.io/badge/Chrome-Extension-4285F4?logo=googlechrome&logoColor=white)](https://www.google.com/chrome/)
[![Windows](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/g-nit/mega-media-downloader?label=Latest%20Release)](https://github.com/g-nit/mega-media-downloader/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/g-nit/mega-media-downloader/total?label=Downloads)](https://github.com/g-nit/mega-media-downloader/releases)


# MEGA Media Downloader

A Chrome extension for downloading files and folders from MEGA directly to your Windows PC or Synology NAS.

Manage downloads from your browser with a built-in queue, progress tracking, destination settings, and download controls.

## Features

- **MEGA links:** Enter public MEGA file or folder links.
- **Folder selection:** Browse files in a public folder and select which files to download.
- **Custom destinations:** Configure separate destinations for movies and TV shows.
- **Windows and NAS support:** Save files to local Windows folders or accessible NAS destinations.
- **Download queue:** Manage multiple download jobs.
- **Progress tracking:** Monitor download progress.
- **Native integration:** Uses a Windows native host to communicate with the downloader.

## Requirements

Before installing, make sure you have:

- Google Chrome on Windows.
- Windows access to your desired download destinations.
- The MEGA Media Downloader release ZIP.
- The included `MegaMediaNativeHost.exe` executable.
- The included native host registration script.

Python and PyInstaller are not required for normal installation when using the prebuilt executable.

## Installation

### Step 1: Download the release

1. Open the repository's [Releases](../../releases) page.
2. Download the latest release ZIP.
3. Extract the ZIP to a permanent folder on your computer.

**Important:** Keep the extracted files together in their original folder structure. Do not run the extension directly from inside the ZIP file.

For example:

```text
mega-media-downloader/
├── extension/
    └── manifest.json
    └── background.js
    └── options.html
    └── options.js
    └── sidepanel.html
    └── sidepanel.js
    └── style.css
├── native-host/
    └── dist/
        └── MegaMediaNativeHost.exe
│   └── com.megamediadownloader.host.json
    └── host.py
    └── README.md
    └── register-host.ps1
    └── uninstall-host.ps1

```

The filenames and folder structure above are illustrative. Use the actual structure included in your release.

### Step 2: Install the Chrome extension

1. Open Google Chrome.
2. Navigate to `chrome://extensions`.
3. Turn on **Developer mode**.
4. Click **Load unpacked**.
5. Select the extracted extension folder containing `manifest.json`.
6. Confirm that MEGA Media Downloader appears in your extensions list.

Keep the extension folder in a permanent location. Moving or deleting it may prevent Chrome from loading it.

### Step 3: Register the native host

The native host allows the Chrome extension to communicate with the Windows downloader executable.

1. Open the extracted project folder.
2. Locate the included registration script, such as `register-host.ps1`.
3. Right-click the script and choose **Run with PowerShell**, if available.

If Windows does not offer that option, open PowerShell and run the script using its actual path:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\native-host\register-host.ps1"
```

Run this command from the extracted project directory, or replace the relative path with the script's full path.

If Windows blocks the script, review the warning and verify that the script came from the release you intended to install before proceeding.

**Important:** The registration script must know your Chrome extension ID and the actual location of `MegaMediaNativeHost.exe`. Follow any prompts provided by the included script. Do not assume registration succeeded until the extension can communicate with the native host.

If registration fails, verify that:

- The extension is installed in Chrome.
- The executable exists at the path expected by the script.
- The Chrome extension ID is correct.
- The script completed without errors.

You generally need to register the native host only once per installation, unless you move the executable or change the extension ID.

### Step 4: Configure download destinations

Open MEGA Media Downloader and navigate to Settings.

Configure the destinations you want to use:

- **Movies — Windows:** Your local movie download folder.
- **TV Shows — Windows:** Your local TV download folder.
- **Movies — NAS:** Your movie destination on the Synology NAS.
- **TV Shows — NAS:** Your TV destination on the Synology NAS.

Example Windows destinations:

```text
C:\Media\Movies
C:\Media\TV
```

Example NAS destinations, if your NAS share is mapped as a Windows drive:

```text
Z:\Media\Movies
Z:\Media\TV
```

Use paths that actually exist on your system, and ensure Windows has permission to write to them.

For NAS downloads, the native host runs on your Windows PC. The NAS destination must therefore be accessible from Windows, for example through a mapped network drive or a suitable UNC path.

If you use a mapped drive, make sure it is accessible in the Windows session running Chrome.

Save your settings before starting downloads.

## Usage

### Download a single file

1. Open MEGA Media Downloader.
2. Paste a public MEGA file link into the link field.
3. Choose the appropriate download destination or media category.
4. Start the download.
5. Monitor the job in the queue.

The file will be saved to the configured destination.

### Download selected files from a folder

1. Copy a public MEGA folder link.
2. Paste it into the extension.
3. Allow the extension to retrieve the folder contents.
4. Select the files you want to download.
5. Use **Select All** or **Clear** if those controls are available in your release.
6. Start the download for your selected files.

You can use this workflow to download specific episodes or files without downloading everything in the folder.

### Manage the download queue

Use the queue to monitor your jobs.

Depending on the job and downloader state, you can:

- **Cancel** a download.
- Monitor the reported progress.

Avoid closing Chrome or shutting down Windows while downloads are running.

### Choose the right destination

Use the movie destination for movies and the TV destination for episodes or TV-season folders.

You can configure your preferred Windows and NAS destinations in Settings. Verify the destination shown for each job before starting a large download.

## Troubleshooting

### The extension cannot connect to the native host

1. Confirm that `MegaMediaNativeHost.exe` exists.
2. Run the registration script again using the correct extension ID.
3. Verify that the script points to the executable's current location.
4. Reload the extension from `chrome://extensions`.
5. Close and reopen Chrome if necessary.

### Destination shows as not configured

Open Settings and verify that the destination paths have been saved. Confirm that the folder exists and is writable.

For NAS destinations, check that the network share is connected and accessible from Windows.

### A download fails

- Verify that the MEGA link is public and valid.
- Check your internet connection.
- Confirm that the destination has enough free space.
- Verify that the destination is writable.
- Check whether the link or folder requires access that the downloader does not support.

If the error persists, record the exact error message and the affected link type (file or folder). Avoid posting private or sensitive links publicly.

### Downloads fail when using a NAS destination

Test the same download to a local Windows folder first.

If the local download succeeds, check the NAS share path, Windows permissions, connectivity, and available storage.

### Progress does not appear accurate

The displayed progress depends on information reported by the native downloader. If the progress bar does not match the reported percentage or stalls, include the displayed percentage and relevant log messages when reporting the issue.

## Updating

1. Download the latest release ZIP.
2. Extract the new version into a new folder.
3. Open `chrome://extensions`.
4. Remove the old extension or otherwise replace its installation as appropriate.
5. Load the new extension folder.
6. Run the registration script again if the executable location or extension ID has changed.
7. Verify your Settings and destination paths.

Keep the previous release until the new version has been tested successfully.

## Security and privacy

The extension uses a local Windows native host to perform downloads.

Only install releases you trust. Review the included registration script before running it, and grant access only to destinations you intend to use.

Do not share private MEGA links, credentials, or sensitive download information in public issue reports.

## Development

The project includes Python source code for the native host and a PyInstaller build process for producing the Windows executable.

Developers who want to modify the native host can use the source files and build instructions included in the repository. End users installing a release with the prebuilt executable do not need to install Python or PyInstaller.

## Support

If you encounter a problem:

1. Check the troubleshooting section.
2. Verify that you are using the latest release.
3. Open a [GitHub issue](../../issues) with the error message, relevant steps to reproduce it, and your Windows/Chrome versions.

Please do not include API keys, private links, or other sensitive information in issue reports.

## License

See the `LICENSE` file in this repository for the terms under which this project is distributed.
