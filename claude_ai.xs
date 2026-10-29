// claude_ai.xs - Claude'i kasud AI-le (laaditakse ClaudeAI.per-is: (include "claude_ai.xs")).
//
// ClaudeAI.per kutsub:
//   (xs-script-call "claudeAiPoll") ~3 s tagant: loeb claude_cmd.xsdat, seab kasu-goal'id
//                                    ja arvutab .per-ile lihtsad lipud (kas teha kyla, kas koguda ajastuks jne)
//   (xs-script-call "claudeAiArmy") ~8 s tagant: liigutab armeed vastavalt reziimile
// XS-i reegleid (rule) siin ei kasutata, sest need ei jookse AI-mangija kontekstis.
//
// Goal'id - PEAVAD klappima ClaudeAI.per defconst'idega.

const int cAiMagic = 20261029;
const int cAiVersion = 2;
const int cAiBuildingCount = 12;

const int cGoalMyPlayer = 101;
const int cGoalSeq = 102;
const int cGoalCmdNew = 103;
const int cGoalUnit1 = 105;
const int cGoalUnit2 = 106;
const int cGoalMode = 107;
const int cGoalTarget = 108;
const int cGoalAgeUp = 109;
const int cGoalVilTarget = 110;
const int cGoalWantVil = 111;
const int cGoalUnderAttack = 112;
const int cGoalTrainOk = 113;
const int cGoalSaving = 114;
// 121..128: kas yksusetyyp 1..8 on valitud (unit1 voi unit2)
const int cGoalUsesBase = 120;
// 141..152: Claude'i hoonete sihtarvud; 161..172: 1, kui sellest hoonest on veel puudu.
// Jarjekord (sama mis general.py BUILDINGS): kasarmud, laskevali, tall, piiramistookoda, sepikoda,
// turg, klooster, ylikool, loss, linnakeskus, torn, sadam
const int cGoalBuildTargetBase = 141;
const int cGoalBuildMoreBase = 161;

// yksuste valikud (sama mis general.py UNITS)
const int cUnitMilitia = 1;
const int cUnitSpear = 2;
const int cUnitArcher = 3;
const int cUnitSkirm = 4;
const int cUnitKnight = 5;
const int cUnitCavArcher = 6;
const int cUnitSiege = 7;
const int cUnitMonk = 8;

// reziimid
const int cModeDefend = 0;
const int cModeAttack = 1;
const int cModeHelp = 2;

// objektide ID-d
const int cIdTownCenter = 109;
const int cTechFeudal = 101;
const int cTechCastle = 102;
const int cTechImperial = 103;

int gAiLastSeq = -1;
int gAiIds = -1;
int gAiArmy = -1;
int gAiArmyCount = 0;
int gAiSend = -1;
bool gAiReportedOpen = false;
int gAiLastMode = -1;
int gAiLastTarget = -1;
int gAiBuildRead = -1;

// Hoone k (0..11) objekti- voi klassi-ID loendamiseks.
int aiBuildingId(int k = 0) {
    if (k == 0) { return (12); }
    if (k == 1) { return (87); }
    if (k == 2) { return (101); }
    if (k == 3) { return (49); }
    if (k == 4) { return (103); }
    if (k == 5) { return (84); }
    if (k == 6) { return (104); }
    if (k == 7) { return (209); }
    if (k == 8) { return (82); }
    if (k == 9) { return (cIdTownCenter); }
    if (k == 10) { return (cTowerClass); }
    return (45);
}

void claudeAiInit() {
    xsChatData("[Claude AI] valmis, mangija %d", xsGetGoal(cGoalMyPlayer));
}

bool aiUses(int unit = 0) {
    return (xsGetGoal(cGoalUnit1) == unit || xsGetGoal(cGoalUnit2) == unit);
}

int aiBool(bool b = false) {
    if (b) {
        return (1);
    }
    return (0);
}

