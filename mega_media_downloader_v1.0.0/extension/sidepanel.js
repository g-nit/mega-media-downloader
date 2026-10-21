const HOST = "com.megamediadownloader.host";
const $ = id => document.getElementById(id);

let port = null;
let jobs = [];
let folderItems = [];
let folderUrl = "";
let folderLoaded = false;
let settings = {
  moviesWindows: "",
  tvWindows: "",
  moviesNas: "",
  tvNas: "",
  megadlPath: "megatools.exe"
};

function send(message) {
  if (!port) throw new Error("Native helper is not connected. Run the native-host installer.");
  port.postMessage(message);
}

function setConnection(kind, text) {
  const el = $("connection");
  el.className = "connection " + kind;
  el.lastElementChild.textContent = text;
}

function destinationPath() {
  const cat = $("category").value;
  const target = $("target").value;
  if (cat === "custom") return $("customPath").value.trim();
  const suffix = target === "nas" ? "Nas" : "Windows";
  return cat === "movies" ? settings["movies" + suffix] : settings["tv" + suffix];
}

function updatePathPreview() {
  $("customWrap").hidden = $("category").value !== "custom";
  $("pathPreview").textContent = "Destination: " + (destinationPath() || "not configured — open Settings");
}

function connect() {
  try {
    port = chrome.runtime.connectNative(HOST);
    port.onMessage.addListener(msg => {
      if (msg.type === "hello") {
        setConnection("ok", "Native helper connected");
        send({action: "list"});
        chrome.storage.local.get(["megaSettings"]).then(data => {
          if (data.megaSettings) {
            settings = {...settings, ...data.megaSettings};
            updatePathPreview();
            try { send({action: "setConfig", config: data.megaSettings}); } catch (_) {}
          } else send({action: "getConfig"});
        });
      } else if (msg.type === "jobs") {
        jobs = msg.jobs || [];
        renderJobs();
      } else if (msg.type === "job") {
        const idx = jobs.findIndex(j => j.id === msg.job.id);
        if (idx >= 0) jobs[idx] = msg.job;
        else jobs.unshift(msg.job);
        renderJobs();
      } else if (msg.type === "config") {
        chrome.storage.local.get(["megaSettings"]).then(data => {
          settings = {...settings, ...(data.megaSettings || msg.config || {})};
          updatePathPreview();
        });
      } else if (msg.type === "chooseFilesLoading") {
        $("folderPicker").hidden = false;
        $("folderStatus").textContent = msg.message || "Waiting for megatools to list the folder…";
        $("fileList").replaceChildren();
        $("downloadSelectedBtn").disabled = true;
        $("selectAllFiles").checked = false;
        folderItems = [];
        folderLoaded = false;
      } else if (msg.type === "chooseFilesTree") {
        folderItems = Array.isArray(msg.items) ? msg.items : [];
        folderLoaded = true;
        $("folderPicker").hidden = false;
        const fileCount = folderItems.filter(item => item.type === "file").length;
        const folderCount = folderItems.filter(item => item.type === "folder").length;
        $("folderStatus").textContent = `${fileCount} files and ${folderCount} folders listed by megatools. Select items to download.`;
        renderFolderItems();
      } else if (msg.type === "chooseFilesSelectionSent") {
        $("downloadSelectedBtn").disabled = true;
        $("folderStatus").textContent = "Selection sent to megatools. Your download is starting…";
      } else if (msg.type === "chooseFilesOutput") {
        if (msg.line) $("folderStatus").textContent = msg.line;
      } else if (msg.type === "chooseFilesDone") {
        $("downloadSelectedBtn").disabled = true;
        if (msg.cancelled) $("folderStatus").textContent = "Folder download cancelled.";
        else if (msg.exitCode === 0) $("folderStatus").textContent = "megatools finished the selected download.";
        else $("folderStatus").textContent = `megatools exited with code ${msg.exitCode}. Check the queue for details.`;
      } else if (msg.type === "folderLoading") {
        $("folderPicker").hidden = false;
        $("folderStatus").textContent = msg.message || "Loading folder contents…";
        $("fileList").replaceChildren();
        $("downloadSelectedBtn").disabled = true;
        $("selectAllFiles").checked = false;
        folderItems = [];
        folderLoaded = false;
      } else if (msg.type === "folderFiles") {
        folderItems = Array.isArray(msg.items) ? msg.items : [];
        folderLoaded = true;
        $("folderPicker").hidden = false;
        const count = msg.fileCount ?? folderItems.filter(item => item.type === "file").length;
        $("folderStatus").textContent = `${count} files found. Select what you want to download.`;
        renderFolderItems();
      } else if (msg.type === "error") {
        setConnection("bad", msg.message || "Native helper error");
        if (!$("folderPicker").hidden && !folderLoaded) {
          $("folderStatus").textContent = "Error: " + (msg.message || "Could not load folder.");
        }
      } else if (msg.type === "pong") {
        setConnection("ok", "Native helper ready");
      }
    });

    port.onDisconnect.addListener(() => {
      const error = chrome.runtime.lastError?.message;
      port = null;
      setConnection("bad", error ? "Helper disconnected: " + error : "Helper disconnected");
      setTimeout(connect, 2500);
    });
    port.postMessage({action: "hello"});
  } catch (e) {
    setConnection("bad", "Native helper unavailable. Install it from the project folder.");
  }
}

