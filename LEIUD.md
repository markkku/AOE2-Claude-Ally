# LEIUD – AoE II DE ↔ Claude sild

_Seis: 2026-10-29. **1. faas läbitud, testid B (RMS) ja C (AI loeb käske) läbitud.**_

## 1. faasi tulemus

**Mäng loeb `.xsdat` faili mängu ajal korduvalt kettalt.** Kui Python muudab `claude_cmd.xsdat` faili, näeb XS järgmisel `xsOpenFile`-il uut sisu. Tõend: chatti kirjutatud `seq`, mille XS igal korral failist loeb, kasvas iga lugemisega. Seisufail jõudis Pythonini iga 5 mängusekundi järel (redaktori test, Test A).

| Küsimus | Vastus |
|---|---|
| Kas fail loetakse uuesti? | ✅ Jah. Iga `xsOpenFile` → `xsRead*` → `xsCloseFile` tsükkel loeb kettalt. Python kirjutab atomaarselt (`tmp` + `os.replace`). |
| Kuhu `.xsdat` tekib? | `…/Games/Age of Empires 2 DE/<steamId>/profile/`. Sinu masinas: `~/.local/share/Steam/steamapps/compatdata/813780/pfx/drive_c/users/steamuser/Games/Age of Empires 2 DE/76561199000857729/profile/` |
| Kust `xsOpenFile` loeb? | Samast `profile/` kaustast |
| Kas `xsOpenFile` avab suvalise nimega faili? | ✅ Jah, `xsOpenFile("claude_cmd")` töötab |
| Kas `xsCreateFile` nime saab valida? | ❌ Ei. Nimi = stsenaariumi nimi, redaktori testis `default0.xsdat`. RMS-mängus tõenäoliselt kaardi nimi (Test B tegemata). |
| Uue faili lisandumise viide | Fail kirjutati üle umbes iga 3 päris sekundi järel. 5 mängusekundit kiirusel 1,7× on ~2,9 s. |

### Test B ja C (2026-10-29, Skirmish, kaart ClaudeBridge, P2 = ClaudeAI) – ✅ mõlemad läbitud

- **Test B (RMS):** `#includeXS` töötab kasutaja RMS-is. Seisufaili nimi on **`ClaudeBridge.xsdat`**, sama mis kaardi nimi, ja see asub samas `profile/` kaustas. Chatis jooksis `Claude utleb: 64, 65, 66, 67, 69`.
- **Test C (AI):** `(include "claude_ai.xs")` leidis faili **profiili** `xs/` kaustast, nii et mängu kausta pole vaja midagi panna. `(xs-script-call "claudeAiPoll")` loeb AI kontekstis `claude_cmd.xsdat` faili, `xsSetGoal` seab goal'i ja `.per` reegel `(up-compare-goal …)` reageerib. Chatis jooksis `2 ClaudeAI: AI (.per) sai kasu: 58 … 68`, kõik numbrid järjest.
- Kaardi XS jättis vahele numbri 68, sest Python kirjutas kiiremini, kui XS luges. Käsuprotokollis kehtib alati viimane käsk, seega see pole probleem. Päris käskude puhul ei tohi samm vahele jääda: Python peab käsku hoidma, kuni XS on selle kinnitanud (ack seisufailis).
- Kas AI XS avas faili otse või alles pärast `xsSetContextPlayer`-it, jäi nägemata (rida kerkis chatist välja). Tulemus töötab mõlemal juhul.
- Viga ja parandus: AI-käsk on `enable-timer`, mitte `enable-timers` (err2005 invalid identifier).

**Ajastus:** XS-i reeglid (`minInterval`) käivad **mänguaja** järgi. DE vaikekiirus on 1,7×, nii et 5 mängusekundit on ~2,9 päris sekundit. Esimeses testis kirjutas Python iga 5 päris sekundi järel, mistõttu iga teine XS-i lugemine nägi sama `seq` väärtust. See on ootuspärane, mitte viga. Pythoni intervall on nüüd 2 s.

**Märkus:** mängu kaustas on ka profiil `0/` (lisaks `76561199000857729/`). `install` paigaldab mõlemasse.

## Keskkond

| Asi | Väärtus |
|---|---|
| OS | Fedora Linux, mäng Steam Protoni all (appid 813780) |
| Paigaldus | `~/.local/share/Steam/steamapps/common/AoE2DE/` |
| Kasutajakaust | `.../pfx/drive_c/users/steamuser/Games/Age of Empires 2 DE/76561199000857729/` |
| Kasutaja XS | `<steamId>/resources/_common/xs/` |
| Kasutaja RMS | `<steamId>/resources/_common/random-map-scripts/` |
| Mängu AI-d | `AoE2DE/resources/_common/ai/` (nt Promisory) |
| Python | 3.14.8 |
| Claude CLI | `~/.local/bin/claude` 2.1.312; `ANTHROPIC_API_KEY` pole seadistatud |
| XS linter | `xs-check` v0.2.31 (Divy1211) |