void aiReadCommand() {
    int cp = xsGetContextPlayer();
    bool needContext = false;
    if (xsOpenFile("claude_cmd") == false) {
        xsSetContextPlayer(xsGetGoal(cGoalMyPlayer));
        needContext = true;
        if (xsOpenFile("claude_cmd") == false) {
            xsSetContextPlayer(cp);
            return;
        }
    }
    if (gAiReportedOpen == false) {
        gAiReportedOpen = true;
        if (needContext) {
            xsChatData("[Claude AI] kasufail avanes parast xsSetContextPlayer");
        }
    }
    int magic = 0;
    int version = 0;
    int seq = 0;
    int claude = 0;
    int unit1 = 0;
    int unit2 = 0;
    int mode = 0;
    int target = 0;
    int ageUp = 0;
    int vilTarget = 0;
    if (gAiBuildRead < 0) {
        gAiBuildRead = xsArrayCreateInt(cAiBuildingCount, 0, "");
    }
    if (xsGetFileSize() >= 40 + cAiBuildingCount * 4) {
        magic = xsReadInt();
        version = xsReadInt();
        seq = xsReadInt();
        claude = xsReadInt();
        unit1 = xsReadInt();
        unit2 = xsReadInt();
        mode = xsReadInt();
        target = xsReadInt();
        ageUp = xsReadInt();
        vilTarget = xsReadInt();
        for (k = 0; < cAiBuildingCount) {
            xsArraySetInt(gAiBuildRead, k, xsReadInt());
        }
    }
    xsCloseFile();
    if (needContext) {
        xsSetContextPlayer(cp);
    }
    if (magic != cAiMagic || version != cAiVersion || seq == gAiLastSeq) {
        return;
    }
    // kask on moeldud ainult Claude'i mangijale
    if (claude != xsGetGoal(cGoalMyPlayer)) {
        return;
    }
    gAiLastSeq = seq;
    xsSetGoal(cGoalSeq, seq);
    xsSetGoal(cGoalUnit1, unit1);
    xsSetGoal(cGoalUnit2, unit2);
    xsSetGoal(cGoalMode, mode);
    xsSetGoal(cGoalTarget, target);
    xsSetGoal(cGoalAgeUp, ageUp);
    xsSetGoal(cGoalVilTarget, vilTarget);
    for (k = 0; < cAiBuildingCount) {
        xsSetGoal(cGoalBuildTargetBase + k, xsArrayGetInt(gAiBuildRead, k));
    }
    xsSetGoal(cGoalCmdNew, 1);
}

// Kas tasub ajastu jaoks ressursse koguda (sojavae tootmine pausile).
bool aiSaving(int me = 0, int age = 0, int vil = 0) {
    if (xsGetGoal(cGoalAgeUp) != 1 || age >= 3) {
        return (false);
    }
    int tech = cTechFeudal;
    int minVil = 19;
    if (age == 1) {
        tech = cTechCastle;
        minVil = 27;
    }
    if (age == 2) {
        tech = cTechImperial;
        minVil = 38;
    }
    if (vil < minVil) {
        return (false);
    }
    int state = xsGetTechState(tech, me);
    return (state == cTechStateReady || state == cTechStateNotReady);
}


void aiUpdateFlags() {
    int me = xsGetGoal(cGoalMyPlayer);
    int age = xsPlayerAttribute(me, cAttributeCurrentAge);
    int vil = xsGetObjectCount(me, cVillagerClass);

    xsSetGoal(cGoalWantVil, aiBool(vil < xsGetGoal(cGoalVilTarget)));

    bool saving = aiSaving(me, age, vil);
    xsSetGoal(cGoalSaving, aiBool(saving));
    bool trainOk = (saving == false) || xsGetGoal(cGoalUnderAttack) == 1 || xsGetGoal(cGoalMode) != cModeDefend;
    xsSetGoal(cGoalTrainOk, aiBool(trainOk));

    for (u = 1; <= 8) {
        xsSetGoal(cGoalUsesBase + u, aiBool(aiUses(u)));
    }

    // hooned: ehita juurde, kuni Claude'i sihtarv on taidetud (arvestab ka ehitamisel olevaid)
    for (k = 0; < cAiBuildingCount) {
        int have = xsGetObjectCountTotal(me, aiBuildingId(k));
        xsSetGoal(cGoalBuildMoreBase + k, aiBool(have < xsGetGoal(cGoalBuildTargetBase + k)));
    }
}

void claudeAiPoll() {
    aiReadCommand();
    aiUpdateFlags();
}

// --- Armee -------------------------------------------------------------------

