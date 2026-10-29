# AOE2-Claude-Ally – AoE II DE ↔ Claude sild

## v1 – Claude kui tiimikaaslane

| Fail | Roll |
|---|---|
| `claude_bridge.xs` | kaardi XS (kaardil `ClaudeGeneral`): iga 5 s kirjutab seisu `ClaudeGeneral.xsdat`, näitab Claude'i sõnumeid chatis |
| `ClaudeAI.per` + `claude_ai.xs` | AI-mängija: majandus, ajastud, tootmine; täidab Claude'i käske, liigutab armeed |
| `general.py` | loeb seisu ja sinu chati (salvestusfailist), küsib `claude -p`, kirjutab `claude_cmd.xsdat` |
| `logs/*.jsonl` | iga otsus koos prompti, vastuse ja latentsusega |

**Käivitamine**
1. `python3 bridge_test.py install`, kui XS/AI/RMS-faile on muudetud.
2. `python3 general.py` (valikud: `--model haiku|sonnet|opus`, `--interval 45`, `--ascii`).
3. Mängus: **Skirmish** → kaart **Custom → ClaudeGeneral** → sina on mängija 1, **mängija 2 = ClaudeAI samas tiimis** (Team 1), vaenlased tavalised AI-d teises tiimis.
4. Räägi Claude'iga **mängu chatis** (Enter, kirjuta, Enter) või terminalis.

**Mida Claude otsustab:** põhi- ja tugiüksus (8 valikut), režiim (kaitse / rünnak mängijale X / abi liitlasele X), kas minna järgmisse ajastusse, külaelanike arv, **hoonete sihtarvud** (kasarmud, laskeväli, tall, piiramistöökoda, sepikoda, turg, klooster, ülikool, loss, linnakeskus, torn, sadam) ja sõnum chatti.
**Mida AI teeb ise:** majad, farmid, veski, puidu- ja kaevanduslaod, külaelanike tootmine, majandusuuringud, valitud üksuste tootmine ja uuendused.
**Millal küsitakse:** iga 45 s järel; kohe, kui kirjutad; kohe, kui tiimikaaslase linnakeskuse juures on ≥3 nähtavat vaenlase sõdurit.
**Mida Claude näeb:** tiimi ressursid ja armee, vaenlastest ainult see, mis on sulle praegu nähtav.

---

# 1. faasi test

Eesmärk: tõestada, et XS-skript ja väline Python-programm saavad mängu ajal `.xsdat` failide kaudu suhelda mõlemas suunas.

| Fail | Mis see on |
|---|---|
| `bridge_test.xs` | XS: iga 5 s kirjutab seisufaili (mänguaeg + loendur) ja loeb `claude_cmd.xsdat`-ist täisarvu chatti |
| `bridge_test.py` | Python: `install` (paigaldab XS + RMS), `run` (jälgib seisu, kirjutab käske), `dump` (hex-dump) |
| `LEIUD.md` | Tulemused ja avatud küsimused |

## 0. Ühekordne ettevalmistus

