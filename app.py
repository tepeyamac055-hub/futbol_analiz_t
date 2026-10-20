import warnings
warnings.filterwarnings("ignore")

import io
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from statsbombpy import sb
from mplsoccer import Pitch, VerticalPitch, PyPizza

st.set_page_config(page_title="Futbol Stat", page_icon="⚽", layout="wide")

# ============================================================
# RENKLER
# ============================================================
ARKA = "#0B0F14"
PANEL = "#141A22"
CIZGI = "#243041"
YAZI = "#E8EDF2"
SOLUK = "#8A96A3"
VURGU = "#00E5A0"   # ana renk (yeşil)
KIRMIZI = "#FF5C7A"
SARI = "#FFB547"
MAVI = "#4DA3FF"

st.markdown(f"""
<style>
.block-container {{padding-top: 2rem; max-width: 1300px;}}
.hero h1 {{font-size: 2.3rem; margin-bottom: 0; line-height: 1.15;}}
.hero p {{color: {SOLUK}; margin-top: .3rem; font-size: 1rem;}}
.hikaye {{background: {PANEL}; border: 1px solid {CIZGI}; border-left: 4px solid {VURGU};
          border-radius: 12px; padding: 16px 18px; height: 100%; min-height: 150px;}}
.hikaye .etiket {{color: {VURGU}; font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;}}
.hikaye .baslik {{color: {YAZI}; font-size: 1.05rem; font-weight: 600; margin: .4rem 0;}}
.hikaye .detay {{color: {SOLUK}; font-size: .9rem;}}
.alt {{color: {SOLUK}; font-size: .95rem; margin-top: -.6rem; margin-bottom: 1rem;}}
[data-testid="stMetric"] {{background: {PANEL}; border: 1px solid {CIZGI}; border-radius: 12px; padding: 12px 16px;}}
</style>
""", unsafe_allow_html=True)

# ============================================================
# TURNUVALAR VE TÜRKÇE İSİMLER
# ============================================================
TURNUVALAR = {
    "2022 Dünya Kupası": (43, 106),
    "Euro 2024": (55, 282),
}

TR = {
    "Argentina": ("Arjantin", "ar"), "Australia": ("Avustralya", "au"), "Belgium": ("Belçika", "be"),
    "Brazil": ("Brezilya", "br"), "Cameroon": ("Kamerun", "cm"), "Canada": ("Kanada", "ca"),
    "Costa Rica": ("Kosta Rika", "cr"), "Croatia": ("Hırvatistan", "hr"), "Denmark": ("Danimarka", "dk"),
    "Ecuador": ("Ekvador", "ec"), "England": ("İngiltere", "gb-eng"), "France": ("Fransa", "fr"),
    "Germany": ("Almanya", "de"), "Ghana": ("Gana", "gh"), "Iran": ("İran", "ir"),
    "Japan": ("Japonya", "jp"), "Mexico": ("Meksika", "mx"), "Morocco": ("Fas", "ma"),
    "Netherlands": ("Hollanda", "nl"), "Poland": ("Polonya", "pl"), "Portugal": ("Portekiz", "pt"),
    "Qatar": ("Katar", "qa"), "Saudi Arabia": ("Suudi Arabistan", "sa"), "Senegal": ("Senegal", "sn"),
    "Serbia": ("Sırbistan", "rs"), "South Korea": ("Güney Kore", "kr"), "Korea Republic": ("Güney Kore", "kr"),
    "Spain": ("İspanya", "es"), "Switzerland": ("İsviçre", "ch"), "Tunisia": ("Tunus", "tn"),
    "United States": ("ABD", "us"), "Uruguay": ("Uruguay", "uy"), "Wales": ("Galler", "gb-wls"),
    "Albania": ("Arnavutluk", "al"), "Austria": ("Avusturya", "at"), "Czech Republic": ("Çekya", "cz"),
    "Czechia": ("Çekya", "cz"), "Georgia": ("Gürcistan", "ge"), "Hungary": ("Macaristan", "hu"),
    "Italy": ("İtalya", "it"), "Romania": ("Romanya", "ro"), "Scotland": ("İskoçya", "gb-sct"),
    "Slovakia": ("Slovakya", "sk"), "Slovenia": ("Slovenya", "si"), "Turkey": ("Türkiye", "tr"),
    "Türkiye": ("Türkiye", "tr"), "Ukraine": ("Ukrayna", "ua"),
}
KOD = {v[0]: v[1] for v in TR.values()}


def tr(ad):
    return TR.get(ad, (ad, None))[0]


def bayrak(tr_ad, genislik=80):
    kod = KOD.get(tr_ad)
    return f"https://flagcdn.com/w{genislik}/{kod}.png" if kod else None


def kol(df, c):
    return df[c] if c in df.columns else pd.Series(np.nan, index=df.index, dtype=object)


# ============================================================
# VERİ YÜKLEME (bir kez indirilir, sonra hafızada tutulur)
# ============================================================
DOKUNUS_TIPLERI = {"Pass", "Carry", "Ball Receipt*", "Shot", "Dribble", "Duel", "Interception",
                   "Ball Recovery", "Clearance", "Block", "Pressure", "Miscontrol", "Dispossessed", "Foul Won"}


