
// This script runs on osu.ppy.sh/beatmapsets/*
// Its primary job is already handled by popup.js executeScript, 
// but we can listen for specific events here if needed.

console.log('osu! Selective Downloader: Content script active.');

// Listen for messages from popup if we need real-time data
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'GET_DIFFICULTIES') {
    const diffs = Array.from(document.querySelectorAll('.bm-difficulty-name__title')).map(el => el.textContent.trim());
    sendResponse({ diffs });
  }
});
