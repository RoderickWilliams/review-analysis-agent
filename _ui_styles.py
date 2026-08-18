# -*- coding: utf-8 -*-
"""UI styles for ReviewPilot — light/dark theme CSS."""


def get_styles(theme: str = "light") -> str:
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {{
        --rp-brand: #6366F1; --rp-brand-2: #8B5CF6;
        --rp-grad: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%);
        --rp-glow: 0 4px 16px rgba(99,102,241,0.4);
        --rp-pos: #10B981; --rp-neu: #F59E0B; --rp-neg: #EF4444; --rp-trust: #3B82F6;
        --rp-bg:#FFFFFF; --rp-bg2:#F8F9FC; --rp-card:#FFFFFF; --rp-hover:#F1F3F9;
        --rp-text:#1A1A2E; --rp-text2:#6B7280; --rp-text3:#9CA3AF;
        --rp-border:#E5E7EB;
        --rp-shadow:0 1px 3px rgba(0,0,0,0.06),0 1px 2px rgba(0,0,0,0.04);
        --rp-shadow-float:0 8px 24px rgba(99,102,241,0.15);
        --rp-input-bg:#FFFFFF; --rp-sidebar-active:#EDE9FE;
        --rp-hero:linear-gradient(135deg,#EDE9FE 0%,#DBEAFE 50%,#E0E7FF 100%);
    }}
    [data-theme="dark"] {{
        --rp-bg:#121212; --rp-bg2:#181818; --rp-card:#1E1E1E; --rp-hover:#2A2A2A;
        --rp-text:#F3F4F6; --rp-text2:#9CA3AF; --rp-text3:#6B7280;
        --rp-border:#2D2D2D;
        --rp-shadow:0 8px 8px rgba(0,0,0,0.3);
        --rp-shadow-float:0 8px 24px rgba(0,0,0,0.5);
        --rp-input-bg:#1E1E1E; --rp-sidebar-active:#2D2040;
        --rp-hero:linear-gradient(135deg,#2D2040 0%,#1E2A4A 50%,#1A2040 100%);
    }}

    * {{ box-sizing:border-box; }}
    html,body,[class*="css"] {{
        font-family:'Inter','Microsoft YaHei','微软雅黑',-apple-system,sans-serif!important;
        -webkit-font-smoothing:antialiased;
    }}
    .stApp {{ background:var(--rp-bg)!important; color:var(--rp-text)!important; }}
    .stApp > div, .main, .block-container, section[data-testid="stSidebar"] + section,
    [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > div,
    [data-testid="stAppViewContainer"] > div > div {{ background:var(--rp-bg)!important; }}
    #MainMenu,footer,.stDeployButton {{ display:none!important; }}
    header[data-testid="stHeader"] {{
        background:var(--rp-bg)!important; border-bottom:1px solid var(--rp-border)!important;
    }}
    .block-container {{ padding-top:2.5rem!important; padding-bottom:3rem!important; max-width:1280px!important; }}

    .main h1 {{ font-size:28px!important; font-weight:700!important; color:var(--rp-text)!important;
        letter-spacing:-0.02em!important; line-height:1.3!important; margin-bottom:4px!important; }}
    .main h2 {{ font-size:22px!important; font-weight:700!important; color:var(--rp-text)!important;
        margin-top:1rem!important; margin-bottom:8px!important; }}
    .main h3 {{ font-size:18px!important; font-weight:700!important; color:var(--rp-text)!important; margin-bottom:6px!important; }}
    .main,.main .stMarkdown,.main .stMarkdown p,.main label,.main .stCaption,.main small,
    .main p,.main span,.main li {{ color:var(--rp-text2)!important; font-size:14px!important; line-height:1.6!important; }}
    .main .stMarkdown strong {{ color:var(--rp-text)!important; font-weight:700!important; }}
    .stAlert,.stAlert p,.stAlert span,.stAlert li,.stAlert strong,.stAlert div,.stAlert small,
    [data-testid="stAlert"],[data-testid="stAlert"] p,[data-testid="stAlert"] span,
    [data-testid="stAlert"] li,[data-testid="stAlert"] strong,[data-testid="stAlert"] div,
    [data-testid="stAlert"] small,[data-testid="stAlertContainer"],
    [data-testid="stAlertContainer"] p,[data-testid="stAlertContainer"] span,
    [data-testid="stAlertContainer"] li,[data-testid="stAlertContainer"] strong,
    [data-testid="stAlertContainer"] div,[data-testid="stAlertContainer"] small,
    div[data-testid="stAlert"] *,div[data-testid="stAlertContainer"] *,
    .stAlert [data-testid="stAlertContent"],.stAlert [data-testid="stAlertContent"] *,
    [data-testid="stAlert"] [data-testid="stAlertContent"],
    [data-testid="stAlert"] [data-testid="stAlertContent"] * {{
        color:#1A1A2E!important;
    }}

    .rp-card {{ background:var(--rp-card); border-radius:16px; padding:24px; margin-bottom:16px;
        box-shadow:var(--rp-shadow); transition:box-shadow .2s; }}
    .rp-card:hover {{ box-shadow:var(--rp-shadow-float); }}
    .rp-card-title {{ font-size:16px; font-weight:700; color:var(--rp-text);
        margin-bottom:16px; display:flex; align-items:center; gap:8px; }}

    .rp-metric {{ background:var(--rp-card); border-radius:12px; padding:20px;
        box-shadow:var(--rp-shadow); transition:transform .2s,box-shadow .2s; height:100%; }}
    .rp-metric:hover {{ transform:translateY(-2px); box-shadow:var(--rp-shadow-float); }}
    .rp-metric-icon {{ width:40px; height:40px; border-radius:10px; display:flex;
        align-items:center; justify-content:center; font-size:18px; margin-bottom:12px; }}
    .rp-metric-value {{ font-size:28px; font-weight:700; color:var(--rp-text); line-height:1.2; letter-spacing:-0.02em; }}
    .rp-metric-label {{ font-size:13px; color:var(--rp-text2); margin-top:4px; }}
    .rp-metric-trend {{ font-size:12px; margin-top:6px; font-weight:600; }}

    .rp-hero {{ background:var(--rp-grad); border-radius:20px; padding:32px 40px; margin-bottom:24px;
        display:flex; align-items:center; justify-content:space-between; position:relative; overflow:hidden;
        box-shadow:0 8px 32px rgba(99,102,241,0.3); }}
    .rp-hero h1 {{ font-size:22px!important; font-weight:700!important; color:#FFFFFF!important; margin-bottom:8px!important; }}
    .rp-hero p {{ font-size:14px; color:rgba(255,255,255,0.88); line-height:1.6; max-width:480px; margin:0; }}
    .rp-hero-logo {{ width:72px; height:72px; background:rgba(255,255,255,0.2); backdrop-filter:blur(8px);
        border-radius:18px; display:flex; align-items:center; justify-content:center; font-size:32px;
        box-shadow:0 8px 24px rgba(0,0,0,0.15); flex-shrink:0; }}

    .stButton>button[kind="primary"] {{
        background:var(--rp-grad)!important; border:none!important; border-radius:9999px!important;
        padding:10px 28px!important; font-weight:600!important; font-size:15px!important;
        color:#fff!important; box-shadow:var(--rp-glow)!important; transition:all .2s!important;
    }}
    .stButton>button[kind="primary"]:hover {{
        box-shadow:0 6px 20px rgba(99,102,241,0.5)!important; transform:translateY(-1px)!important;
    }}
    .stButton>button:not([kind="primary"]) {{
        border-radius:9999px!important; border:1px solid var(--rp-border)!important;
        background:var(--rp-card)!important; color:var(--rp-text)!important;
        font-weight:600!important; font-size:14px!important; padding:8px 24px!important; transition:all .2s!important;
    }}
    .stButton>button:not([kind="primary"]):hover {{
        border-color:var(--rp-brand)!important; color:var(--rp-brand)!important; background:var(--rp-hover)!important;
    }}

    .stTextInput input,.stTextArea textarea {{
        background:transparent!important; color:#1A1A2E!important;
        border:none!important; border-radius:10px!important;
        padding:10px 14px!important; font-size:14px!important;
        transition:border-color .2s,box-shadow .2s!important;
        outline:none!important;
    }}
    .stTextInput>div,.stTextArea>div {{
        background:transparent!important; border:1px solid #D1D5DB!important; border-radius:10px!important;
        box-shadow:none!important; transition:border-color .2s!important;
    }}
    .stTextInput>div>div,.stTextArea>div>div {{
        background:transparent!important; border:none!important;
    }}
    .stTextArea textarea {{ border:none!important; outline:none!important; }}
    .stTextArea>div {{ padding:4px!important; }}
    .stTextInput>div:focus-within,.stTextArea>div:focus-within {{
        border:1px solid var(--rp-brand)!important; box-shadow:0 0 0 3px rgba(99,102,241,0.12)!important;
    }}
    .stTextInput textarea:focus,.stTextArea textarea:focus {{
        outline:none!important; box-shadow:none!important;
    }}

    /* 下拉框：透明背景、黑字、无深色块（覆盖 Streamlit 外层 wrapper + BaseWeb / React Aria 内层） */
    [data-testid="stAppViewContainer"] .stSelectbox>div,
    [data-testid="stAppViewContainer"] .stSelectbox>div>div,
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"]>div,
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"]>div>div,
    .stSelectbox>div,
    .stSelectbox>div>div,
    [data-testid="stSelectbox"]>div,
    [data-testid="stSelectbox"]>div>div {{
        background:transparent!important; background-color:transparent!important;
        border:none!important; box-shadow:none!important;
    }}
    /* BaseWeb select（Streamlit 1.30–1.39） */
    [data-testid="stAppViewContainer"] .stSelectbox [data-baseweb="select"],
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [data-baseweb="select"],
    .stSelectbox [data-baseweb="select"],
    [data-testid="stSelectbox"] [data-baseweb="select"] {{
        background:transparent!important; background-color:transparent!important;
    }}
    [data-testid="stAppViewContainer"] .stSelectbox [data-baseweb="select"]>div,
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [data-baseweb="select"]>div,
    .stSelectbox [data-baseweb="select"]>div,
    [data-testid="stSelectbox"] [data-baseweb="select"]>div {{
        background:transparent!important; background-color:transparent!important;
        border:none!important; border-radius:10px!important;
        box-shadow:0 0 0 0.5px #000000!important;
        min-height:42px!important; color:#1A1A2E!important;
    }}
    [data-testid="stAppViewContainer"] .stSelectbox [data-baseweb="select"]>div>div,
    [data-testid="stAppViewContainer"] .stSelectbox [data-baseweb="select"]>div>div>div,
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [data-baseweb="select"]>div>div,
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [data-baseweb="select"]>div>div>div,
    .stSelectbox [data-baseweb="select"]>div>div,
    .stSelectbox [data-baseweb="select"]>div>div>div,
    [data-testid="stSelectbox"] [data-baseweb="select"]>div>div,
    [data-testid="stSelectbox"] [data-baseweb="select"]>div>div>div {{
        background:transparent!important; background-color:transparent!important;
        border:none!important; box-shadow:none!important; color:#1A1A2E!important;
    }}
    /* React Aria ComboBox（Streamlit 1.40+） */
    [data-testid="stAppViewContainer"] .stSelectbox [role="group"],
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [role="group"],
    .stSelectbox [role="group"],
    [data-testid="stSelectbox"] [role="group"] {{
        background:transparent!important; background-color:transparent!important;
        border:none!important; border-radius:10px!important;
        box-shadow:0 0 0 0.5px #000000!important;
        min-height:42px!important; color:#1A1A2E!important;
    }}
    [data-testid="stAppViewContainer"] .stSelectbox [role="group"]:focus-within,
    [data-testid="stAppViewContainer"] .stSelectbox [role="group"][data-focus-within],
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [role="group"]:focus-within,
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [role="group"][data-focus-within],
    .stSelectbox [role="group"]:focus-within,
    .stSelectbox [role="group"][data-focus-within],
    [data-testid="stSelectbox"] [role="group"]:focus-within,
    [data-testid="stSelectbox"] [role="group"][data-focus-within] {{
        box-shadow:0 0 0 0.5px var(--rp-brand),0 0 0 3px rgba(99,102,241,0.15)!important;
    }}
    [data-testid="stAppViewContainer"] .stSelectbox input,
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] input,
    .stSelectbox input,
    [data-testid="stSelectbox"] input {{
        background:transparent!important; background-color:transparent!important;
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
        border:none!important; box-shadow:none!important;
    }}
    [data-testid="stAppViewContainer"] .stSelectbox [role="group"] button,
    [data-testid="stAppViewContainer"] [data-testid="stSelectbox"] [role="group"] button,
    .stSelectbox [role="group"] button,
    [data-testid="stSelectbox"] [role="group"] button {{
        background:transparent!important; background-color:transparent!important;
        color:#1A1A2E!important; border:none!important; box-shadow:none!important;
    }}
    .stSelectbox [data-baseweb="select"] [data-baseweb="select-arrow"],
    [data-testid="stSelectbox"] [data-baseweb="select"] [data-baseweb="select-arrow"] {{
        background:transparent!important; border:none!important; min-height:auto!important;
    }}
    .stSelectbox [data-baseweb="select"]>div:focus-within,
    [data-testid="stSelectbox"] [data-baseweb="select"]>div:focus-within {{
        box-shadow:0 0 0 0.5px var(--rp-brand),0 0 0 3px rgba(99,102,241,0.15)!important;
    }}
    .stSelectbox [data-baseweb="select"] svg,
    [data-testid="stSelectbox"] [data-baseweb="select"] svg,
    .stSelectbox [role="group"] svg,
    [data-testid="stSelectbox"] [role="group"] svg {{
        fill:#1A1A2E!important; color:#1A1A2E!important;
    }}
    .stSelectbox label,
    .stSelectbox [data-baseweb="select"] span,
    .stSelectbox [data-baseweb="select"] div,
    .stSelectbox [role="group"] span,
    .stSelectbox [role="group"] div,
    [data-testid="stSelectbox"] label,
    [data-testid="stSelectbox"] [data-baseweb="select"] span,
    [data-testid="stSelectbox"] [data-baseweb="select"] div,
    [data-testid="stSelectbox"] [role="group"] span,
    [data-testid="stSelectbox"] [role="group"] div {{
        color:#1A1A2E!important;
    }}

    /* 数字输入框：透明背景、黑字、无深色块 —— 强力覆盖所有可能的 DOM 层级 */
    .stNumberInput,
    [data-testid="stNumberInput"],
    .stNumberInput *,
    [data-testid="stNumberInput"] * {{
        background-color:transparent!important; background:transparent!important;
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
    }}
    .stNumberInput input,
    [data-testid="stNumberInput"] input {{
        background-color:transparent!important; background:transparent!important;
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
        border:none!important; box-shadow:none!important;
    }}
    .stNumberInput [data-baseweb="input"],
    [data-testid="stNumberInput"] [data-baseweb="input"],
    .stNumberInput [data-baseweb="base-input"],
    [data-testid="stNumberInput"] [data-baseweb="base-input"] {{
        background-color:transparent!important; background:transparent!important;
        border:none!important; border-radius:10px!important;
        box-shadow:0 0 0 0.5px #000000!important;
    }}
    .stNumberInput [data-baseweb="input"]>div,
    [data-testid="stNumberInput"] [data-baseweb="input"]>div,
    .stNumberInput [data-baseweb="base-input"]>div,
    [data-testid="stNumberInput"] [data-baseweb="base-input"]>div {{
        background-color:transparent!important; background:transparent!important;
        border:none!important;
    }}
    .stNumberInput button,
    [data-testid="stNumberInput"] button,
    .stNumberInput [data-baseweb="spinbutton"],
    [data-testid="stNumberInput"] [data-baseweb="spinbutton"] {{
        background:transparent!important; background-color:transparent!important;
        color:#1A1A2E!important; border:none!important; box-shadow:none!important;
    }}
    .stNumberInput button:hover,
    [data-testid="stNumberInput"] button:hover {{
        background:rgba(99,102,241,0.08)!important;
    }}
    .stNumberInput button svg,
    [data-testid="stNumberInput"] button svg,
    .stNumberInput svg,
    [data-testid="stNumberInput"] svg {{
        fill:#1A1A2E!important; color:#1A1A2E!important;
    }}

    /* 复选框：透明背景、无深色块、勾选后黑色对勾 */
    .stCheckbox,
    [data-testid="stCheckbox"],
    .stCheckbox *,
    [data-testid="stCheckbox"] * {{
        background:transparent!important; background-color:transparent!important;
    }}
    .stCheckbox label,
    [data-testid="stCheckbox"] label,
    .stCheckbox [data-baseweb="checkbox"] span,
    [data-testid="stCheckbox"] [data-baseweb="checkbox"] span,
    .stCheckbox span,
    [data-testid="stCheckbox"] span {{
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
    }}
    /* 复选框方框 */
    .stCheckbox [data-baseweb="checkbox"] [data-baseweb="checkmark"],
    [data-testid="stCheckbox"] [data-baseweb="checkbox"] [data-baseweb="checkmark"],
    .stCheckbox div[role="checkbox"],
    [data-testid="stCheckbox"] div[role="checkbox"],
    .stCheckbox [class*="checkbox"] [class*="box"],
    [data-testid="stCheckbox"] [class*="checkbox"] [class*="box"] {{
        background:transparent!important; background-color:transparent!important;
        border:1.5px solid #1A1A2E!important; border-radius:4px!important;
        box-shadow:none!important;
    }}
    /* 勾选状态：透明背景 + 黑色边框 */
    .stCheckbox [data-baseweb="checkbox"] input:checked + [data-baseweb="checkmark"],
    [data-testid="stCheckbox"] [data-baseweb="checkbox"] input:checked + [data-baseweb="checkmark"],
    .stCheckbox div[role="checkbox"][aria-checked="true"],
    [data-testid="stCheckbox"] div[role="checkbox"][aria-checked="true"] {{
        background:transparent!important; background-color:transparent!important;
        border-color:#1A1A2E!important;
    }}
    /* 黑色对勾 —— 覆盖所有可能的伪元素和 SVG */
    .stCheckbox [data-baseweb="checkbox"] input:checked + [data-baseweb="checkmark"]::after,
    [data-testid="stCheckbox"] [data-baseweb="checkbox"] input:checked + [data-baseweb="checkmark"]::after {{
        content:"✓"!important; display:block!important; color:#1A1A2E!important;
        font-size:12px!important; font-weight:700!important; line-height:1!important;
        text-align:center!important; width:100%!important; height:100%!important;
    }}
    .stCheckbox div[role="checkbox"][aria-checked="true"]::after,
    [data-testid="stCheckbox"] div[role="checkbox"][aria-checked="true"]::after {{
        content:"✓"!important; display:block!important; color:#1A1A2E!important;
        font-size:12px!important; font-weight:700!important; line-height:1!important;
        text-align:center!important; width:100%!important; height:100%!important;
    }}
    .stCheckbox svg,
    [data-testid="stCheckbox"] svg {{
        fill:#1A1A2E!important; color:#1A1A2E!important;
    }}
    .stSelectbox [data-baseweb="popover"],
    .stSelectbox ul,
    .stSelectbox [role="listbox"],
    [data-testid="stSelectboxVirtualDropdown"],
    [data-testid="stSelectbox"] [role="listbox"] {{
        background:var(--rp-card)!important; border:1px solid var(--rp-border)!important;
        border-radius:10px!important; box-shadow:var(--rp-shadow-float)!important;
    }}
    .stSelectbox li,
    .stSelectbox [role="option"],
    [data-testid="stSelectboxVirtualDropdown"] li,
    [data-testid="stSelectboxVirtualDropdown"] [role="option"],
    .stSelectbox [role="listbox"] li,
    .stSelectbox [role="listbox"] [role="option"] {{
        color:#1A1A2E!important; border-radius:6px!important; font-size:14px!important;
        -webkit-text-fill-color:#1A1A2E!important;
    }}
    .stSelectbox li *,
    .stSelectbox [role="option"] *,
    [data-testid="stSelectboxVirtualDropdown"] li *,
    [data-testid="stSelectboxVirtualDropdown"] [role="option"] * {{
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
    }}
    .stSelectbox li:hover,
    .stSelectbox [role="option"]:hover,
    .stSelectbox [role="option"][data-hovered],
    .stSelectbox [role="option"][data-focused],
    [data-testid="stSelectboxVirtualDropdown"] li:hover,
    [data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
    [data-testid="stSelectboxVirtualDropdown"] [role="option"][data-hovered],
    [data-testid="stSelectboxVirtualDropdown"] [role="option"][data-focused],
    .stSelectbox [aria-selected="true"],
    .stSelectbox [role="option"][aria-selected="true"] {{
        background:var(--rp-hover)!important; color:#1A1A2E!important;
        -webkit-text-fill-color:#1A1A2E!important;
    }}

    .stTextInput label,.stTextArea label,.stSelectbox label,.stNumberInput label,
    .stCheckbox label,.stFileUploader label {{
        color:var(--rp-text)!important; font-size:14px!important; font-weight:600!important; margin-bottom:6px!important;
    }}

    .stFileUploader>section {{
        background:var(--rp-card)!important; border:2px dashed var(--rp-brand)!important;
        border-radius:12px!important; padding:28px!important; transition:all .2s!important;
    }}
    .stFileUploader>section:hover {{ border-color:var(--rp-brand-2)!important; background:var(--rp-hover)!important; }}
    .stFileUploader p,.stFileUploader span {{ color:var(--rp-text2)!important; }}
    .stFileUploader button, .stFileUploader [data-testid="stFileUploaderDropzone"] button {{
        background:var(--rp-grad)!important; color:#FFFFFF!important; border:none!important;
        border-radius:9999px!important; font-weight:600!important; padding:8px 20px!important;
        box-shadow:var(--rp-glow)!important;
    }}
    .stFileUploader button *, .stFileUploader [data-testid="stFileUploaderDropzone"] button *,
    .stFileUploader button span, .stFileUploader [data-testid="stFileUploaderDropzone"] button span,
    .stFileUploader button p, .stFileUploader [data-testid="stFileUploaderDropzone"] button p,
    .stFileUploader button div, .stFileUploader [data-testid="stFileUploaderDropzone"] button div {{
        color:#FFFFFF!important; -webkit-text-fill-color:#FFFFFF!important;
    }}

    .stDataFrame {{ background:#FFFFFF!important; border-radius:12px; box-shadow:var(--rp-shadow); overflow:hidden;
        border:1px solid var(--rp-border)!important; }}
    /* DataFrame 内部网格强制白色背景 */
    .stDataFrame [data-testid="stDataFrame"],
    .stDataFrame [data-testid="stDataFrameResizeHandle"],
    .stDataFrame [class*="glide"],
    .stDataFrame [class*="grid"],
    .stDataFrame [class*="cell"],
    .stDataFrame [class*="header"],
    .stDataFrame [class*="row"],
    .stDataFrame [class*="container"],
    .stDataFrame [class*="viewport"],
    .stDataFrame [class*="canvas"],
    .stDataFrame canvas,
    .stDataFrame div,
    .stDataFrame section {{
        background:#FFFFFF!important; background-color:#FFFFFF!important;
        color:#1A1A2E!important;
    }}
    /* stTable 静态表格 — 强制白色背景 + 深色文字 */
    [data-testid="stTable"], .stTable,
    [data-testid="stTable"] *, .stTable *,
    [data-testid="stTable"] table.dataframe, .stTable table.dataframe,
    [data-testid="stTable"] .dataframe, .stTable .dataframe {{
        background:#FFFFFF!important; background-color:#FFFFFF!important;
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
    }}
    /* 表格容器：限制宽度并允许横向滚动，防止撑破布局 */
    [data-testid="stTable"], .stTable {{
        overflow-x:auto!important; max-width:100%!important; display:block!important;
    }}
    [data-testid="stTable"] table, .stTable table,
    [data-testid="stTable"] thead, .stTable thead,
    [data-testid="stTable"] tbody, .stTable tbody,
    [data-testid="stTable"] tr, .stTable tr,
    [data-testid="stTable"] th, .stTable th,
    [data-testid="stTable"] td, .stTable td {{
        background:#FFFFFF!important; background-color:#FFFFFF!important;
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
        border-color:#E5E7EB!important;
        white-space:nowrap!important;
    }}
    /* 表头略深背景 */
    [data-testid="stTable"] thead th, .stTable thead th,
    [data-testid="stTable"] th, .stTable th {{
        background:#F8F9FC!important; background-color:#F8F9FC!important;
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
        font-weight:600!important;
    }}
    /* 行悬停效果 */
    [data-testid="stTable"] tbody tr:hover, .stTable tbody tr:hover {{
        background:#F1F3F9!important; background-color:#F1F3F9!important;
    }}
    .stProgress>div>div>div>div {{ background:var(--rp-grad)!important; border-radius:9999px; }}
    .stAlert {{ border-radius:12px!important; border:none!important; box-shadow:var(--rp-shadow)!important; }}

    .stTabs [data-baseweb="tab-list"] {{ gap:24px; background:transparent;
        border-bottom:1px solid var(--rp-border)!important; margin-bottom:24px; }}
    .stTabs [data-baseweb="tab"] {{ padding:10px 2px!important; font-weight:600!important;
        font-size:14px!important; color:var(--rp-text2)!important; background:transparent!important;
        border:none!important; border-bottom:2px solid transparent!important; }}
    .stTabs [aria-selected="true"] {{ color:var(--rp-brand)!important; border-bottom:2px solid var(--rp-brand)!important; }}

    section[data-testid="stSidebar"] {{
        background:var(--rp-bg2)!important; border-right:1px solid var(--rp-border)!important;
    }}
    section[data-testid="stSidebar"] > div:first-child {{ padding-top:0px!important; }}
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top:0px!important; gap:0!important; }}
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] > div:first-child {{ margin-top:0!important; padding-top:4px!important; }}
    section[data-testid="stSidebar"] * {{ color:var(--rp-text2)!important; }}
    section[data-testid="stSidebar"] h1,section[data-testid="stSidebar"] h2,section[data-testid="stSidebar"] h3 {{
        color:var(--rp-text)!important; font-weight:700!important;
    }}
    section[data-testid="stSidebar"] hr {{ border-color:var(--rp-border)!important; margin:12px 0!important; }}
    section[data-testid="stSidebar"] .stSelectbox>div>div,
    section[data-testid="stSidebar"] .stTextInput>div>div>input,
    section[data-testid="stSidebar"] .stTextArea>div>div>textarea {{
        background:var(--rp-card)!important; border:1px solid var(--rp-border)!important;
        color:var(--rp-text)!important; border-radius:10px!important;
    }}
    section[data-testid="stSidebar"] .stButton>button {{
        background:var(--rp-card)!important; border:1px solid var(--rp-border)!important;
        color:var(--rp-text)!important; border-radius:10px!important;
        font-weight:500!important; padding:9px 16px!important; justify-content:flex-start!important;
    }}
    section[data-testid="stSidebar"] .stButton>button:hover {{
        border-color:var(--rp-brand)!important; color:var(--rp-brand)!important; background:var(--rp-hover)!important;
    }}
    section[data-testid="stSidebar"] .stExpander {{
        background:var(--rp-card)!important; border:1px solid var(--rp-border)!important; border-radius:12px!important;
    }}

    .stDownloadButton>button {{
        border-radius:9999px!important; border:1px solid var(--rp-border)!important;
        background:var(--rp-card)!important; color:var(--rp-text)!important;
        font-weight:600!important; padding:8px 24px!important;
    }}
    .stDownloadButton>button:hover {{ border-color:var(--rp-brand)!important; color:var(--rp-brand)!important; }}

    .stCodeBlock,pre {{ background:#F8F9FC!important; border:1px solid var(--rp-border)!important;
        border-radius:10px!important; padding:14px 18px!important; }}
    code {{ color:#6B21A8!important; background:#F1F3F9!important;
        padding:2px 6px!important; border-radius:6px!important; }}
    pre code {{ color:#1A1A2E!important; background:transparent!important;
        font-size:13px!important; line-height:1.6!important; }}
    /* stCodeBlock 内部容器 */
    .stCodeBlock div, .stCodeBlock span {{
        background:#F8F9FC!important; background-color:#F8F9FC!important;
        color:#1A1A2E!important;
    }}
    /* stCodeBlock 语法高亮 */
    .stCodeBlock .token-key, .stCodeBlock .token-property {{
        color:#0066CC!important;
    }}
    .stCodeBlock .token-string, .stCodeBlock .token-string-2 {{
        color:#008000!important;
    }}
    .stCodeBlock .token-number {{
        color:#CC6600!important;
    }}
    .stCodeBlock .token-boolean {{
        color:#8B0000!important;
    }}
    .stCodeBlock .token-null {{
        color:#666666!important;
    }}
    .stCodeBlock .token-punctuation {{
        color:#999999!important;
    }}

    /* JSON 查看器：强制白色背景、深色文字 —— 全覆盖 */
    .stJson,
    [data-testid="stJson"],
    .stJson *,
    [data-testid="stJson"] *,
    [data-testid="stJson"] div,
    [data-testid="stJson"] span,
    [data-testid="stJson"] pre,
    [data-testid="stJson"] code,
    .react-json-view,
    .react-json-view *,
    [class*="json-view"],
    [class*="json-view"] *,
    [class*="JSONView"],
    [class*="JSONView"] *,
    [class*="json-tree"],
    [class*="json-tree"] *,
    [class*="object-key"],
    [class*="object-value"],
    [class*="variable-row"],
    [class*="object-container"],
    [class*="not-editable"] {{
        background:#FFFFFF!important; background-color:#FFFFFF!important;
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important;
    }}
    /* JSON 语法高亮：在白色背景上使用醒目颜色 */
    .stJson [class*="key"],
    [data-testid="stJson"] [class*="key"],
    [class*="object-key"] {{
        color:#0066CC!important; -webkit-text-fill-color:#0066CC!important;
    }}
    .stJson [class*="string"],
    [data-testid="stJson"] [class*="string"],
    [class*="object-value"],
    [class*="string-value"] {{
        color:#008000!important; -webkit-text-fill-color:#008000!important;
    }}
    .stJson [class*="number"],
    [data-testid="stJson"] [class*="number"],
    [class*="number-value"] {{
        color:#CC6600!important; -webkit-text-fill-color:#CC6600!important;
    }}
    .stJson [class*="boolean"],
    [data-testid="stJson"] [class*="boolean"],
    [class*="boolean-value"] {{
        color:#8B0000!important; -webkit-text-fill-color:#8B0000!important;
    }}
    .stJson [class*="null"],
    [data-testid="stJson"] [class*="null"],
    [class*="null-value"] {{
        color:#666666!important; -webkit-text-fill-color:#666666!important;
    }}
    /* JSON 折叠箭头和图标 */
    .stJson svg,
    [data-testid="stJson"] svg,
    .react-json-view svg {{
        fill:#6B7280!important; color:#6B7280!important;
    }}
    /* JSON 中的引号和括号 */
    .stJson [class*="punctuation"],
    [data-testid="stJson"] [class*="punctuation"] {{
        color:#999999!important;
    }}
    /* JSON 行间距和缩进 */
    .stJson div, [data-testid="stJson"] div,
    .react-json-view div {{
        line-height:1.6!important; padding:1px 0!important;
    }}

    .stExpander {{ background:var(--rp-card)!important; border:1px solid var(--rp-border)!important;
        border-radius:12px!important; box-shadow:var(--rp-shadow)!important; overflow:hidden; }}
    .stExpander summary {{ padding:16px 20px!important; font-weight:600!important;
        color:var(--rp-text)!important; font-size:14px!important; }}
    .stExpander [data-testid="stExpanderDetails"] {{ padding:0 20px 20px 20px!important; }}

    [data-testid="stMetric"] {{ background:var(--rp-card); border-radius:12px; padding:18px 22px; box-shadow:var(--rp-shadow); }}
    [data-testid="stMetricValue"] {{ font-size:26px!important; font-weight:700!important; color:var(--rp-text)!important; }}
    [data-testid="stMetricLabel"] {{ color:var(--rp-text2)!important; font-size:12px!important; }}
    .stJson {{ background:#FFFFFF!important; background-color:#FFFFFF!important;
        border-radius:10px!important; padding:14px!important;
        border:1px solid var(--rp-border)!important;
        color:#1A1A2E!important; -webkit-text-fill-color:#1A1A2E!important; }}

    .rp-page-title {{ font-size:28px; font-weight:700; color:var(--rp-text); margin-bottom:4px; letter-spacing:-0.02em; }}
    .rp-page-subtitle {{ font-size:14px; color:#1A1A2E!important; margin-bottom:24px; line-height:1.5; }}

    .rp-badge {{ display:inline-flex; align-items:center; gap:4px; padding:3px 10px;
        border-radius:9999px; font-size:12px; font-weight:600; }}
    .rp-badge-pos {{ background:#D1FAE5; color:#065F46; }}
    .rp-badge-neu {{ background:#FEF3C7; color:#92400E; }}
    .rp-badge-neg {{ background:#FEE2E2; color:#991B1B; }}
    .rp-badge-brand {{ background:#EDE9FE; color:#5B21B6; }}

    .rp-ethics {{ background:var(--rp-grad); border-radius:14px; padding:16px 22px; margin-bottom:20px; margin-top:8px;
        font-size:13px; color:rgba(255,255,255,0.92); line-height:1.6;
        box-shadow:0 6px 24px rgba(99,102,241,0.25); display:flex; align-items:center; gap:10px;
        border:none; overflow:visible; }}
    .rp-ethics strong {{ color:#FFFFFF!important; font-weight:700!important; }}

    .rp-sidebar-brand {{ display:flex; align-items:center; gap:12px; padding:8px 4px 8px 4px; margin:0!important; }}
    .rp-sidebar-logo {{ width:40px; height:40px; background:var(--rp-grad); border-radius:10px;
        display:flex; align-items:center; justify-content:center; font-size:18px;
        box-shadow:var(--rp-glow); flex-shrink:0; }}
    .rp-sidebar-name {{ font-size:18px; font-weight:700; color:var(--rp-text)!important; }}
    .rp-sidebar-version {{ font-size:11px; color:var(--rp-text3)!important; }}

    .rp-nav-group {{ font-size:11px!important; font-weight:700!important; color:var(--rp-text3)!important;
        text-transform:uppercase; letter-spacing:0.06em; padding:12px 14px 6px; }}

    .rp-donut-wrap {{ display:flex; align-items:center; gap:32px; justify-content:center; padding:16px 0; }}
    .rp-donut {{ width:200px; height:200px; border-radius:50%; position:relative; flex-shrink:0; }}
    .rp-donut-hole {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
        width:110px; height:110px; border-radius:50%; background:var(--rp-card);
        display:flex; flex-direction:column; align-items:center; justify-content:center; }}
    .rp-donut-value {{ font-size:28px; font-weight:700; color:var(--rp-text); }}
    .rp-donut-label {{ font-size:13px; color:var(--rp-text2); }}
    .rp-legend {{ display:flex; flex-direction:column; gap:8px; }}
    .rp-legend-item {{ display:flex; align-items:center; gap:8px; font-size:13px; color:var(--rp-text2); }}
    .rp-legend-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
    .rp-legend-pct {{ margin-left:auto; font-weight:600; color:var(--rp-text); }}

    .rp-recent-item {{ display:flex; align-items:center; gap:12px; padding:12px 0;
        border-bottom:1px solid var(--rp-border); transition:background .15s; border-radius:8px; }}
    .rp-recent-item:hover {{ background:var(--rp-hover)!important; }}
    .rp-recent-item:last-child {{ border-bottom:none; }}
    .rp-recent-icon {{ width:40px; height:40px; border-radius:10px; display:flex;
        align-items:center; justify-content:center; font-size:18px; flex-shrink:0; }}
    .rp-recent-title {{ font-size:14px; font-weight:600; color:var(--rp-text); }}
    .rp-recent-meta {{ font-size:12px; color:var(--rp-text3); margin-top:2px; }}
    .rp-recent-right {{ margin-left:auto; text-align:right; flex-shrink:0; }}
    .rp-recent-score {{ font-size:14px; font-weight:700; }}
    .rp-recent-time {{ font-size:11px; color:var(--rp-text3); margin-top:2px; }}

    ::-webkit-scrollbar {{ width:8px; height:8px; }}
    ::-webkit-scrollbar-track {{ background:transparent; }}
    ::-webkit-scrollbar-thumb {{ background:var(--rp-border); border-radius:4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background:var(--rp-text3); }}
    ::selection {{ background:rgba(99,102,241,0.2); }}
    </style>
    """