function renderJobs() {
  $("queueCount").textContent = `${jobs.length} job${jobs.length === 1 ? "" : "s"}`;
  const root = $("queue");
  if (!jobs.length) {
    root.innerHTML = '<div class="empty">Your queue is empty.</div>';
    return;
  }
  root.replaceChildren();
  jobs.slice().reverse().forEach(job => {
    const card = document.createElement("article");
    card.className = "job";
    const top = document.createElement("div");
    top.className = "job-top";
    const info = document.createElement("div");
    info.className = "job-info";
    const name = document.createElement("div");
    name.className = "job-name";
    name.textContent = job.label || job.url || "MEGA download";
    const path = document.createElement("div");
    path.className = "job-path";
    path.textContent = job.path || "";
    info.append(name, path);
    const status = document.createElement("span");
    status.className = "status " + (job.status || "queued");
    status.textContent = job.status || "queued";
    top.append(info, status);
    card.append(top);

    const bar = document.createElement("div");
    bar.className = "progress";
    const fill = document.createElement("div");
    fill.style.width = `${Math.max(0, Math.min(100, job.progress || 0))}%`;
    bar.append(fill);
    card.append(bar);

    const bottom = document.createElement("div");
    bottom.className = "job-bottom";
    const detail = document.createElement("span");
    detail.textContent = job.detail || (job.progress ? `${job.progress}%` : "Waiting");
    bottom.append(detail);
    if (["queued", "selecting", "downloading"].includes(job.status)) {
      const cancel = document.createElement("button");
      cancel.className = "cancel";
      cancel.textContent = "Cancel";
      cancel.type = "button";
      cancel.addEventListener("click", () => {
        try {
          if (job.kind === "chooseFiles") send({action: "cancelChooseFiles"});
          else send({action: "cancel", id: job.id});
        } catch (e) { setConnection("bad", e.message); }
      });
      bottom.append(cancel);
    }
    card.append(bottom);
    if (job.target) {
      const tag = document.createElement("div");
      tag.className = "tag";
      tag.textContent = `${job.category || "custom"} · ${job.target === "nas" ? "Synology NAS" : "Windows PC"}`;
      card.append(tag);
    }
    root.append(card);
  });
}

