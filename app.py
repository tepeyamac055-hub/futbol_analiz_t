import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
from statsbombpy import sb
from mplsoccer import Pitch

st.set_page_config(page_title="Futbol Analiz", page_icon="⚽", layout="wide")

# Ücretsiz StatsBomb verisindeki turnuvalar: (competition_id, season_id)
TURNUVALAR = {
    "2022 Dünya Kupası": (43, 106),
    "Euro 2024": (55, 282),
}


@st.cache_data(show_spinner="Veriler indiriliyor... İlk açılış 1-3 dakika sürebilir.")
def veri_yukle(comp_id, season_id):
    maclar = sb.matches(competition_id=comp_id, season_id=season_id)
    parcalar = []
    for mac_id in maclar["match_id"]:
        olaylar = sb.events(match_id=mac_id)
        s = olaylar[(olaylar["type"] == "Shot") & (olaylar["period"] < 5)].copy()
        s["mac_id"] = mac_id
        parcalar.append(s[["mac_id", "id", "team", "player", "location",
                           "shot_statsbomb_xg", "shot_outcome", "shot_type"]])
    return maclar, pd.concat(parcalar)


def gol_say(s):
    return (s == "Goal").sum()


# ---------------- Kenar menü ----------------
st.sidebar.title("⚽ Futbol Analiz")
turnuva_adi = st.sidebar.selectbox("Turnuva seç", list(TURNUVALAR))
maclar, sutlar = veri_yukle(*TURNUVALAR[turnuva_adi])
st.sidebar.caption("Veri: StatsBomb açık verisi")

st.title(turnuva_adi)

# ---------------- Takım tablosu ----------------
mac_sayisi = pd.concat([maclar["home_team"], maclar["away_team"]]).value_counts()
tablo = sutlar.groupby("team").agg(
    sut=("id", "count"),
    xG=("shot_statsbomb_xg", "sum"),
    gol=("shot_outcome", gol_say),
)
tablo["Maç"] = mac_sayisi
tablo["Maç başı xG"] = tablo["xG"] / tablo["Maç"]
tablo["Maç başı şut"] = tablo["sut"] / tablo["Maç"]
tablo["Maç başı gol"] = tablo["gol"] / tablo["Maç"]
tablo = tablo.rename(columns={"sut": "Toplam şut", "xG": "Toplam xG", "gol": "Toplam gol"})
tablo.index.name = "Takım"

sekme1, sekme2, sekme3 = st.tabs(["🏟️ Takımlar", "👤 Oyuncular", "🎯 Şut Haritası"])

with sekme1:
    sol, sag = st.columns(2)
    metrik = sol.selectbox("İstatistik", ["Maç başı xG", "Maç başı şut", "Maç başı gol",
                                          "Toplam gol", "Toplam şut", "Toplam xG"])
    kac = sag.slider("Kaç takım gösterilsin", 5, len(tablo), 10)

    t = tablo.sort_values(metrik, ascending=False).head(kac).reset_index()
    fig = px.bar(t, x=metrik, y="Takım", orientation="h",
                 text=t[metrik].round(2), color=metrik,
                 color_continuous_scale="Teal", template="plotly_dark")
    fig.update_traces(textposition="outside", textfont=dict(color="white", size=14))
    fig.update_layout(yaxis=dict(autorange="reversed", title=""),
                      coloraxis_showscale=False, height=max(400, kac * 35))
    st.plotly_chart(fig)

    with st.expander("Tüm tabloyu göster"):
        st.dataframe(tablo.sort_values(metrik, ascending=False).round(2))

# ---------------- Oyuncular ----------------
with sekme2:
    sol, sag = st.columns(2)
    penaltisiz = sol.toggle("Penaltıları çıkar (npxG)", value=True)
    min_sut = sag.slider("En az şut sayısı", 1, 20, 5)

    veri = sutlar[sutlar["shot_type"] != "Penalty"] if penaltisiz else sutlar
    oyuncu = veri.groupby(["player", "team"]).agg(
        Şut=("id", "count"),
        xG=("shot_statsbomb_xg", "sum"),
        Gol=("shot_outcome", gol_say),
    )
    oyuncu["Gol - xG"] = oyuncu["Gol"] - oyuncu["xG"]
    o = oyuncu[oyuncu["Şut"] >= min_sut].reset_index().rename(
        columns={"player": "Oyuncu", "team": "Takım"})

    fig = px.scatter(o, x="xG", y="Gol", size="Şut", color="Gol - xG",
                     color_continuous_scale="RdYlGn", hover_name="Oyuncu",
                     hover_data=["Takım", "Şut"], template="plotly_dark",
                     title="Kesikli çizginin üstü: beklenenden fazla gol atanlar")
    ust = max(o["xG"].max(), o["Gol"].max()) + 0.5 if len(o) else 1
    fig.add_shape(type="line", x0=0, y0=0, x1=ust, y1=ust,
                  line=dict(dash="dash", color="gray"))
    fig.update_layout(height=600)
    st.plotly_chart(fig)

    st.subheader("En iyi bitiriciler")
    st.dataframe(o.sort_values("Gol - xG", ascending=False).head(15).round(2),
                 hide_index=True)

# ---------------- Şut haritası ----------------
with sekme3:
    maclar["etiket"] = (maclar["home_team"] + " " + maclar["home_score"].astype(str) + " - "
                        + maclar["away_score"].astype(str) + " " + maclar["away_team"])
    secim = st.selectbox("Maç seç", maclar.sort_values("match_date")["etiket"])
    satir = maclar[maclar["etiket"] == secim].iloc[0]
    ms = sutlar[sutlar["mac_id"] == satir["match_id"]]

    pitch = Pitch(pitch_color="grass", line_color="white", stripe=True)
    fig, ax = pitch.draw(figsize=(12, 8))
    for _, sut in ms.iterrows():
        x, y = sut["location"][0], sut["location"][1]
        if sut["team"] == satir["away_team"]:
            x, y = 120 - x, 80 - y
            renk = "navy"
        else:
            renk = "skyblue"
        gol = sut["shot_outcome"] == "Goal"
        pitch.scatter(x, y, s=sut["shot_statsbomb_xg"] * 1500, color=renk,
                      edgecolors="yellow" if gol else "black",
                      linewidth=3 if gol else 1, alpha=0.85, ax=ax)
    ax.set_title(f"{satir['home_team']} (açık mavi) sağa, {satir['away_team']} (lacivert) sola hücum ediyor\n"
                 "Nokta büyüklüğü = xG, sarı çerçeve = gol", fontsize=13)
    st.pyplot(fig)
