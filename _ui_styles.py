# -*- coding: utf-8 -*-
"""Intercom-inspired presentation layer for ReviewPilot."""


def get_styles(theme: str = "light") -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

    :root {
        --rp-canvas:#f5f1ec; --rp-surface:#ffffff; --rp-surface-2:#ebe7e1;
        --rp-ink:#111111; --rp-muted:#626260; --rp-subtle:#8a8782;
        --rp-line:#d3cec6; --rp-line-soft:#e7e2dc; --rp-orange:#ff5600;
        --rp-blue:#65b5ff; --rp-green:#12b76a; --rp-amber:#f79009;
        --rp-red:#d92d20; --rp-purple:#7a5af8;
    }

    * { box-sizing:border-box; }
    html, body, [class*="css"] {
        font-family:'Inter','PingFang SC','Microsoft YaHei',system-ui,sans-serif !important;
        -webkit-font-smoothing:antialiased;
    }
    .stApp, .main, [data-testid="stAppViewContainer"], .block-container {
        background:var(--rp-canvas) !important; color:var(--rp-ink) !important;
    }
    #MainMenu, footer, .stDeployButton { display:none !important; }
    header[data-testid="stHeader"] {
        background:rgba(245,241,236,.92) !important; border-bottom:1px solid var(--rp-line-soft) !important;
        backdrop-filter:blur(12px);
    }
    .block-container { max-width:1280px !important; padding:2.25rem 2.5rem 4rem !important; }
    .main h1, .main h2, .main h3, .main strong { color:var(--rp-ink) !important; }
    .main h1 { font-size:36px !important; font-weight:500 !important; letter-spacing:-1.2px !important; }
    .main h2 { font-size:28px !important; font-weight:500 !important; letter-spacing:-.6px !important; }
    .main h3 { font-size:18px !important; font-weight:500 !important; }
    .main p, .main label, .main li, .main small, .stCaption { color:var(--rp-muted) !important; }

    section[data-testid="stSidebar"] { width:248px !important;min-width:248px !important;height:100vh;background:var(--rp-canvas) !important;border-right:1px solid rgba(0,0,0,.06) !important;font-family:Inter,'PingFang SC','Microsoft YaHei',system-ui,sans-serif; }
    section[data-testid="stSidebar"] > div { background:var(--rp-canvas) !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] { height:100vh;padding:0 !important;box-sizing:border-box;overflow-y:auto !important;scrollbar-width:none !important;display:flex !important;flex-direction:column !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"]::-webkit-scrollbar { display:none !important;width:0 !important;height:0 !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] { flex:0 0 auto !important;height:auto !important;padding:8px 16px 0 !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { flex:1 0 auto !important;min-height:0 !important;padding:0 14px 16px !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div { height:100% !important;display:flex !important;flex-direction:column !important; }
    /* 隐藏侧边栏所有滚动条 */
    section[data-testid="stSidebar"] * { scrollbar-width:none !important; }
    section[data-testid="stSidebar"] *::-webkit-scrollbar { display:none !important;width:0 !important;height:0 !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > div[data-testid="stVerticalBlock"] { flex:1 1 0% !important;min-height:0 !important;display:flex !important;flex-direction:column !important;gap:0 !important;padding-top:0 !important;margin-top:0 !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] > div { flex-shrink:0 !important; }
    section[data-testid="stSidebar"] :is(.st-key-sidebar_analysis,.st-key-sidebar_records) { display:flex !important;flex-direction:column !important;gap:6px !important;height:auto !important; }
    section[data-testid="stSidebar"] .st-key-sidebar_records { margin-top:26px !important; }
    section[data-testid="stSidebar"] :is(.st-key-sidebar_analysis,.st-key-sidebar_records) [data-testid="stMarkdownContainer"] { min-height:26px !important;overflow:visible !important; }
    /* 强制第一个子元素（品牌区）顶部无间距 */
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > div[data-testid="stVerticalBlock"] > div:first-child { padding-top:0 !important;margin-top:0 !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > div[data-testid="stVerticalBlock"] > div:first-child > div { padding-top:0 !important;margin-top:0 !important; }
    .rp-sidebar-brand { align-self:flex-start;height:48px;display:flex;align-items:center;gap:11px;padding:0;margin:10px 0 26px !important; }
    .rp-sidebar-logo {
        width:40px;height:40px;display:flex;align-items:center;justify-content:center;flex:0 0 40px;
        background:var(--rp-ink);color:white;border-radius:10px;font-size:13px;font-weight:600;overflow:hidden;
    }
    .rp-sidebar-logo img { display:block;width:100%;height:100%;object-fit:cover;transform:scale(1.49); }
    .rp-sidebar-name { color:var(--rp-ink);font-size:16px;font-weight:650;letter-spacing:-.25px;line-height:1.15; }
    .rp-sidebar-version { color:#8a8580;font-size:11.5px;margin-top:2px;line-height:1.2; }
    .rp-nav-label { display:block;color:#a09b95;font-size:10px;font-weight:550;letter-spacing:.06em;line-height:18px;min-height:18px;padding:0;margin:0 0 8px 10px;text-transform:uppercase; }
    .rp-nav-label-data { margin-top:20px; }
    section[data-testid="stSidebar"] :is(.stButton,[data-testid="stButton"]) { margin:0 !important; }
    section[data-testid="stSidebar"] :is(.stButton,[data-testid="stButton"]) > button {
        width:100%;height:40px;min-height:40px;display:flex;justify-content:flex-start;align-items:center;gap:10px;padding:0 10px !important;
        border:1px solid transparent !important;border-radius:8px !important;background:transparent !important;
        color:#66615d !important;box-shadow:none !important;font-size:13.5px !important;font-weight:450 !important;text-align:left;
        transition:background 140ms ease,color 140ms ease !important;transform:none !important;
    }
    section[data-testid="stSidebar"] :is(.stButton,[data-testid="stButton"]) > button > div { justify-content:flex-start !important;gap:10px; }
    section[data-testid="stSidebar"] :is(.stButton,[data-testid="stButton"]) > button p { color:inherit !important;font-size:inherit !important;font-weight:inherit !important;text-align:left;white-space:nowrap; }
    section[data-testid="stSidebar"] :is(.stButton,[data-testid="stButton"]) > button span[data-testid="stIconMaterial"] { width:17px;flex:0 0 17px;font-size:17px !important;color:inherit !important; }
    section[data-testid="stSidebar"] :is(.stButton,[data-testid="stButton"]) > button:hover { background:rgba(0,0,0,.035) !important;border-color:transparent !important;color:var(--rp-ink) !important; }
    section[data-testid="stSidebar"] :is(.stButton,[data-testid="stButton"]) > button:is([kind="primary"],[data-testid="stBaseButton-primary"]) { background:#eeece8 !important;border:1px solid transparent !important;color:var(--rp-ink) !important;font-weight:550 !important;box-shadow:none !important; }
    section[data-testid="stSidebar"] button:focus-visible { outline:2px solid var(--rp-orange) !important;outline-offset:2px;box-shadow:none !important; }
    .st-key-sidebar_footer { margin-top:auto !important;padding-top:24px !important;padding-bottom:0 !important;gap:0 !important; }
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has(.st-key-sidebar_footer) { margin-top:auto !important; }
    .rp-sidebar-divider { height:1px;background:rgba(0,0,0,.07);margin:14px 0; }
    .st-key-language_switcher { position:static !important;width:100% !important;margin:0 !important; }
    .st-key-language_switcher [data-testid="stSegmentedControl"] { margin:0; }
    .st-key-language_switcher :is([data-testid="stSegmentedControl"] > div,[role="radiogroup"]) { display:flex;width:100%;min-height:34px;box-sizing:border-box;padding:2px;background:#eeece8;border:1px solid #ddd9d4;border-radius:8px;box-shadow:none;gap:2px; }
    .st-key-language_switcher button { flex:1;min-width:0 !important;width:auto !important;height:28px;min-height:28px;padding:0 10px;border:0!important;border-radius:6px!important;background:transparent!important;color:#77726d!important;font-size:12px!important;box-shadow:none!important; }
    .st-key-language_switcher [data-testid="stButtonGroup"] { width:100% !important; }
    .st-key-language_switcher [data-testid="stButtonGroup"] > div { display:flex !important;width:100% !important; }
    .st-key-language_switcher button { flex:1 0 84px !important;min-width:84px !important; }
    .st-key-language_switcher button > div { min-width:0 !important;width:auto !important;max-width:none !important;overflow:visible !important; }
    .st-key-language_switcher button :is(p,span,[data-testid="stMarkdownContainer"]) { max-width:none !important;overflow:visible !important;text-overflow:clip !important;white-space:nowrap !important; }
    .st-key-language_switcher button p { font-size:12px !important;color:inherit !important; }
    .st-key-language_switcher button:is([aria-checked="true"],[aria-pressed="true"]) { background:#fff!important;color:var(--rp-ink)!important;box-shadow:0 1px 2px rgba(0,0,0,.06)!important; }
    .rp-sidebar-version-row { display:flex;align-items:center;justify-content:space-between;padding:0 6px;color:#77726d;font-size:12px;line-height:1.4;font-weight:400; }
    .rp-sidebar-version-row span:last-child { color:#aaa59f;font-size:11px; }

    .rp-hero {
        display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:32px;
        position:relative;overflow:hidden;padding:42px 0 38px;margin-bottom:30px;border-bottom:1px solid var(--rp-line);
        animation:rp-rise .65s cubic-bezier(.2,.8,.2,1) both;
    }
    .rp-hero::after { content:"";position:absolute;right:4%;top:4px;width:170px;height:170px;border-radius:50%;background:radial-gradient(circle,rgba(255,86,0,.11),rgba(255,86,0,0) 70%);pointer-events:none;animation:rp-breathe 5s ease-in-out infinite; }
    .rp-hero h1 { margin:0 0 12px !important;font-size:48px !important;line-height:1.05 !important;font-weight:500 !important;letter-spacing:-2px !important; }
    .rp-hero p { margin:0;max-width:720px;color:var(--rp-muted);font-size:16px;line-height:1.6; }
    .rp-hero-mark { position:relative;z-index:1;color:var(--rp-orange);font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding-bottom:4px; }
    .rp-page-title { color:var(--rp-ink);font-size:34px;font-weight:500;line-height:1.15;letter-spacing:-1.1px;margin-top:16px; }
    .rp-page-subtitle { color:var(--rp-muted);font-size:14px;line-height:1.6;margin:8px 0 28px;padding-bottom:22px;border-bottom:1px solid var(--rp-line); }
    .rp-section-title, .rp-card-title { color:var(--rp-ink);font-size:15px;font-weight:600;margin:30px 0 12px;padding-top:18px;border-top:1px solid var(--rp-line); }
    .rp-guide-overview { display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin:32px 0 14px; }
    .rp-guide-overview > div { --guide-accent:#ff5600;position:relative;isolation:isolate;overflow:hidden;min-height:164px;background:var(--rp-surface);border:1px solid var(--rp-line);border-radius:14px;padding:22px;display:flex;flex-direction:column;box-shadow:0 8px 26px rgba(17,17,17,.035);transition:transform .24s ease,border-color .24s ease,box-shadow .24s ease; }
    .rp-guide-overview > div:nth-child(2) { --guide-accent:#0878d1; }.rp-guide-overview > div:nth-child(3) { --guide-accent:#07834b; }.rp-guide-overview > div:nth-child(4) { --guide-accent:#6941c6; }
    .rp-guide-overview > div::after,.rp-guide-panel::after,.rp-guide-check::after { content:"";position:absolute;right:-62px;bottom:-78px;width:200px;height:200px;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--guide-accent) 15%,transparent),color-mix(in srgb,var(--guide-accent) 6%,transparent) 42%,transparent 72%);z-index:-1;pointer-events:none; }
    .rp-guide-overview > div:hover { transform:translateY(-5px);border-color:color-mix(in srgb,var(--guide-accent) 50%,var(--rp-line));box-shadow:0 16px 38px rgba(17,17,17,.065); }
    .rp-guide-overview span { color:var(--guide-accent);font-size:10px;font-weight:600;letter-spacing:.12em; }
    .rp-guide-overview strong { margin-top:34px;font-size:16px;font-weight:600; }
    .rp-guide-overview small { max-width:82%;margin-top:9px;color:var(--rp-muted);font-size:11px;line-height:1.55; }
    .rp-guide-panel { --guide-accent:#ff5600;position:relative;isolation:isolate;overflow:hidden;height:100%;min-height:250px;background:var(--rp-surface);border:1px solid var(--rp-line);border-radius:16px;padding:28px;box-shadow:0 10px 30px rgba(17,17,17,.045);transition:transform .24s ease,border-color .24s ease; }
    .rp-guide-panel:hover { transform:translateY(-4px);border-color:color-mix(in srgb,var(--guide-accent) 48%,var(--rp-line)); }
    .rp-guide-orange { --guide-accent:#ff5600; }.rp-guide-blue { --guide-accent:#0878d1; }.rp-guide-green { --guide-accent:#07834b; }.rp-guide-purple { --guide-accent:#6941c6; }.rp-guide-red { --guide-accent:#d92d20; }.rp-guide-amber { --guide-accent:#c66a00; }
    .rp-guide-kicker { color:var(--guide-accent);font-size:9px;font-weight:600;letter-spacing:.14em; }
    .rp-guide-panel h3 { margin:24px 0 10px;font-size:21px!important; }
    .rp-guide-panel p { min-height:66px;line-height:1.65;font-size:13px; }
    .rp-guide-formula { margin-top:18px;padding:13px 15px;background:color-mix(in srgb,var(--guide-accent) 5%,#fff);border-left:3px solid var(--guide-accent);color:var(--rp-ink);font-size:11px;font-weight:500; }
    .rp-guide-check { --guide-accent:#ff5600;position:relative;isolation:isolate;min-height:172px;background:var(--rp-surface);border:1px solid var(--rp-line);border-radius:14px;padding:22px;overflow:hidden;box-shadow:0 8px 24px rgba(17,17,17,.03);transition:transform .22s ease,border-color .22s ease; }
    .rp-guide-check:hover { transform:translateY(-4px);border-color:color-mix(in srgb,var(--guide-accent) 48%,var(--rp-line)); }
    .rp-guide-check strong { font-size:15px; }.rp-guide-check p { max-width:76%;margin-top:20px;font-size:11px;line-height:1.6; }
    .rp-guide-check span { position:absolute;right:17px;bottom:14px;color:var(--guide-accent);font-size:27px;font-weight:500;letter-spacing:-1px; }

    .rp-metric { --rp-card-accent:var(--rp-orange);position:relative;isolation:isolate;overflow:hidden;height:100%;min-height:168px;background:#fff;border:1px solid var(--rp-line);border-radius:14px;padding:20px 20px 18px;box-shadow:0 8px 26px rgba(17,17,17,.04);transition:transform .25s ease,border-color .25s ease,box-shadow .25s ease;animation:rp-rise .55s cubic-bezier(.2,.8,.2,1) both; }
    .rp-metric:hover { transform:translateY(-5px);border-color:color-mix(in srgb,var(--rp-card-accent) 55%,var(--rp-line));box-shadow:0 16px 38px rgba(17,17,17,.075); }
    .rp-metric::after { content:"";position:absolute;right:-54px;bottom:-72px;width:190px;height:190px;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--rp-card-accent) 14%,transparent) 0%,color-mix(in srgb,var(--rp-card-accent) 7%,transparent) 36%,transparent 72%);z-index:-1;pointer-events:none; }
    .rp-metric::before { content:"";position:absolute;right:14px;bottom:10px;width:82px;height:46px;background:linear-gradient(135deg,transparent 0 48%,color-mix(in srgb,var(--rp-card-accent) 12%,transparent) 49% 51%,transparent 52%);opacity:.7;z-index:-1; }
    .rp-metric > * { position:relative;z-index:2; }
    .rp-metric-blue { --rp-card-accent:#0878d1; }.rp-metric-green { --rp-card-accent:#07834b; }.rp-metric-purple { --rp-card-accent:#6941c6; }.rp-metric-red { --rp-card-accent:#d92d20; }
    .rp-metric-top { display:flex;align-items:center;justify-content:space-between;color:var(--rp-muted);font-size:12px;font-weight:500; }
    .rp-metric-dot { width:8px;height:8px;border-radius:50%;background:var(--rp-card-accent);box-shadow:0 0 0 5px color-mix(in srgb,var(--rp-card-accent) 10%,transparent); }
    .rp-metric-value { color:var(--rp-ink);font-size:34px;font-weight:500;letter-spacing:-1.4px;line-height:1;margin-top:31px; }
    .rp-metric-footer { display:flex;align-items:center;gap:9px;color:var(--rp-subtle);font-size:9px;font-weight:600;letter-spacing:.11em;margin-top:18px; }
    .rp-metric-line { display:block;width:24px;height:2px;background:var(--rp-card-accent); }
    .rp-dashboard-gap { height:24px; }
    .rp-ethics { color:var(--rp-muted);font-size:12px;line-height:1.5;padding:10px 0;margin-bottom:4px;border-bottom:1px solid var(--rp-line-soft); }
    .rp-ethics strong { color:var(--rp-ink);font-weight:600; }

    .stButton > button, .stDownloadButton > button {
        min-height:42px;border:1px solid var(--rp-line) !important;border-radius:8px !important;
        background:var(--rp-surface) !important;color:var(--rp-ink) !important;
        box-shadow:none !important;font-size:14px !important;font-weight:500 !important;padding:9px 18px !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover { border-color:var(--rp-ink) !important;background:var(--rp-surface) !important; }
    .stButton > button[kind="primary"] { background:var(--rp-ink) !important;color:white !important;border-color:var(--rp-ink) !important; }
    .stButton > button[kind="primary"]:hover { background:#000 !important; }
    .stButton > button:focus, .stDownloadButton > button:focus { box-shadow:0 0 0 3px rgba(255,86,0,.16) !important; }

    .stTextInput input, .stTextArea textarea, .stNumberInput input {
        color:var(--rp-ink) !important;background:var(--rp-surface) !important;
        -webkit-text-fill-color:var(--rp-ink) !important;font-size:14px !important;
    }
    .stTextInput [data-baseweb="input"], .stTextArea [data-baseweb="textarea"],
    .stNumberInput [data-baseweb="input"], [data-testid="stNumberInputContainer"],
    .stSelectbox [data-baseweb="select"] > div, .stSelectbox [role="group"] {
        background:var(--rp-surface) !important;border:1px solid var(--rp-line) !important;
        border-radius:8px !important;box-shadow:none !important;color:var(--rp-ink) !important;
    }
    .stTextInput [data-baseweb="input"]:focus-within, .stTextArea [data-baseweb="textarea"]:focus-within,
    .stNumberInput [data-baseweb="input"]:focus-within, .stSelectbox [data-baseweb="select"] > div:focus-within,
    .stSelectbox [role="group"]:focus-within {
        border-color:var(--rp-orange) !important;box-shadow:0 0 0 3px rgba(255,86,0,.12) !important;
    }
    .stSelectbox [data-baseweb="select"] *, .stSelectbox [role="group"] *, .stSelectbox input {
        color:var(--rp-ink) !important;background-color:transparent !important;-webkit-text-fill-color:var(--rp-ink) !important;
    }
    [data-testid="stNumberInputContainer"] button { display:none !important; }
    input[type=number]::-webkit-inner-spin-button, input[type=number]::-webkit-outer-spin-button { -webkit-appearance:none;margin:0; }
    input[type=number] { -moz-appearance:textfield; }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder { color:var(--rp-subtle) !important;-webkit-text-fill-color:var(--rp-subtle) !important; }

    [data-testid="stFileUploader"] { background:var(--rp-surface);border:1px solid var(--rp-line);border-radius:10px;padding:6px; }
    [data-testid="stFileUploaderDropzone"] { background:var(--rp-canvas) !important;border:1px dashed var(--rp-line) !important;border-radius:8px !important; }
    [data-testid="stFileUploaderDropzone"] button { background:var(--rp-ink) !important;color:white !important;border-color:var(--rp-ink) !important; }
    [data-testid="stAlert"] { border-radius:8px !important;border:1px solid var(--rp-line) !important;box-shadow:none !important; }
    [data-testid="stAlert"] * { color:var(--rp-ink) !important; }
    [data-testid="stExpander"] { background:var(--rp-surface) !important;border:1px solid var(--rp-line) !important;border-radius:8px !important;box-shadow:none !important; }
    [data-testid="stMetric"] { background:var(--rp-surface);border-left:1px solid var(--rp-line);padding:12px 14px; }
    [data-testid="stMetricValue"] { color:var(--rp-ink) !important;font-weight:500 !important; }
    [data-testid="stDataFrame"], .stTable { border:1px solid var(--rp-line);border-radius:8px;overflow:hidden;background:var(--rp-surface); }
    .stTable table { width:100%; }
    .stTable th { background:var(--rp-surface-2) !important;color:var(--rp-ink) !important;font-weight:500 !important; }
    .stTable td { background:var(--rp-surface) !important;color:var(--rp-muted) !important;border-color:var(--rp-line-soft) !important; }
    .stCodeBlock { border:1px solid var(--rp-line);border-radius:8px;overflow:hidden; }
    .stProgress > div > div > div > div { background:var(--rp-orange) !important; }
    [data-testid="stToast"] { background:var(--rp-ink) !important;color:white !important;border-radius:8px !important; }
    div[data-testid="stHorizontalBlock"] { gap:20px; }
    .main hr { border-color:var(--rp-line) !important;margin:28px 0 !important; }
    a { color:#0007cb; }

    @keyframes rp-rise { from { opacity:0;transform:translateY(14px); } to { opacity:1;transform:translateY(0); } }
    @keyframes rp-breathe { 0%,100% { transform:scale(.92);opacity:.58; } 50% { transform:scale(1.08);opacity:1; } }

    @media (max-width:900px) {
        section[data-testid="stSidebar"] { width:min(248px,86vw) !important;min-width:min(248px,86vw) !important; }
        .block-container { padding:1.5rem 1rem 3rem !important; }
        .rp-hero { grid-template-columns:1fr;padding-top:24px; }
        .rp-hero h1 { font-size:38px !important; }
        .rp-hero-mark { display:none; }
        .rp-guide-overview { grid-template-columns:repeat(2,1fr); }
    }
    @media (prefers-reduced-motion:reduce) {
        *,*::before,*::after { animation-duration:.01ms !important;animation-iteration-count:1 !important;scroll-behavior:auto !important;transition-duration:.01ms !important; }
    }
    </style>
    """