1. **Käivita mäng Steamist üks kord peamenüüni** ja sulge. Alles siis tekib kasutajakaust
   `~/.local/share/Steam/steamapps/compatdata/813780/pfx/drive_c/users/steamuser/Games/Age of Empires 2 DE/<steamId>/`
   (Windowsis `C:\Users\<user>\Games\Age of Empires 2 DE\<steamId>\`). Praegu seda kausta veel pole.
2. Paigalda skriptid:
   ```bash
   cd ~/Claude/AOE2
   python3 bridge_test.py install
   ```
   See kopeerib `bridge_test.xs` → `<steamId>/resources/_common/xs/` ja loob
   `<steamId>/resources/_common/random-map-scripts/ClaudeBridge.rms` (sinu Arabia koopia, mille 1. real on `#includeXS bridge_test.xs`).
   Mängu enda faile ei muudeta.

## 1. Test A – stsenaariumiredaktor (kõige lihtsam, alusta sellest)

1. Terminalis: `python3 bridge_test.py run` ja jäta see jooksma.
2. Mängus: **Editors → Create Scenario** (vaikeseaded sobivad).
3. Ava vahekaart **Map**, leia väli **Script Filename** (või sarnane) ja kirjuta `bridge_test` (ilma `.xs`-ita).
4. Vajuta **Test** (vasak ülanurk). Kui küsitakse, salvesta stsenaarium (nt `bridgetest`).
5. Oota 10–20 s ja vaata chatti.

## 2. Test B – juhuslik kaart AI vastu (lõpliku lahenduse kuju)

1. `python3 bridge_test.py run` jookseb.
2. **Single Player → Skirmish**, kaardi tüüp **Custom**, kaart **ClaudeBridge**. Lisa 1 AI. Start.
3. Vaata chatti.

## 3. Test C – AI loeb käske (`ClaudeAI.per` + `claude_ai.xs`)

Sama seadistus mis Test B, aga AI mängijaks vali **ClaudeAI** (sama tiim sinuga või eraldi, pole oluline).
Ahel: Python → `claude_cmd.xsdat` → `.per` kutsub iga 3 s `(xs-script-call "claudeAiPoll")` → XS seab goal'id 102/103 → `.per` reegel kirjutab chatti.

| Chatt | Tähendus |
|---|---|
| `[AI per] ClaudeAI laaditud, mangija N` | AI-skript laaditi |
| `[AI xs] claude_ai.xs laaditud, context player=N` | `include` töötas, XS on AI-le kättesaadav |
| `[AI xs] claude_cmd avanes otse` / `alles parast xsSetContextPlayer` | kas faili lugemiseks on vaja konteksti vahetada |
| `AI (.per) sai kasu: N` (N kasvab) | ✅ **kogu ahel töötab** |
| `[AI per] …` on, aga `[AI xs] …` pole | `include` ei leidnud faili profiili `xs/` kaustast |

## Mida chatis peaks nägema

| Chatt | Tähendus |
|---|---|
| `[bridge] bridge_test.xs laaditud` | XS laaditi (`main()` jooksis) |
| `[bridge] t=5 kirjutatud=1 claude_cmd: AVAMINE EBAONNESTUS` | XS töötab, aga ei leia käsufaili (Python pole veel õigesse kausta kirjutanud – peaks 5–10 s jooksul paranema) |
| `Claude utleb: 1`, `Claude utleb: 2`, … | ✅ **Test läbitud** – mäng loeb faili korduvalt kettalt |
| `[bridge] ... sama seq=N (Python pole vahepeal uut kasku kirjutanud)` | normaalne, kui see vaheldub `Claude utleb` ridadega (XS loeb mänguaja järgi, kiirusel 1,7× ~3 s tagant). ❌ Viga on ainult siis, kui N **ei kasva**, kuigi Python kirjutab uusi numbreid |
| `[bridge] xsCreateFile EBAONNESTUS` | seisufaili kirjutamine ei õnnestu |
| Mitte midagi | XS-i ei laaditud (vale skriptinimi / fail vales kaustas / süntaksiviga – vaata ka ekraanil XS-i veateadet) |

Terminalis peaks `run` näitama:
```
=== Uus .xsdat: .../<steamId>/profile/default0.xsdat (26 baiti)   <- hex-dump
*** XS kirjutab kausta: ...
[21:33:02] default0.xsdat: manguaeg=15 s  loendur=3 ...
[21:33:05] kask seq=2 vaartus=2 -> .../claude_cmd.xsdat
```

Kuni Python pole näinud ühtegi XS-i kirjutatud faili, kirjutab ta `claude_cmd.xsdat` igaks juhuks mitmesse kohta
(`<steamId>/profile`, `<steamId>/resources/_common/xs`, `<steamId>`). Kui seisufail ilmub, kirjutab ta ainult sinna kausta.
Kui seisufaili üldse ei leita, proovi `python3 bridge_test.py run --scan-install` ja otsi käsitsi:
```bash
find ~/.local/share/Steam/steamapps -name "*.xsdat"
```

## Mida mulle tagasi öelda

1. Chatiread (kasvõi paar esimest ja paar viimast).
2. Terminali väljund `run`-ist (eriti hex-dump ja „XS kirjutab kausta“ rida).
3. Kumb test (A/B) ja kas XS-i laadimisel tuli veateade.
