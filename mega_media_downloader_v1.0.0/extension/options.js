const ids = ["moviesWindows","tvWindows","moviesNas","tvNas","megadlPath"];
const defaults = {
  moviesWindows:"",
  tvWindows:"",
  moviesNas:"",
  tvNas:"",
  megadlPath:"megatools.exe"
};
async function load() {
  const data = await chrome.storage.local.get(["megaSettings"]);
  const config = {...defaults, ...(data.megaSettings || {})};
  ids.forEach(id => document.getElementById(id).value = config[id] || "");
}
function saveNativeConfig(config) {
  return new Promise((resolve, reject) => {
    let port;
    try {
      port = chrome.runtime.connectNative("com.megamediadownloader.host");
    } catch (error) {
      reject(error);
      return;
    }
    let finished = false;
    const finish = (error) => {
      if (finished) return;
      finished = true;
      try { port.disconnect(); } catch (_) {}
      error ? reject(error) : resolve();
    };
    port.onMessage.addListener(msg => {
      if (msg.type === "config") finish();
      else if (msg.type === "error") finish(new Error(msg.message || "Native helper rejected settings."));
    });
    port.onDisconnect.addListener(() => {
      const error = chrome.runtime.lastError?.message;
      if (!finished) finish(new Error(error || "Native helper disconnected before confirming settings."));
    });
    port.postMessage({action:"setConfig", config});
  });
}
document.getElementById("save").addEventListener("click", async () => {
  const config = {};
  ids.forEach(id => config[id] = document.getElementById(id).value.trim());
  await chrome.storage.local.set({megaSettings:config});
  const message = document.getElementById("message");
  try {
    await saveNativeConfig(config);
    message.textContent = "Settings saved and synced with the native helper.";
  } catch (error) {
    // Chrome storage is the extension's source of truth, so paths remain available
    // even if the helper needs to be reinstalled or is temporarily unavailable.
    message.textContent = "Settings saved in Chrome. Native helper sync failed: " + error.message;
  }
});
load();
