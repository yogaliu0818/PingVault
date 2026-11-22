# PingVault Project Memory

## Current decisions

- GitHub repository：`yogaliu0818/PingVault`
- Release artifact 使用固定名稱 `PingVault-Setup.exe`，讓 README 的 latest-download 連結不必隨版本修改
- `build/` 與 `dist/` 不提交到 Git；安裝檔只放 GitHub Release
- 測試使用 Python 標準 `unittest`，避免 CI 必須額外依賴 pytest

## Known gaps

- 尚未加入程式碼簽章
- 尚未完成 Windows 10／11 實機互動測試
- 尚未決定公開 License
