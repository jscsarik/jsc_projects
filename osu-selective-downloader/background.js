
// Background script for manifest V3
chrome.runtime.onInstalled.addListener(() => {
  console.log('osu! Selective Downloader extension installed.');
});

// We can handle download completion or other persistent tasks here