void aiAddClass(int me = 0, int classId = 0) {
    gAiIds = xsGetPlayerUnitIds(me, classId, gAiIds);
    int n = xsArrayGetSize(gAiIds);
    for (i = 0; < n) {
        if (gAiArmyCount >= xsArrayGetSize(gAiArmy)) {
            xsArrayResizeInt(gAiArmy, gAiArmyCount + 50);
        }
        xsArraySetInt(gAiArmy, gAiArmyCount, xsArrayGetInt(gAiIds, i));
        gAiArmyCount++;
    }
}

void aiCollectArmy(int me = 0) {
    if (gAiArmy < 0) {
        gAiArmy = xsArrayCreateInt(100, -1, "");
    }
    gAiArmyCount = 0;
    aiAddClass(me, cInfantryClass);
    aiAddClass(me, cTwoHandedSwordsmanClass);
    aiAddClass(me, cPikemanClass);
    aiAddClass(me, cSpearmanClass);
    aiAddClass(me, cArcherClass);
    aiAddClass(me, cHandCannoneerClass);
    aiAddClass(me, cCavalryClass);
    aiAddClass(me, cWarElephantClass);
    aiAddClass(me, cCavalryArcherClass);
    aiAddClass(me, cElephantArcherClass);
    aiAddClass(me, cConquistadorClass);
    aiAddClass(me, cSiegeWeaponClass);
    aiAddClass(me, cUnpackedSiegeUnitClass);
    aiAddClass(me, cScorpionClass);
    // skaut jaab luurama, kui teda pole valitud pohiyksuseks
    if (aiUses(cUnitKnight)) {
        aiAddClass(me, cScoutCavalryClass);
    }
    if (aiUses(cUnitMonk)) {
        aiAddClass(me, cMonkClass);
    }
}

// Mangija p objekt/klass, mis on punktile koige lahemal. Kui pole, tagastab false.
vector gAiFound = vector(0, 0, 0);

bool aiFindNearest(int p = 0, int objectOrClass = 0, vector from = vector(0, 0, 0)) {
    gAiIds = xsGetPlayerUnitIds(p, objectOrClass, gAiIds);
    int n = xsArrayGetSize(gAiIds);
    if (n <= 0) {
        return (false);
    }
    float best = 100000.0;
    for (i = 0; < n) {
        vector pos = xsGetUnitPosition(xsArrayGetInt(gAiIds, i));
        float d = dist(from, pos);
        if (d < best) {
            best = d;
            gAiFound = pos;
        }
    }
    return (true);
}

void claudeAiArmy() {
    int me = xsGetGoal(cGoalMyPlayer);
    int mode = xsGetGoal(cGoalMode);
    int target = xsGetGoal(cGoalTarget);

    vector home = vector(0, 0, 0);
    if (aiFindNearest(me, cIdTownCenter, vector(0, 0, 0)) == false) {
        return;
    }
    home = gAiFound;

    aiCollectArmy(me);
    if (gAiArmyCount <= 0) {
        return;
    }

    vector dest = home;
    if (mode == cModeAttack && target > 0) {
        // lahim vaenlase hoone meie linnakeskusest
        if (aiFindNearest(target, cBuildingClass, home) == false) {
            return;
        }
        dest = gAiFound;
    }
    if (mode == cModeHelp && target > 0) {
        if (aiFindNearest(target, cIdTownCenter, home) == false) {
            return;
        }
        dest = gAiFound;
    }

    // kaitses saadame koju ainult kaugele jaanud yksused
    if (gAiSend < 0) {
        gAiSend = xsArrayCreateInt(gAiArmyCount, -1, "");
    }
    xsArrayResizeInt(gAiSend, gAiArmyCount);
    int sendCount = 0;
    for (i = 0; < gAiArmyCount) {
        int id = xsArrayGetInt(gAiArmy, i);
        if (mode == cModeDefend) {
            if (dist(xsGetUnitPosition(id), home) < 30) {
                continue;
            }
        }
        xsArraySetInt(gAiSend, sendCount, id);
        sendCount++;
    }
    if (sendCount > 0) {
        xsArrayResizeInt(gAiSend, sendCount);
        xsTaskUnits(gAiSend, cActionTypeAttackMove, dest);
    }
    if (mode != gAiLastMode || target != gAiLastTarget) {
        gAiLastMode = mode;
        gAiLastTarget = target;
        xsChatData("[Claude AI] reziim (0 kaitse, 1 rynnak, 2 abi): %d", mode);
        xsChatData("[Claude AI] siht-mangija: %d", target);
    }
}
