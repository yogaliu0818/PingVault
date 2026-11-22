# PingVault

Windows 本機遊戲加速與效能監測工具。

PingVault 可協助調整遊戲程序優先權、降低背景程序負載，並監測延遲、網速、CPU、記憶體與溫度。

> PingVault 不是 VPN，也不會改變遊戲伺服器位置。實際延遲仍取決於 ISP 與遊戲伺服器位置。

![PingVault 加速中心](docs/images/pingvault-dashboard.png)

## 一鍵下載

[![下載 PingVault](https://img.shields.io/badge/Windows%20下載-PingVault%20Setup-blue?style=for-the-badge&logo=windows)](https://github.com/yogaliu0818/PingVault/releases/latest/download/PingVault-Setup.exe)

或前往 [最新版本 Releases](https://github.com/yogaliu0818/PingVault/releases/latest)。

## 功能

- 約 89 款主流遊戲，支援中英文與類型搜尋
- 一鍵套用遊戲加速方案
- 提高遊戲程序優先權
- 降低背景程序優先權
- 可暫停 Chrome、Edge、OneDrive 等背景程序
- DNS、計時器與高效能電源調整
- ICMP 延遲與丟包監測
- 即時上下行網速
- CPU、記憶體、磁碟與溫度監測
- 加速前後延遲／CPU／FPS 對照
- 系統匣常駐
- 異常中斷後嘗試還原系統設定

## 安裝

1. 點擊上方按鈕，進入最新版 Releases。
2. 下載 `PingVault-Setup.exe`。
3. 執行安裝程式並依照精靈完成安裝。
4. 啟動 PingVault；UAC 出現時按「是」。

PingVault 需要系統管理員權限，才能穩定調整程序優先權、DNS、計時器與電源設定。

## 使用方式

1. 開啟「加速中心」。
2. 搜尋並選擇遊戲。
3. 視需要調整背景降載與暫停程式選項。
4. 按下「BOOST」。
5. 遊戲結束後按「停止加速」。

請使用系統匣的「結束並還原」離開程式，不建議直接從工作管理員強制結束。

## FPS 顯示

FPS 需要先安裝並執行 [RivaTuner Statistics Server（RTSS）](https://www.guru3d.com/files-details/rtss-rivatuner-statistics-server-download.html)。

未安裝 RTSS 時，延遲與 CPU 對照仍可正常使用，但 FPS 會顯示為 `—`。

## 系統需求

- Windows 10 或 Windows 11
- 系統管理員權限
- FPS 顯示需要 RTSS

## 注意事項

PingVault 主要改善本機資源與網路堆疊狀態，不保證降低所有遊戲的實際延遲，也不是跨國線路加速器。

詳細操作方式請參考 [使用說明書](使用說明書.md)。

## 開發與打包

安裝開發依賴並啟動：

```bash
pip install -r requirements.txt
python main.py
```

產生 Windows 安裝程式：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

輸出位置：

```text
dist\installer\PingVault-Setup.exe
```

只產生免安裝版本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```