@st.cache_data(show_spinner="Veriler indiriliyor... İlk açılış birkaç dakika sürebilir ⏳", persist="disk")
def veri_yukle(comp_id, season_id):
    maclar = sb.matches(competition_id=comp_id, season_id=season_id)
    if os.environ.get("FS_TEST"):
        maclar = maclar.head(int(os.environ["FS_TEST"]))

    oyuncu_mac, sutlar, dokunuslar, takim_mac, pozlar = [], [], [], [], []
    takma_ad = {}

    for m in maclar.itertuples():
        mid = m.match_id
        ev = sb.events(match_id=mid)

        # Kısa isimler (Lionel Andrés Messi Cuccittini -> Lionel Messi)
        try:
            for _, df in sb.lineups(match_id=mid).items():
                lakaplar = df["player_nickname"] if "player_nickname" in df.columns else [None] * len(df)
                for ad, lakap in zip(df["player_name"], lakaplar):
                    if isinstance(lakap, str) and lakap.strip():
                        takma_ad[ad] = lakap
        except Exception:
            pass

        # Oynanan dakikalar
        son = int(ev.loc[ev["period"] < 5, "minute"].max()) + 1
        sure = {}
        for _, r in ev[ev["type"] == "Starting XI"].iterrows():
            for p in r["tactics"]["lineup"]:
                sure[p["player"]["name"]] = [0, son]
        for _, r in ev[ev["type"] == "Substitution"].iterrows():
            dk = int(r["minute"])
            if r["player"] in sure:
                sure[r["player"]][1] = dk
            giren = r.get("substitution_replacement")
            if isinstance(giren, str):
                sure[giren] = [dk, son]
        for c in ["foul_committed_card", "bad_behaviour_card"]:
            if c in ev.columns:
                for _, r in ev[ev[c].isin(["Red Card", "Second Yellow"])].iterrows():
                    if r["player"] in sure:
                        sure[r["player"]][1] = int(r["minute"])

        pozlar.append(ev[["player", "position"]].dropna())

        # Olay bayrakları
        tip = ev["type"]
        sut_mu = (tip == "Shot") & (ev["period"] < 5)
        xg = pd.to_numeric(kol(ev, "shot_statsbomb_xg"), errors="coerce").fillna(0.0)
        pen = kol(ev, "shot_type") == "Penalty"
        gol = sut_mu & (kol(ev, "shot_outcome") == "Goal")
        pas_mu = tip == "Pass"
        isabetli = pas_mu & kol(ev, "pass_outcome").isna()
        kilit = pas_mu & (kol(ev, "pass_shot_assist").eq(True) | kol(ev, "pass_goal_assist").eq(True))
        asist = pas_mu & kol(ev, "pass_goal_assist").eq(True)
        ss = ev[sut_mu]
        xa_map = dict(zip(kol(ss, "shot_key_pass_id"), pd.to_numeric(kol(ss, "shot_statsbomb_xg"), errors="coerce")))
        ileri = pd.Series([isinstance(a, list) and isinstance(b, list) and b[0] - a[0] >= 10 and b[0] >= 60
                           for a, b in zip(ev["location"], kol(ev, "pass_end_location"))], index=ev.index)

        f = pd.DataFrame({
            "player": ev["player"], "team": ev["team"],
            "sut": sut_mu, "xG": np.where(sut_mu, xg, 0.0), "npxG": np.where(sut_mu & ~pen, xg, 0.0),
            "gol": gol, "npgol": gol & ~pen,
            "pas": pas_mu, "isabetli_pas": isabetli, "kilit_pas": kilit, "asist": asist,
            "xA": ev["id"].map(xa_map).fillna(0.0).astype(float),
            "ileri_pas": isabetli & ileri,
            "basarili_calim": (tip == "Dribble") & (kol(ev, "dribble_outcome") == "Complete"),
            "mudahale": (tip == "Duel") & (kol(ev, "duel_type") == "Tackle"),
            "top_calma": tip == "Interception",
            "top_kazanma": tip == "Ball Recovery",
            "pres": tip == "Pressure",
            "uzaklastirma": tip == "Clearance",
        })
        g = f.dropna(subset=["player"]).groupby(["player", "team"]).sum().reset_index()
        g["dakika"] = g["player"].map(lambda p: max(sure[p][1] - sure[p][0], 0) if p in sure else 0)
        g["mac_id"] = mid
        oyuncu_mac.append(g)

        # Şutlar
        s = ev[sut_mu]
        sutlar.append(pd.DataFrame({
            "mac_id": mid, "team": s["team"], "player": s["player"], "dakika": s["minute"],
            "x": [l[0] for l in s["location"]], "y": [l[1] for l in s["location"]],
            "xG": pd.to_numeric(kol(s, "shot_statsbomb_xg"), errors="coerce").fillna(0.0),
            "sonuc": kol(s, "shot_outcome"), "tur": kol(s, "shot_type"),
        }))

        # Topla temaslar (ısı haritası için)
        d = ev[tip.isin(DOKUNUS_TIPLERI) & ev["location"].notna() & ev["player"].notna()]
        dokunuslar.append(pd.DataFrame({
            "mac_id": mid, "team": d["team"], "player": d["player"],
            "x": [l[0] for l in d["location"]], "y": [l[1] for l in d["location"]],
        }))

        # Takım maç özeti
        pas_say = ev[pas_mu].groupby("team").size()
        toplam = pas_say.sum()
        for takim, rakip, at, yedi in [(m.home_team, m.away_team, m.home_score, m.away_score),
                                       (m.away_team, m.home_team, m.away_score, m.home_score)]:
            ts, rs = s[s["team"] == takim], s[s["team"] == rakip]
            takim_mac.append({
                "mac_id": mid, "tarih": m.match_date, "team": takim, "rakip": rakip,
                "atilan": at, "yenilen": yedi, "sut": len(ts), "rakip_sut": len(rs),
                "xG": pd.to_numeric(kol(ts, "shot_statsbomb_xg"), errors="coerce").sum(),
                "xGA": pd.to_numeric(kol(rs, "shot_statsbomb_xg"), errors="coerce").sum(),
                "topla_oynama": 100 * pas_say.get(takim, 0) / toplam if toplam else 50.0,
            })

    oy = pd.concat(oyuncu_mac, ignore_index=True)
    sut = pd.concat(sutlar, ignore_index=True)
    dok = pd.concat(dokunuslar, ignore_index=True)
    tm = pd.DataFrame(takim_mac)
    pz = pd.concat(pozlar)
    poz = pz.groupby("player")["position"].agg(lambda x: x.value_counts().index[0]).to_dict()

    for df in (oy, sut, dok):
        df["team"] = df["team"].map(tr)
    tm["team"] = tm["team"].map(tr)
    tm["rakip"] = tm["rakip"].map(tr)
    maclar = maclar.copy()
    maclar["home_team"] = maclar["home_team"].map(tr)
    maclar["away_team"] = maclar["away_team"].map(tr)
    return maclar, oy, sut, dok, tm, poz, takma_ad


