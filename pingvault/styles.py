"""Deep-sea tactical HUD theme — charcoal navy, signal cyan, instrument edges."""

THEME = {
    "bg": "#05080F",
    "bg_mid": "#0A101C",
    "panel": "#0B1322",
    "panel_alt": "#0F1829",
    "border": "#1C2A44",
    "border_strong": "#2E4570",
    "text": "#E8F0FF",
    "muted": "#7E91B0",
    "muted_dim": "#53647F",
    "accent": "#2F6BFF",
    "accent_soft": "#163A8C",
    "accent_hover": "#4B82FF",
    "accent_glow": "rgba(47, 107, 255, 0.28)",
    "cyan": "#35D0FF",
    "cyan_dim": "#1A6F8A",
    "success": "#2EE59D",
    "warning": "#FFB020",
    "danger": "#FF5C6A",
    "sidebar": "#070B14",
    "grid": "rgba(53, 208, 255, 0.045)",
    "hud_line": "#243656",
}

FONT_UI = '"Bahnschrift", "Segoe UI Variable Text", "Microsoft JhengHei UI", sans-serif'
FONT_DISPLAY = '"Bahnschrift", "Segoe UI Variable Display", "Microsoft JhengHei UI", sans-serif'
FONT_DATA = '"Cascadia Mono", "Consolas", "Bahnschrift", "Microsoft JhengHei UI", monospace'

APP_STYLESHEET = f"""
QWidget {{
    background-color: transparent;
    color: {THEME["text"]};
    font-family: {FONT_UI};
    font-size: 13px;
}}

QMainWindow, QWidget#Root {{
    background-color: {THEME["bg"]};
}}

QFrame#Sidebar {{
    background-color: {THEME["sidebar"]};
    border-right: 1px solid {THEME["border"]};
}}

QFrame#HeroPanel, QFrame#ContentPanel, QFrame#ProcessPanel {{
    background-color: rgba(11, 19, 34, 0.92);
    border: 1px solid {THEME["border"]};
    border-radius: 4px;
}}

QFrame#HeroPanel {{
    border-top: 1px solid {THEME["cyan_dim"]};
}}

QFrame#HudBox {{
    background-color: rgba(15, 24, 41, 0.9);
    border: 1px solid {THEME["hud_line"]};
    border-radius: 2px;
}}

QFrame#StatStrip {{
    background-color: rgba(11, 19, 34, 0.88);
    border: 1px solid {THEME["border"]};
    border-radius: 4px;
}}

QFrame#StatChip {{
    background-color: transparent;
    border-right: 1px solid {THEME["border"]};
    border-radius: 0;
}}

QFrame#StatChip:last-child {{
    border-right: none;
}}

QLabel#Brand {{
    font-family: {FONT_DISPLAY};
    font-size: 26px;
    font-weight: 700;
    color: {THEME["text"]};
    letter-spacing: 1.2px;
}}

QLabel#BrandAccent {{
    font-family: {FONT_DISPLAY};
    font-size: 26px;
    font-weight: 700;
    color: {THEME["cyan"]};
    letter-spacing: 1.2px;
}}

QLabel#SectionTitle {{
    font-family: {FONT_DISPLAY};
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}

QLabel#HeroTitle {{
    font-family: {FONT_DISPLAY};
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.3px;
}}

QLabel#Muted {{
    color: {THEME["muted"]};
}}

QLabel#MetricValue {{
    font-family: {FONT_DATA};
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}

QLabel#MetricLabel {{
    color: {THEME["muted_dim"]};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.4px;
}}

QLabel#StatusChip {{
    border-radius: 2px;
    padding: 10px 12px;
    font-weight: 700;
    letter-spacing: 0.8px;
    border: 1px solid {THEME["border"]};
}}

QLabel#HudEyebrow {{
    color: {THEME["cyan"]};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}

QLineEdit#SearchBox {{
    background-color: rgba(15, 24, 41, 0.95);
    border: 1px solid {THEME["border"]};
    border-radius: 2px;
    padding: 11px 14px 11px 14px;
    selection-background-color: {THEME["accent"]};
    font-size: 13px;
    min-height: 20px;
    font-family: {FONT_DATA};
}}

QLineEdit#SearchBox:focus {{
    border: 1px solid {THEME["cyan"]};
    background-color: #0E1728;
}}

QPushButton#NavButton {{
    background-color: transparent;
    border: none;
    border-radius: 2px;
    text-align: left;
    padding: 12px 12px;
    color: {THEME["muted"]};
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.4px;
}}

QPushButton#NavButton:hover {{
    background-color: {THEME["panel_alt"]};
    color: {THEME["text"]};
}}

QPushButton#NavButton[active="true"] {{
    background-color: rgba(53, 208, 255, 0.06);
    color: {THEME["text"]};
    border-left: 2px solid {THEME["cyan"]};
}}

QPushButton#PrimaryButton {{
    background-color: {THEME["accent"]};
    color: white;
    border: 1px solid {THEME["accent_hover"]};
    border-radius: 2px;
    padding: 16px 20px;
    font-family: {FONT_DISPLAY};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1.6px;
}}

QPushButton#PrimaryButton:hover {{
    background-color: {THEME["accent_hover"]};
    border-color: {THEME["cyan"]};
}}

QPushButton#PrimaryButton:disabled {{
    background-color: #152036;
    color: {THEME["muted_dim"]};
    border-color: {THEME["border"]};
}}

QPushButton#GhostButton {{
    background-color: transparent;
    color: {THEME["text"]};
    border: 1px solid {THEME["border"]};
    border-radius: 2px;
    padding: 10px 14px;
    font-weight: 600;
    letter-spacing: 0.6px;
}}

QPushButton#GhostButton:hover {{
    border-color: {THEME["cyan"]};
    color: {THEME["cyan"]};
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {THEME["hud_line"]};
    border-radius: 2px;
    min-height: 28px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QProgressBar#SlimBar {{
    background-color: #121C2E;
    border: none;
    border-radius: 1px;
    text-align: center;
    color: transparent;
    max-height: 3px;
    min-height: 3px;
}}

QProgressBar#SlimBar::chunk {{
    background-color: {THEME["cyan"]};
    border-radius: 1px;
}}

QTableWidget {{
    background-color: transparent;
    border: none;
    gridline-color: {THEME["border"]};
    selection-background-color: #15213A;
    font-family: {FONT_DATA};
}}

QHeaderView::section {{
    background-color: transparent;
    color: {THEME["muted"]};
    border: none;
    border-bottom: 1px solid {THEME["border"]};
    padding: 8px;
    font-weight: 700;
    letter-spacing: 1px;
    font-size: 11px;
}}

QTableWidget::item {{
    padding: 8px;
    border-bottom: 1px solid {THEME["border"]};
}}

QListWidget {{
    background-color: rgba(15, 24, 41, 0.95);
    border: 1px solid {THEME["hud_line"]};
    border-radius: 2px;
    padding: 4px;
    outline: none;
}}

QListWidget::item {{
    padding: 5px 6px;
    border-radius: 2px;
}}

QListWidget::item:selected {{
    background-color: rgba(47, 107, 255, 0.18);
}}
"""