## `.xsdat` formaat (kinnitatud hex-dumpiga)

Päist pole, väärtused on järjestikku ja little-endian.

```
a5 28 35 01  34 00 00 00  04 01 00 00  00 00 82 43  06 00 00 00  62 72 69 64 67 65
magic        loendur=52   aeg=260      float 260.0  str len=6    "bridge"
```

| Tüüp | Baidid |
|---|---|
| int | 4, signed int32 LE |
| float | 4, IEEE 754 float32 LE |
| vector | 12, 3 × float32 (dokumentatsiooni järgi, testimata) |
| string | uint32 LE pikkus + 1 bait tähe kohta (ASCII). Täpitähti pole testitud. |

`xsCreateFile(false)` kirjutab faili iga kord üle (26 baiti).

---

## 3. faasi uuring

### 3.1 Milliseid andmeid XS mängust loeb

Allikas on `xs-check` `prelude.xs` (DE XS API).

| Andmed | Funktsioon |
|---|---|
| Ressursid | `xsPlayerAttribute(p, cAttributeFood/Wood/Stone/Gold)` (0–3) |
| Populatsioon / limiit | `cAttributePopulation` (11), `cAttributePopulationCap` (4), `cAttributeCivilianPopulation` (37), `cAttributeMilitaryPopulation` (40) |
| Ajastu | `cAttributeCurrentAge` (6) |
| Tapmised, kogutud ressursid jms | `cAttributeKills` (20), `cAttribute*Total` (166–169), skoorid |
| Üksuste arv tüübi või klassi järgi | `xsGetObjectCount(p, unitOrClassId)`, `xsGetObjectCountTotal` (koos ehitamisel olevatega) |
| Üksuste ID-d | `xsGetPlayerUnitIds(p, unitOrClass, arrayId)`, seejärel `xsGetUnitPosition`, `xsGetUnitHitpoints`, `xsGetUnitTargetUnitId`, `xsGetUnitMoveTarget`, `xsGetUnitClass` |
| Tehnoloogiad | `xsGetTechState(tech, p)`, `xsGetPlayerNumberOfTechs` |
| Mängijad | `xsGetNumPlayers`, `xsGetPlayerCivilization`, `xsGetPlayerName`, `xsGetPlayerInGame`, `xsGetPlayerType` |
| Liitlased/vaenlased | `xsGetDiplomacy(a, b)` → `cDiplomacyAlly` (0), `Neutral` (1), `Enemy` (3) |
| Kaart, aeg | `xsGetMapWidth/Height`, `xsGetGameTime`, `xsGetTurn` |

⚠️ **Need funktsioonid näevad kõike, ka sõjaudu taga.** Vaenlase üksuste lugemine on sisuliselt „maphack”. Ausa mängu jaoks tuleb otsustada, mida Claude'ile näidata. Variandid:
- ainult oma ja liitlaste andmed;
- vaenlase kohta ainult see, mis on nähtav. Selle jaoks on `xsUnsyncIsUnitVisible(unitId, allowInFog, playerId)`, mis on unsync-funktsioon, aga üksikmängus kasutatav.

Kaardi-XS (RMS `#includeXS`) saab koguda andmeid **kõigi mängijate kohta ühes kohas** ja kirjutada need ühte seisufaili. See on lihtsaim lahendus.

### 3.2 Kuidas XS saab AI-skriptile (.per) käske anda

**Kinnitatud mehhanism: `include` + `xs-script-call` + goal'id.** Seda kasutab mängu enda AI **Promisory**: `ai/Promisory/scoutcontrol.per` kutsub `(xs-script-call "RotateByAngleNoConvert")` funktsiooni failist `xs/ailib/Geometry.xs`. Andmed liiguvad goal'ide kaudu: `.per` teeb `set-goal`, XS loeb `xsGetGoal`-iga ja kirjutab tulemuse `xsSetGoal`-iga.