# ============================================================
# TABLOLAR
# ============================================================
def grup(p):
    if not isinstance(p, str):
        return "Bilinmiyor"
    if "Goalkeeper" in p:
        return "Kaleci"
    if "Back" in p:
        return "Defans"
    if "Midfield" in p:
        return "Orta saha"
    return "Forvet"


def oyuncu_tablosu(oy, poz, takma):
    sayilar = [c for c in oy.columns if c not in ("player", "team", "mac_id")]
    t = (oy.groupby(["player", "team"])
           .agg({**{c: "sum" for c in sayilar}, "mac_id": "nunique"})
           .rename(columns={"mac_id": "mac"}).reset_index())
    t = t[t["dakika"] > 0].copy()
    t["ad"] = t["player"].map(lambda p: takma.get(p, p))
    t["pozisyon"] = t["player"].map(poz).map(grup)
    t["etiket"] = t["ad"] + " · " + t["team"]
    d90 = t["dakika"].clip(lower=1) / 90
    for c in sayilar:
        if c != "dakika":
            t[c + "_90"] = t[c] / d90
    t["pas_isabet"] = 100 * t["isabetli_pas"] / t["pas"].clip(lower=1)
    t["bitiricilik"] = t["npgol"] - t["npxG"]
    return t


def takim_tablosu(tm):
    t = tm.groupby("team").agg(
        mac=("mac_id", "nunique"), atilan=("atilan", "sum"), yenilen=("yenilen", "sum"),
        sut=("sut", "sum"), xG=("xG", "sum"), xGA=("xGA", "sum"), topla_oynama=("topla_oynama", "mean"))
    for c in ["atilan", "yenilen", "sut", "xG", "xGA"]:
        t[c + "_mac"] = t[c] / t["mac"]
    t["gol_eksi_xG"] = t["atilan"] - t["xG"]
    return t.reset_index()


# ============================================================
# GRAFİK YARDIMCILARI
# ============================================================
def stil(fig, yukseklik=None):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=YAZI), margin=dict(l=10, r=40, t=60, b=10), title_font=dict(size=18))
    fig.update_xaxes(gridcolor=CIZGI, zerolinecolor=CIZGI)
    fig.update_yaxes(gridcolor=CIZGI, zerolinecolor=CIZGI)
    if yukseklik:
        fig.update_layout(height=yukseklik)
    return fig


def bar_ortalama(df, x, y, baslik, ortalama, dusuk_iyi=False, ondalik=2):
    renk = [VURGU if ((v <= ortalama) if dusuk_iyi else (v >= ortalama)) else "#2A6B5A" for v in df[x]]
    fig = go.Figure(go.Bar(x=df[x], y=df[y], orientation="h", marker_color=renk,
                           text=df[x].round(ondalik), textposition="outside", textfont=dict(color=YAZI, size=13)))
    fig.add_vline(x=ortalama, line_dash="dash", line_color=SOLUK,
                  annotation_text=f"Ortalama {ortalama:.{ondalik}f}", annotation_font_color=SOLUK,
                  annotation_position="top")
    fig.update_layout(title=baslik, yaxis=dict(autorange="reversed"))
    return stil(fig, max(420, 34 * len(df) + 100))


def hikaye(etiket, baslik, detay):
    return (f"<div class='hikaye'><div class='etiket'>{etiket}</div>"
            f"<div class='baslik'>{baslik}</div><div class='detay'>{detay}</div></div>")


def baslik_yaz(ust, alt):
    st.markdown(f"<div class='hero'><h1>{ust}</h1><p>{alt}</p></div>", unsafe_allow_html=True)


def png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
    return buf.getvalue()


def yuzdelik(havuz, deger):
    havuz = pd.Series(havuz).dropna()
    if len(havuz) == 0:
        return 50
    p = 100 * ((havuz < deger).mean() + 0.5 * (havuz == deger).mean())
    return int(min(max(round(p), 0), 99))


PIZZA = [
    ("npgol_90", "Penaltısız\ngol", KIRMIZI), ("npxG_90", "npxG", KIRMIZI), ("sut_90", "Şut", KIRMIZI),
    ("xA_90", "xA", SARI), ("kilit_pas_90", "Kilit\npas", SARI), ("ileri_pas_90", "İleri\npas", SARI),
    ("pas_isabet", "Pas\nisabeti %", MAVI), ("basarili_calim_90", "Başarılı\nçalım", MAVI), ("pres_90", "Pres", MAVI),
    ("mudahale_90", "Müdahale", VURGU), ("top_calma_90", "Top\nçalma", VURGU), ("top_kazanma_90", "Top\nkazanma", VURGU),
]
TEMALAR = [("Hücum", KIRMIZI), ("Yaratıcılık", SARI), ("Top kullanma", MAVI), ("Savunma", VURGU)]


def oyuncu_yuzdelikleri(satir, havuz):
    return [yuzdelik(havuz[c], satir[c]) for c, _, _ in PIZZA]


