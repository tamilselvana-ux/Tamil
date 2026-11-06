# Stub & Incomplete-Code Scan

Run: 2026-11-05 22:52 · Root: `D:\Bill`

**Blockers:** 0 · **Warnings:** 13 · **Verdict:** ✅ no stubs found

## 🚫 Blockers (must fix before 'done')
| Rule | File | Line | Code |
|---|---|---|---|
| — | — | — | none |

## ⚠️ Warnings (review)
| Rule | File | Line | Code |
|---|---|---|---|
| Hard-coded localhost URL | apps\core\google_auth.py | 40 | `return 'http://localhost:8000/super-admin/google/callback/'` |
| Hard-coded localhost URL | config\settings.py | 155 | `'http://127.0.0.1,http://localhost,http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002'` |
| Hard-coded localhost URL | config\settings.py | 155 | `'http://127.0.0.1,http://localhost,http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002'` |
| Hard-coded localhost URL | config\settings.py | 155 | `'http://127.0.0.1,http://localhost,http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002'` |
| Hard-coded localhost URL | config\settings.py | 155 | `'http://127.0.0.1,http://localhost,http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002'` |
| Hard-coded localhost URL | config\settings.py | 155 | `'http://127.0.0.1,http://localhost,http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002'` |
| alert() used for UX | templates\flowers\flowers.html | 120 | `alert('Error: ' + data.message);` |
| alert() used for UX | templates\flowers\flowers.html | 123 | `alert('Network error: ' + err);` |
| alert() used for UX | templates\parties\suppliers.html | 323 | `alert('Delete failed: ' + (data.message // 'Error'));` |
| alert() used for UX | templates\parties\suppliers.html | 326 | `alert('Error: ' + err);` |
| alert() used for UX | templates\purchases\terminal.html | 296 | `alert('At least one lot line must remain in active terminal.');` |
| alert() used for UX | templates\purchases\terminal.html | 439 | `alert('Posting error: ' + data.message);` |
| alert() used for UX | templates\purchases\terminal.html | 442 | `alert('Network error: ' + e);` |