function isMegaFolderLink(url) {
  return /^https:\/\/(www\.)?mega\.(nz|co\.nz)\/(?:folder\/[A-Za-z0-9_-]+|#F![A-Za-z0-9_-]+!|#f![A-Za-z0-9_-]+!)/i.test(url);
}

function renderFolderItems() {
  const root = $("fileList");
  root.replaceChildren();

  if (!folderItems.length) {
    root.innerHTML = '<div class="empty">No items were returned for this folder.</div>';
    updateSelectedCount();
    return;
  }

  const sorted = folderItems.slice().sort((a, b) =>
    String(a.relativePath || a.name || "").localeCompare(String(b.relativePath || b.name || ""), undefined, {numeric: true, sensitivity: "base"})
  );

  sorted.forEach((item, index) => {
    const row = document.createElement("label");
    row.className = "file-row " + (item.type === "folder" || item.type === "directory" ? "folder-row" : "file-row-item");
    row.style.paddingLeft = `${12 + Math.max(0, Number(item.depth) || 0) * 16}px`;
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "item-check";
    checkbox.dataset.index = String(folderItems.indexOf(item));
    checkbox.dataset.path = item.relativePath || item.name || "";
    checkbox.dataset.type = item.type || "file";
    checkbox.addEventListener("change", () => {
      if (checkbox.dataset.type === "folder" || checkbox.dataset.type === "directory") {
        const prefix = checkbox.dataset.path.replace(/\/+$/, "") + "/";
        root.querySelectorAll(".item-check").forEach(other => {
          if (other === checkbox) return;
          const p = other.dataset.path || "";
          if (p.startsWith(prefix)) other.checked = checkbox.checked;
        });
      }
      updateSelectedCount();
    });

    const icon = document.createElement("span");
    const isFolder = item.type === "folder" || item.type === "directory";
    icon.className = "file-icon";
    icon.textContent = isFolder ? "📁" : "📄";

    const details = document.createElement("span");
    details.className = "file-details";
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = item.name || item.relativePath || (isFolder ? "Folder" : "File");
    const rel = document.createElement("span");
    rel.className = "file-relative";
    rel.textContent = item.relativePath || item.name || "";
    details.append(name, rel);

    row.append(checkbox, icon, details);
    if (!isFolder && (item.sizeLabel || (item.size !== undefined && Number.isFinite(Number(item.size))))) {
      const size = document.createElement("span");
      size.className = "file-size";
      size.textContent = item.sizeLabel || formatBytes(Number(item.size));
      row.append(size);
    }
    root.append(row);
  });

  updateSelectedCount();
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let i = 1; i < units.length && value >= 1024; i++) {
    value /= 1024;
    unit = units[i];
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${unit}`;
}

function selectedMegatoolsNumbers() {
  const selectedBoxes = [...$("fileList").querySelectorAll(".item-check:checked")];
  const selectedItems = selectedBoxes
    .map(box => folderItems[Number(box.dataset.index)])
    .filter(Boolean);
  const selectedFolders = selectedItems.filter(item => item.type === "folder" || item.type === "directory");
  const chosen = selectedItems.filter(item => {
    const path = item.relativePath || item.name || "";
    // When a parent folder is selected, don't also send its selected descendants.
    return !selectedFolders.some(folder => {
      if (folder === item) return false;
      const parentPath = (folder.relativePath || folder.name || "").replace(/\/+$/, "");
      return path.startsWith(parentPath + "/");
    });
  });
  return [...new Set(chosen.map(item => Number(item.number)).filter(Number.isInteger))].sort((a, b) => a - b);
}

function selectedFileCount() {
  const selectedBoxes = [...$("fileList").querySelectorAll(".item-check:checked")];
  return selectedBoxes.filter(box => box.dataset.type === "file").length;
}

function updateSelectedCount() {
  const count = selectedFileCount();
  const hasSelection = selectedMegatoolsNumbers().length > 0;
  $("downloadSelectedBtn").disabled = !folderLoaded || !hasSelection;
  $("downloadSelectedBtn").textContent = count
    ? `Download Selected Files (${count})`
    : "Download Selected Files";
  const boxes = [...$("fileList").querySelectorAll(".item-check")];
  const fileBoxes = boxes.filter(box => box.dataset.type === "file");
  $("selectAllFiles").checked = fileBoxes.length > 0 && fileBoxes.every(box => box.checked);
}

$("category").addEventListener("change", updatePathPreview);
$("target").addEventListener("change", updatePathPreview);
$("customPath").addEventListener("input", updatePathPreview);
$("settingsBtn").addEventListener("click", () => chrome.runtime.openOptionsPage());
$("refreshBtn").addEventListener("click", () => {
  try { send({action: "list"}); } catch (e) { setConnection("bad", e.message); }
});

$("addBtn").addEventListener("click", () => {
  const url = $("megaLink").value.trim();
  const path = destinationPath();
  if (!/^https:\/\/(www\.)?mega\.(nz|co\.nz)\//i.test(url)) {
    alert("Enter a valid https://mega.nz or https://mega.co.nz link.");
    return;
  }
  if (!path) {
    alert("Choose or configure a destination folder first.");
    return;
  }
  $("addBtn").disabled = true;
  try {
    send({action: "enqueue", url, path, category: $("category").value, target: $("target").value});
    $("megaLink").value = "";
  } catch (e) {
    setConnection("bad", e.message);
    alert(e.message);
  }
  setTimeout(() => $("addBtn").disabled = false, 500);
});

$("browseBtn").addEventListener("click", () => {
  const url = $("megaLink").value.trim();
  if (!isMegaFolderLink(url)) {
    alert("Paste a public MEGA folder link first, such as https://mega.nz/folder/HANDLE#KEY.");
    return;
  }
  folderUrl = url;
  $("folderPicker").hidden = false;
  $("folderStatus").textContent = "Loading folder contents…";
  $("fileList").replaceChildren();
  folderItems = [];
  folderLoaded = false;
  $("downloadSelectedBtn").disabled = true;
  const path = destinationPath();
  if (!path) {
    alert("Choose or configure a destination folder first.");
    return;
  }
  try {
    send({action: "chooseFiles", url: folderUrl, path, category: $("category").value, target: $("target").value});
  } catch (e) {
    $("folderStatus").textContent = e.message;
    setConnection("bad", e.message);
  }
});

$("closePickerBtn").addEventListener("click", () => {
  $("folderPicker").hidden = true;
});

$("selectAllFiles").addEventListener("change", () => {
  const checked = $("selectAllFiles").checked;
  $("fileList").querySelectorAll(".item-check").forEach(box => {
    if (box.dataset.type === "file") box.checked = checked;
  });
  updateSelectedCount();
});

$("downloadSelectedBtn").addEventListener("click", () => {
  const numbers = selectedMegatoolsNumbers();
  if (!numbers.length) {
    alert("Select at least one file or folder.");
    return;
  }
  try {
    send({action: "chooseFilesSelect", numbers});
    $("downloadSelectedBtn").disabled = true;
    $("folderStatus").textContent = "Sending selection to megatools…";
  } catch (e) {
    setConnection("bad", e.message);
    alert(e.message);
  }
});

$("clearHistoryBtn").addEventListener("click", () => {
  const finishedCount = jobs.filter(job =>
    ["completed", "failed", "cancelled"].includes(job.status)
  ).length;

  if (!finishedCount) {
    alert("There are no finished jobs to clear.");
    return;
  }

  if (!confirm(`Clear ${finishedCount} finished job(s) from history?`)) {
    return;
  }

  try {
    send({ action: "clearHistory" });
  } catch (e) {
    setConnection("bad", e.message);
  }
});

chrome.storage.local.get(["megaSettings"]).then(data => {
  if (data.megaSettings) settings = {...settings, ...data.megaSettings};
  updatePathPreview();
});
connect();