def pizza_karti(satir, degerler, turnuva, kullanici):
    params = [p[1] for p in PIZZA]
    renkler = [p[2] for p in PIZZA]
    baker = PyPizza(params=params, background_color=ARKA, straight_line_color=ARKA, straight_line_lw=1,
                    last_circle_color=CIZGI, last_circle_lw=1.5, other_circle_lw=0, inner_circle_size=16)
    fig, ax = baker.make_pizza(
        degerler, figsize=(9, 11.25), color_blank_space="same", slice_colors=renkler,
        value_colors=[ARKA] * len(params), value_bck_colors=renkler, blank_alpha=0.22,
        kwargs_slices=dict(edgecolor=ARKA, zorder=2, linewidth=2),
        kwargs_params=dict(color=YAZI, fontsize=12, va="center"),
        kwargs_values=dict(color=ARKA, fontsize=11, zorder=3, fontweight="bold",
                           bbox=dict(edgecolor=ARKA, facecolor="white", boxstyle="round,pad=0.25", lw=1)))
    ax.set_position([0.1, 0.12, 0.8, 0.64])
    fig.text(0.06, 0.945, satir["ad"], fontsize=28, fontweight="bold", color=YAZI)
    fig.text(0.06, 0.91, f"{satir['team']} · {satir['pozisyon']} · {turnuva} · {int(satir['dakika'])} dk",
             fontsize=13, color=SOLUK)
    x = 0.06
    for ad, renk in TEMALAR:
        fig.text(x, 0.87, "■ " + ad, fontsize=12, color=renk, fontweight="bold")
        x += 0.2
    fig.text(0.06, 0.045, "Yüzdelik dilim: aynı pozisyondaki oyunculara göre, 90 dk başına\nVeri: StatsBomb",
             fontsize=9.5, color=SOLUK)
    fig.text(0.94, 0.05, kullanici, fontsize=15, color=VURGU, fontweight="bold", ha="right")
    return fig


def sut_haritasi_karti(ms, ev_sahibi, deplasman, skor, turnuva, kullanici):
    pitch = Pitch(pitch_type="statsbomb", pitch_color=ARKA, line_color=SOLUK, linewidth=1.3, goal_type="box")
    fig, ax = pitch.draw(figsize=(9, 9))
    fig.set_facecolor(ARKA)
    ax.set_position([0.04, 0.14, 0.92, 0.6])
    for _, s in ms.iterrows():
        x, y = s["x"], s["y"]
        renk = VURGU
        if s["team"] == deplasman:
            x, y, renk = 120 - x, 80 - y, KIRMIZI
        boyut = 120 + s["xG"] * 1400
        if s["sonuc"] == "Goal":
            pitch.scatter(x, y, s=boyut, marker="football", ax=ax, zorder=3)
        else:
            pitch.scatter(x, y, s=boyut, color=renk, alpha=0.55, edgecolors=ARKA, linewidth=1, ax=ax, zorder=2)
    xg_ev = ms.loc[ms["team"] == ev_sahibi, "xG"].sum()
    xg_dep = ms.loc[ms["team"] == deplasman, "xG"].sum()
    fig.text(0.5, 0.92, skor, fontsize=26, fontweight="bold", color=YAZI, ha="center")
    fig.text(0.5, 0.875, f"xG  {xg_ev:.2f} - {xg_dep:.2f}", fontsize=15, color=SOLUK, ha="center")
    fig.text(0.06, 0.8, f"● {ev_sahibi}  →", fontsize=13, color=VURGU, fontweight="bold")
    fig.text(0.94, 0.8, f"←  {deplasman} ●", fontsize=13, color=KIRMIZI, fontweight="bold", ha="right")
    fig.text(0.06, 0.06, f"{turnuva} · Nokta büyüklüğü = xG · top simgesi = gol\nVeri: StatsBomb", fontsize=10, color=SOLUK)
    fig.text(0.94, 0.07, kullanici, fontsize=15, color=VURGU, fontweight="bold", ha="right")
    return fig


def isi_haritasi(d, baslik):
    pitch = Pitch(pitch_type="statsbomb", pitch_color=ARKA, line_color=SOLUK, line_zorder=2, linewidth=1.2)
    fig, ax = pitch.draw(figsize=(8, 5.6))
    fig.set_facecolor(ARKA)
    cmap = LinearSegmentedColormap.from_list("v", [ARKA, "#0B4D3C", VURGU, "#EAFFF7"])
    if len(d) > 5:
        pitch.kdeplot(d["x"], d["y"], ax=ax, fill=True, levels=100, thresh=0, cut=4, cmap=cmap)
    ax.set_title(baslik + "   (hücum yönü →)", color=YAZI, fontsize=13)
    return fig


def oyuncu_sut_haritasi(s, baslik):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color=ARKA, line_color=SOLUK, linewidth=1.2)
    fig, ax = pitch.draw(figsize=(7, 5.6))
    fig.set_facecolor(ARKA)
    for _, r in s.iterrows():
        boyut = 120 + r["xG"] * 1400
        if r["sonuc"] == "Goal":
            pitch.scatter(r["x"], r["y"], s=boyut, marker="football", ax=ax, zorder=3)
        else:
            pitch.scatter(r["x"], r["y"], s=boyut, color=VURGU, alpha=0.5, edgecolors=ARKA, ax=ax)
    ax.set_title(baslik, color=YAZI, fontsize=13)
    return fig


# ============================================================
# KENAR MENÜ
# ============================================================
st.sidebar.markdown("## ⚽ Futbol Stat")
turnuva_adi = st.sidebar.selectbox("Turnuva", list(TURNUVALAR))
sayfa = st.sidebar.radio("Sayfa", ["🏠 Ana sayfa", "🏟️ Takımlar", "🛡️ Takım profili", "👤 Oyuncular",
                                   "🍕 Oyuncu profili", "⚔️ Karşılaştır", "🎯 Maç merkezi"])
st.sidebar.divider()
min_dk = st.sidebar.slider("Sıralamalarda en az dakika", 90, 600, 180, step=30,
                           help="Az oynayan oyuncular sıralamaları bozmasın diye")