- `.per`: `(include "claude_ai.xs")`. `.xs` laiend on kohustuslik ja rida peab olema **pärast kõiki `load` käske**, muidu XS-i ei laadita (airef, teadaolev viga). Fail otsitakse `xs/` kaustast. Suhteline tee `../ai/...` mod'ides ei tööta.
- `.per`: `(xs-script-call "claudePoll")` kutsub parameetriteta XS-funktsiooni **selle AI mängija kontekstis**.
- XS: `xsGetGoal(id)` / `xsSetGoal(id, v)` / `xsGetStrategicNumber` / `xsSetStrategicNumber` mõjutavad **ainult seda AI-d**, kes funktsiooni kutsus.
- airef'i järgi: XS-i reeglid (`rule`) ei tööta AI-de puhul mängijapõhiselt. AI XS-koodis tuleks kasutada ainult `xs-script-call`-iga kutsutud funktsioone. Globaalsed muutujad on iga AI jaoks eraldi.
- airef: AI kontekstis tuleb enne faili-I/O-d kutsuda `xsSetContextPlayer(...)`.

**Plaanitud käsuvoog (ehitamata):**
```
Python → claude_cmd.xsdat → (AI .per iga N s) xs-script-call "claudePoll"
       → XS: xsOpenFile + xsReadInt → xsSetGoal(gClaudeUnit, …), xsSetGoal(gClaudeAttack, …)
       → .per reeglid: (goal gClaudeAttack 1) => (attack-now) jne
```
Seis kirjutatakse samuti. Kas AI saab ise `xsCreateFile`-iga kirjutada ja mis nimega fail tekib, on teadmata. Lihtsam on lasta kaardi-XS-il seis kirjutada ja AI-XS-il ainult käske lugeda.

**Alternatiivid (testimata):**
- `xsSetAiSignal(signalId, value)` / `xsGetAiSignal` kaardi-XS-ist ja `.per`-is `up-get-signal`/`fe-set-signal`. Võimaldaks kaardi-XS-il saata käske kõigile AI-dele ilma `include`'ita.
- Kaardi-XS-is `xsSetContextPlayer(ai)` + `xsSetGoal(...)`. On teadmata, kas see väljaspool AI konteksti mõjub.
- Kaardi-XS juhib üksusi otse (`xsTaskUnits`, `xsTrainObject`, `xsResearchTechnology`). See on võimas, aga osa käske on „cheat” (nt kohene uurimine).

### 3.3 Kuidas Python küsib Claude'ilt otsust

Mõõdetud 2026-10-29: `claude -p --output-format json`, realistlik seisuprompt (~300 märki), vastuseks 1-realine JSON.

| Mudel | Seinaaeg | API aeg |
|---|---|---|
| haiku | 6,1–7,1 s | 3,2–3,8 s |
| sonnet | 6,0–6,2 s | 3,0–3,3 s |

- **`claude -p`** töötab kohe sinu Claude'i tellimusega ja API-võtit pole vaja. CLI käivitus lisab ~3 s. **6–7 s mahub hästi 30–60 s tsüklisse.**
- **Anthropic API** (`anthropic` Pythoni pakett) jätab CLI käivituse ära ja annaks eeldatavasti ~1–4 s. Selleks on vaja `ANTHROPIC_API_KEY`-d ja eraldi arveldust. Struktureeritud väljundi (tool use / JSON schema) saab sundida kindla kujuga.
- Vastus polnud ühtlane (`"spear"` vs `"spearman"`). Lõpplahenduses peab olema kindel valikute loend (enum) ja Python peab vastuse valideerima.
- Otsuse ajal mäng ei peatu. Claude'i otsus põhineb 6–10 s vanal seisul, mis strateegiliseks tasemeks sobib.

### Avatud küsimused järgmiseks sammuks

- [x] Test B: `#includeXS` töötab, fail on `ClaudeBridge.xsdat`
- [x] AI-XS: `xsOpenFile` töötab `xs-script-call`'i kontekstis (kas `xsSetContextPlayer` on vajalik, jäi kinnitamata)
- [ ] Kas kaardi-XS saab AI goal'e mõjutada (`xsSetContextPlayer` + `xsSetGoal` või `xsSetAiSignal`)
- [ ] Kuidas eristada „minu tiimikaaslase” AI-d (mängija number) teistest AI-dest

## Allikad

- [Divy1211/xs-check](https://github.com/Divy1211/xs-check) – `xsc-core/prelude.xs`
- [Divy1211/vsc-xs-support](https://github.com/Divy1211/vsc-xs-support)
- [airef: XS Scripting for AI Tournaments](https://airef.github.io/resources/articles/xs-for-tournaments.html) ja [käsuviide](https://airef.github.io/) (`include`, `xs-script-call`)
- Mängu enda failid: `ai/Promisory/scoutcontrol.per`, `xs/ailib/Geometry.xs`
- [AoE foorum: .xsdat kampaaniates](https://forums.ageofempires.com/t/xsdat-file-cannot-be-stored-in-correct-file-as-expected-for-campaigns/204962)
- [AoE foorum: goal'id AI-skriptides](https://forums.ageofempires.com/t/using-goals-to-clean-up-ai-scripts/205241)
