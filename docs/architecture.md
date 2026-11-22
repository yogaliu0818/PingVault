# PingVault Architecture

## Design goals

- 所有系統變更都能被追蹤與還原
- UI 不直接承擔 Windows 系統 API 的細節
- 沒有管理員權限、沒有遊戲程序或網路失敗時，仍能安全退回
- 服務可以在不啟動完整 GUI 的情況下被單元測試

## Layers

```text
UI / Tray
    ↓
Application workflow
    ↓
Domain services
    ↓
Windows adapters and external integrations
```

### UI layer

`pingvault/ui/` 負責頁面、狀態呈現、工作執行緒與系統匣事件。UI 應透過服務層操作系統，不直接修改程序或電源設定。

### Service layer

`pingvault/services/` 包含程序優先權、網路、電源、計時器、暫停程式、FPS、效能監測與還原 ledger。

### Recovery boundary

每個會改變系統狀態的操作，都應先記錄原始狀態，再套用變更；停止、例外與下次啟動時，依 ledger 還原。還原操作必須具備冪等性，重複執行不應造成額外副作用。

## Boost lifecycle

```text
Idle → Preparing → WaitingForGame → Boosting → Restoring → Restored
                         │                  │
                         └── game found ────┘

Any failure → RecoveryRequired → Restored
```

## Testing boundary

- 純資料與狀態轉換：標準 Python 單元測試
- Windows API：在 Windows runner 做 smoke test，並以 adapter 隔離
- GUI：使用人工 Windows 10／11 實機驗證互動與系統匣行為
- Release：CI 建置後檢查安裝檔存在、版本與 SHA-256