kullanici = st.sidebar.text_input("Kartlarda görünecek adın", "@futbolstat")
st.sidebar.caption("Veri: StatsBomb açık verisi")

maclar, oy_mac, sut, dok, tm, poz, takma = veri_yukle(*TURNUVALAR[turnuva_adi])
oyuncular = oyuncu_tablosu(oy_mac, poz, takma)
nitelikli = oyuncular[oyuncular["dakika"] >= min_dk]
takimlar = takim_tablosu(tm)
sut["ad"] = sut["player"].map(lambda p: takma.get(p, p))
dok["ad"] = dok["player"].map(lambda p: takma.get(p, p))


# ============================================================
# ANA SAYFA
# ============================================================
if sayfa == "🏠 Ana sayfa":
    baslik_yaz(turnuva_adi, f"{len(maclar)} maç · {takimlar['team'].nunique()} takım · "
                            f"{len(sut)} şut · {int(takimlar['atilan'].sum())} gol")

    st.subheader("Turnuvadan öne çıkanlar")
    ort_xg = takimlar["xG_mac"].mean()
    a = takimlar.loc[takimlar["xG_mac"].idxmax()]
    b = takimlar.loc[takimlar["gol_eksi_xG"].idxmax()]
    c = takimlar.loc[takimlar["gol_eksi_xG"].idxmin()]
    kartlar = [
        hikaye("En tehlikeli hücum", f"{a['team']} rakip kaleyi en çok zorlayan takım oldu",
               f"Maç başı {a['xG_mac']:.2f} xG üretti. Turnuva ortalaması {ort_xg:.2f}."),
        hikaye("Fırsatçı", f"{b['team']} pozisyonlarını en iyi değerlendiren takım",
               f"{b['xG']:.1f} xG'den {int(b['atilan'])} gol, beklentinin {b['gol_eksi_xG']:+.1f} üstü."),
        hikaye("Şanssız / savurgan", f"{c['team']} beklenenden az gol attı",
               f"{c['xG']:.1f} xG'den sadece {int(c['atilan'])} gol ({c['gol_eksi_xG']:+.1f})."),
    ]
    if len(nitelikli):
        d = nitelikli.loc[nitelikli["bitiricilik"].idxmax()]
        kartlar.append(hikaye("En iyi bitirici", f"{d['ad']} beklentilerin çok üstüne çıktı",
                              f"{d['npxG']:.1f} npxG'den {int(d['npgol'])} penaltısız gol ({d['bitiricilik']:+.1f})."))
    for kolon, kart in zip(st.columns(len(kartlar)), kartlar):
        kolon.markdown(kart, unsafe_allow_html=True)

    st.write("")
    sol, sag = st.columns(2)
    gk = oyuncular.sort_values(["gol", "xG"], ascending=False).head(10)
    fig = bar_ortalama(gk, "gol", "etiket", "Gol krallığı", oyuncular.loc[oyuncular["gol"] > 0, "gol"].mean(), ondalik=0)
    sol.plotly_chart(fig)
    xa = oyuncular.sort_values("xA", ascending=False).head(10)
    fig = bar_ortalama(xa, "xA", "etiket", "En çok pozisyon hazırlayanlar (xA)",
                       oyuncular.loc[oyuncular["xA"] > 0, "xA"].mean())
    sag.plotly_chart(fig)
    st.caption("💡 Her grafiğin sağ üstündeki 📷 simgesiyle grafiği resim olarak indirebilirsin.")


# ============================================================
# TAKIMLAR
# ============================================================
elif sayfa == "🏟️ Takımlar":
    baslik_yaz("Takımlar", "Hangi takım pozisyon üretti, hangisi az pozisyon verdi?")
    METRIK = {"Maç başı xG": ("xG_mac", False), "Maç başı yenen xG (xGA)": ("xGA_mac", True),
              "Maç başı şut": ("sut_mac", False), "Maç başı gol": ("atilan_mac", False),
              "Maç başı yenen gol": ("yenilen_mac", True), "Topla oynama %": ("topla_oynama", False),
              "Gol - xG farkı": ("gol_eksi_xG", False)}
    sol, sag = st.columns([2, 1])
    secim = sol.selectbox("İstatistik", list(METRIK))
    kac = sag.slider("Kaç takım", 5, len(takimlar), min(12, len(takimlar)))
    c, dusuk = METRIK[secim]
    t = takimlar.sort_values(c, ascending=dusuk).head(kac)
    baslik = secim + (" (az olan daha iyi)" if dusuk else "")
    st.plotly_chart(bar_ortalama(t, c, "team", baslik, takimlar[c].mean(), dusuk_iyi=dusuk))

    st.subheader("Hücum mu, savunma mı?")
    st.markdown("<div class='alt'>Sağa gittikçe daha çok pozisyon üretiyor, yukarı çıktıkça daha az pozisyon veriyor.</div>",
                unsafe_allow_html=True)
    fig = px.scatter(takimlar, x="xG_mac", y="xGA_mac", text="team", hover_data={"mac": True},
                     labels={"xG_mac": "Maç başı üretilen xG", "xGA_mac": "Maç başı verilen xG"})
    fig.update_traces(marker=dict(size=13, color=VURGU, line=dict(color=ARKA, width=1)),
                      textposition="top center", textfont=dict(size=11, color=YAZI))
    fig.add_vline(x=takimlar["xG_mac"].mean(), line_dash="dot", line_color=SOLUK)
    fig.add_hline(y=takimlar["xGA_mac"].mean(), line_dash="dot", line_color=SOLUK)
    fig.update_yaxes(autorange="reversed")
    for x, y, yazi, renk in [(0.99, 0.99, "Güçlü hücum + sağlam savunma", VURGU),
                             (0.01, 0.99, "Sağlam savunma, zayıf hücum", MAVI),
                             (0.99, 0.01, "Güçlü hücum, açık veren savunma", SARI),
                             (0.01, 0.01, "Zorlanan takımlar", KIRMIZI)]:
        fig.add_annotation(xref="paper", yref="paper", x=x, y=y, text=yazi, showarrow=False,
                           font=dict(color=renk, size=12), xanchor="right" if x > 0.5 else "left",
                           yanchor="top" if y > 0.5 else "bottom")
    st.plotly_chart(stil(fig, 650))

    with st.expander("📋 Tüm tablo"):
        tablo = takimlar.rename(columns={"team": "Takım", "mac": "Maç", "atilan": "Atılan", "yenilen": "Yenilen",
                                         "sut": "Şut", "xG": "xG", "xGA": "xGA", "topla_oynama": "Topla oynama %",
                                         "xG_mac": "xG/maç", "xGA_mac": "xGA/maç", "sut_mac": "Şut/maç",
                                         "atilan_mac": "Gol/maç", "yenilen_mac": "Yenilen/maç",
                                         "gol_eksi_xG": "Gol - xG"})
        st.dataframe(tablo.sort_values("xG/maç", ascending=False).round(2), hide_index=True)


