# DISCORD-USERNAME-SNIPER
<div align="center">

  <h1>⚡ DISCORD USERNAME SNIPER & CHECKER</h1>

  <p>
    An ultra-fast, multi-threaded asynchronous username checker built for high throughput, featuring real-time terminal analytics and robust rate-limit management.
  </p>

  <p>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.9+"></a>
    <a href="https://github.com/"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License"></a>
    <a href="https://github.com/"><img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blue?style=for-the-badge" alt="Platform"></a>
  </p>

</div>

---

## 📌 Features

- **🚀 Asyncio Architecture:** Blazing-fast concurrency optimized for high-volume availability scanning.
- **📊 Interactive Live Dashboard:** Rich terminal interface updating stats, thread lanes, errors, and availability logs in real-time.
- **🛡️ Intelligent Rate-Limit Queue:** Gracefully handles cooldowns by pausing affected lanes and re-queuing usernames.
- **💾 Instant Auto-Save:** Hits are written directly to your output file with disk-write thread safety.
- **🔀 Dual Checking Modes:** Switch seamlessly between authenticated Token execution and high-concurrency Proxy scanning.

---

## ⚙️ Operating Modes

The engine supports two primary operational approaches:

### 1. Token Mode
* **How it works:** Authenticates directly using your account token(s) configured in `config.json`.
* **Best for:** Fast verification and low-overhead targeted checks.
* **Setup:** Place your token inside `config.json` under `discord_tokens`.

### 2. Proxy Mode
* **How it works:** Routes requests across external connections listed in `proxies.txt` to bypass IP-based throttling.
* **Best for:** High-volume, continuous generation and brute-force style dictionary runs.
* **Requirements:** Requires configuring `proxies.txt`.

> [!WARNING]
> **Use Paid Proxies Only:** Free, open, or public proxies will get flagged, blocked, or heavily throttled by Cloudflare and Discord's edge network. For optimal results, use high-speed **paid residential** or **private rotating datacenter** proxies.

---

## 📂 Project Structure

```text
├── config.json          # Main runtime configuration & tokens
├── proxies.txt          # List of proxies (one per line)
├── main.py              # Main execution script & lane orchestrator
├── sniper.py            # Underlying scanner engine & dashboard UI
├── requirements.txt     # Python dependencies
└── hits.txt             # Auto-saved available usernames