# ============================================================
# TAKIM PROFİLİ
# ============================================================
elif sayfa == "🛡️ Takım profili":
    takim = st.selectbox("Takım seç (yazarak arayabilirsin)", sorted(takimlar["team"]))
    t = takimlar[takimlar["team"] == takim].iloc[0]
    tmac = tm[tm["team"] == takim].sort_values("tarih")
    g_ = int((tmac["atilan"] > tmac["yenilen"]).sum())
    b_ = int((tmac["atilan"] == tmac["yenilen"]).sum())
    m_ = int((tmac["atilan"] < tmac["yenilen"]).sum())

    sol, sag = st.columns([1, 8])
    if bayrak(takim):
        sol.image(bayrak(takim, 160), width=90)
    with sag:
        baslik_yaz(takim, f"{int(t['mac'])} maç · {g_}G {b_}B {m_}M · {int(t['atilan'])} attı, {int(t['yenilen'])} yedi")

    ort = takimlar.mean(numeric_only=True)
    k = st.columns(5)
    k[0].metric("Gol / maç", f"{t['atilan_mac']:.2f}", f"{t['atilan_mac'] - ort['atilan_mac']:+.2f} ort.")
    k[1].metric("xG / maç", f"{t['xG_mac']:.2f}", f"{t['xG_mac'] - ort['xG_mac']:+.2f} ort.")
    k[2].metric("Verilen xG / maç", f"{t['xGA_mac']:.2f}", f"{t['xGA_mac'] - ort['xGA_mac']:+.2f} ort.",
                delta_color="inverse")
    k[3].metric("Şut / maç", f"{t['sut_mac']:.1f}", f"{t['sut_mac'] - ort['sut_mac']:+.1f} ort.")
    k[4].metric("Topla oynama", f"%{t['topla_oynama']:.0f}", f"{t['topla_oynama'] - ort['topla_oynama']:+.0f} ort.")

    st.write("")
    sol, sag = st.columns([1, 1])
    with sol:
        st.subheader("Maçlar")
        mt = pd.DataFrame({
            "Tarih": tmac["tarih"], "Rakip": tmac["rakip"],
            "Skor": tmac["atilan"].astype(int).astype(str) + " - " + tmac["yenilen"].astype(int).astype(str),
            "xG": tmac["xG"].round(2), "Rakip xG": tmac["xGA"].round(2),
            "Topla oynama %": tmac["topla_oynama"].round(0)})
        st.dataframe(mt, hide_index=True)
    with sag:
        st.subheader("Bütün şutlar")
        st.pyplot(oyuncu_sut_haritasi(sut[sut["team"] == takim], f"{takim} · {len(sut[sut['team'] == takim])} şut"))

    st.subheader("Oyuncular")
    to = oyuncular[oyuncular["team"] == takim].sort_values("dakika", ascending=False)
    st.dataframe(to[["ad", "pozisyon", "mac", "dakika", "gol", "asist", "xG", "xA", "kilit_pas", "mudahale"]]
                 .rename(columns={"ad": "Oyuncu", "pozisyon": "Pozisyon", "mac": "Maç", "dakika": "Dakika",
                                  "gol": "Gol", "asist": "Asist", "kilit_pas": "Kilit pas", "mudahale": "Müdahale"})
                 .round(2), hide_index=True)


# ============================================================
# OYUNCULAR
# ============================================================
elif sayfa == "👤 Oyuncular":
    baslik_yaz("Oyuncular", f"En az {min_dk} dakika oynayan {len(nitelikli)} oyuncu")
    METRIK = {"Gol": "gol", "Asist": "asist", "xG": "xG", "Penaltısız xG (npxG)": "npxG", "xA": "xA",
              "Kilit pas": "kilit_pas", "İleri pas": "ileri_pas", "Başarılı çalım": "basarili_calim",
              "Müdahale": "mudahale", "Top çalma": "top_calma", "Pres": "pres"}
    a, b, c = st.columns([2, 2, 1])
    secim = a.selectbox("İstatistik", list(METRIK) + ["Bitiricilik (penaltısız gol - npxG)"])
    pozlar_ = b.multiselect("Pozisyon", ["Forvet", "Orta saha", "Defans", "Kaleci"],
                            default=["Forvet", "Orta saha", "Defans"])
    doksan = c.toggle("90 dk başına", value=True)
    havuz = nitelikli[nitelikli["pozisyon"].isin(pozlar_)]
    if secim.startswith("Bitiricilik"):
        kolon, ad = "bitiricilik", secim
    else:
        kolon = METRIK[secim] + ("_90" if doksan else "")
        ad = secim + (" / 90 dk" if doksan else "")
    if len(havuz):
        t = havuz.sort_values(kolon, ascending=False).head(15)
        st.plotly_chart(bar_ortalama(t, kolon, "etiket", ad, havuz[kolon].mean()))

        st.subheader("Kim iyi bitirici, kim pozisyon harcıyor?")
        st.markdown("<div class='alt'>Kesikli çizginin üstündekiler beklenenden fazla gol attı.</div>",
                    unsafe_allow_html=True)
        o = havuz[havuz["sut"] >= 3]
        fig = px.scatter(o, x="npxG", y="npgol", size="sut", color="bitiricilik", color_continuous_scale="RdYlGn",
                         hover_name="ad", hover_data={"team": True, "sut": True},
                         labels={"npxG": "Penaltısız xG", "npgol": "Penaltısız gol", "bitiricilik": "Gol - xG",
                                 "team": "Takım", "sut": "Şut"})
        ust = max(o["npxG"].max(), o["npgol"].max()) + 0.5 if len(o) else 1
        fig.add_shape(type="line", x0=0, y0=0, x1=ust, y1=ust, line=dict(dash="dash", color=SOLUK))
        st.plotly_chart(stil(fig, 600))

        with st.expander("📋 Tüm tablo"):
            st.dataframe(havuz[["ad", "team", "pozisyon", "mac", "dakika", "gol", "asist", "npxG", "xA",
                                "kilit_pas", "basarili_calim", "mudahale", "top_calma"]]
                         .rename(columns={"ad": "Oyuncu", "team": "Takım", "pozisyon": "Pozisyon", "mac": "Maç",
                                          "dakika": "Dakika", "gol": "Gol", "asist": "Asist", "kilit_pas": "Kilit pas",
                                          "basarili_calim": "Başarılı çalım", "mudahale": "Müdahale",
                                          "top_calma": "Top çalma"})
                         .sort_values("Gol", ascending=False).round(2), hide_index=True)
    else:
        st.info("Bu filtrelerle oyuncu yok. Sol menüden dakika sınırını düşürmeyi dene.")


# ============================================================
# OYUNCU PROFİLİ
# ============================================================
elif sayfa == "🍕 Oyuncu profili":
    liste = oyuncular.sort_values("dakika", ascending=False)["etiket"].tolist()
    varsayilan = oyuncular.sort_values("xG", ascending=False)["etiket"].iloc[0]
    secim = st.selectbox("Oyuncu seç (yazarak arayabilirsin)", liste, index=liste.index(varsayilan))
    o = oyuncular[oyuncular["etiket"] == secim].iloc[0]

    sol, sag = st.columns([1, 8])
    if bayrak(o["team"]):
        sol.image(bayrak(o["team"], 160), width=90)
    with sag:
        baslik_yaz(o["ad"], f"{o['team']} · {o['pozisyon']} · {int(o['mac'])} maç · {int(o['dakika'])} dakika")

    k = st.columns(6)
    k[0].metric("Gol", int(o["gol"]))
    k[1].metric("Asist", int(o["asist"]))
    k[2].metric("npxG", f"{o['npxG']:.2f}")
    k[3].metric("xA", f"{o['xA']:.2f}")
    k[4].metric("Şut", int(o["sut"]))
    k[5].metric("Kilit pas", int(o["kilit_pas"]))

    if o["pozisyon"] == "Kaleci":
        st.info("Kaleci pizza grafiği yakında. Şimdilik ısı haritasına bakabilirsin.")
    else:
        havuz = nitelikli[nitelikli["pozisyon"] == o["pozisyon"]]
        if o["dakika"] < min_dk:
            st.warning(f"Bu oyuncu {int(o['dakika'])} dakika oynamış. Az dakika olduğu için yüzdelikler yanıltıcı olabilir.")
        degerler = oyuncu_yuzdelikleri(o, havuz)
        sol, sag = st.columns([3, 2])
        with sol:
            fig = pizza_karti(o, degerler, turnuva_adi, kullanici)
            st.pyplot(fig)
            st.download_button("📸 Instagram kartını indir", png(fig), file_name=f"{o['ad']}_pizza.png",
                               mime="image/png", type="primary")
        with sag:
            st.subheader("Nasıl okunur?")
            st.markdown(f"<div class='alt'>Her dilim, oyuncunun o istatistikte diğer {len(havuz)} "
                        f"{o['pozisyon'].lower()} oyuncusundan yüzde kaçını geçtiğini gösterir. "
                        f"90 = oyuncuların %90'ından iyi.</div>", unsafe_allow_html=True)
            tablo = pd.DataFrame({
                "İstatistik": [p[1].replace("\n", " ") for p in PIZZA],
                "90 dk başına": [round(o[p[0]], 2) for p in PIZZA],
                "Yüzdelik": degerler})
            st.dataframe(tablo, hide_index=True,
                         column_config={"Yüzdelik": st.column_config.ProgressColumn(
                             "Yüzdelik", min_value=0, max_value=100, format="%d")})

    sol, sag = st.columns(2)
    with sol:
        st.pyplot(isi_haritasi(dok[dok["player"] == o["player"]], "Topla temas ısı haritası"))
    with sag:
        st.pyplot(oyuncu_sut_haritasi(sut[sut["player"] == o["player"]], f"Şutlar · {int(o['gol'])} gol"))


# ============================================================
# KARŞILAŞTIR
# ============================================================
elif sayfa == "⚔️ Karşılaştır":
    baslik_yaz("Karşılaştır", "İki oyuncuyu aynı grafikte yan yana koy")
    liste = nitelikli[nitelikli["pozisyon"] != "Kaleci"].sort_values("xG", ascending=False)["etiket"].tolist()
    if len(liste) < 2:
        st.info("Karşılaştırma için yeterli oyuncu yok. Sol menüden dakika sınırını düşür.")
    else:
        a, b = st.columns(2)
        s1 = a.selectbox("1. oyuncu", liste, index=0)
        s2 = b.selectbox("2. oyuncu", liste, index=1)
        if s1 == s2:
            st.warning("İki farklı oyuncu seç.")
        else:
            o1 = oyuncular[oyuncular["etiket"] == s1].iloc[0]
            o2 = oyuncular[oyuncular["etiket"] == s2].iloc[0]
            y1 = oyuncu_yuzdelikleri(o1, nitelikli[nitelikli["pozisyon"] == o1["pozisyon"]])
            y2 = oyuncu_yuzdelikleri(o2, nitelikli[nitelikli["pozisyon"] == o2["pozisyon"]])
            etiketler = [p[1].replace("\n", " ") for p in PIZZA]
            fig = go.Figure()
            for o_, y_, renk in [(o1, y1, VURGU), (o2, y2, KIRMIZI)]:
                fig.add_trace(go.Scatterpolar(r=y_ + [y_[0]], theta=etiketler + [etiketler[0]], fill="toself",
                                              name=f"{o_['ad']} ({o_['team']})", line=dict(color=renk, width=2),
                                              opacity=0.75))
            fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)",
                                         radialaxis=dict(range=[0, 100], gridcolor=CIZGI, showticklabels=False),
                                         angularaxis=dict(gridcolor=CIZGI)),
                              legend=dict(orientation="h", y=-0.1), title="Yüzdelik dilimler (kendi pozisyonuna göre)")
            st.plotly_chart(stil(fig, 620))

            n1, n2 = o1["ad"], o2["ad"] if o2["ad"] != o1["ad"] else o2["ad"] + " (2)"
            tablo = pd.DataFrame({"İstatistik": etiketler,
                                  n1: [round(o1[p[0]], 2) for p in PIZZA],
                                  n2: [round(o2[p[0]], 2) for p in PIZZA]}).set_index("İstatistik")
            st.subheader("90 dakika başına rakamlar")
            st.dataframe(tablo.style.highlight_max(axis=1, color="#0F3D31").format("{:.2f}"))
            st.caption("💡 Yeşil olan o istatistikte daha iyi. Grafiği 📷 simgesiyle resim olarak indirebilirsin.")


# ============================================================
# MAÇ MERKEZİ
# ============================================================
elif sayfa == "🎯 Maç merkezi":
    m = maclar.sort_values("match_date", ascending=False).copy()
    m["etiket"] = (m["match_date"].astype(str) + " · " + m["home_team"] + " " + m["home_score"].astype(str)
                   + " - " + m["away_score"].astype(str) + " " + m["away_team"])
    secim = st.selectbox("Maç seç (yazarak arayabilirsin)", m["etiket"])
    r = m[m["etiket"] == secim].iloc[0]
    ev_, dep = r["home_team"], r["away_team"]
    skor = f"{ev_} {r['home_score']} - {r['away_score']} {dep}"
    ms = sut[sut["mac_id"] == r["match_id"]]
    tme = tm[tm["mac_id"] == r["match_id"]].set_index("team")

    baslik_yaz(skor, f"{r['match_date']}")
    k = st.columns(4)
    k[0].metric(f"xG · {ev_}", f"{tme.loc[ev_, 'xG']:.2f}")
    k[1].metric(f"xG · {dep}", f"{tme.loc[dep, 'xG']:.2f}")
    k[2].metric("Şut", f"{int(tme.loc[ev_, 'sut'])} - {int(tme.loc[dep, 'sut'])}")
    k[3].metric("Topla oynama", f"%{tme.loc[ev_, 'topla_oynama']:.0f} - %{tme.loc[dep, 'topla_oynama']:.0f}")

    # xG yarışı
    fig = go.Figure()
    son = int(max(ms["dakika"].max() if len(ms) else 90, 90)) + 1
    for takim, renk in [(ev_, VURGU), (dep, KIRMIZI)]:
        s = ms[ms["team"] == takim].sort_values("dakika")
        x = [0] + s["dakika"].tolist() + [son]
        y = [0] + s["xG"].cumsum().tolist() + [s["xG"].sum()]
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line_shape="hv", name=takim, line=dict(color=renk, width=3)))
        g = s[s["sonuc"] == "Goal"]
        if len(g):
            fig.add_trace(go.Scatter(x=g["dakika"], y=s["xG"].cumsum()[g.index], mode="markers", showlegend=False,
                                     marker=dict(symbol="star", size=16, color=renk, line=dict(color="white", width=1)),
                                     text=g["ad"], hovertemplate="⚽ %{text} · %{x}. dk<extra></extra>"))
    fig.update_layout(title="xG yarışı (⭐ = gol)", xaxis_title="Dakika", yaxis_title="Toplam xG",
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(stil(fig, 420))

    sol, sag = st.columns([3, 2])
    with sol:
        fig = sut_haritasi_karti(ms, ev_, dep, skor, turnuva_adi, kullanici)
        st.pyplot(fig)
        st.download_button("📸 Instagram kartını indir", png(fig), file_name="sut_haritasi.png",
                           mime="image/png", type="primary")
    with sag:
        st.subheader("Maçın oyuncuları")
        mo = oy_mac[oy_mac["mac_id"] == r["match_id"]].copy()
        mo["ad"] = mo["player"].map(lambda p: takma.get(p, p))
        mo["katki"] = mo["xG"] + mo["xA"]
        st.dataframe(mo.sort_values("katki", ascending=False)[["ad", "team", "dakika", "gol", "asist", "xG", "xA",
                                                               "kilit_pas", "basarili_calim"]]
                     .rename(columns={"ad": "Oyuncu", "team": "Takım", "dakika": "Dk", "gol": "Gol", "asist": "Asist",
                                      "kilit_pas": "Kilit pas", "basarili_calim": "Çalım"})
                     .round(2), hide_index=True, height=560)

plt.close("all")
st.divider()
st.caption("Futbol Stat · Veri: StatsBomb açık verisi · xG = gol beklentisi")
