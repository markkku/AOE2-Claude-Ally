// claude_ai.xs - carries out Claude's commands for the AI player (loaded by ClaudeAI.per: (include "claude_ai.xs")).
//
// ClaudeAI.per calls:
//   (xs-script-call "claudeAiPoll") every ~3 s: reads claude_cmd.xsdat, stores the command in goals
//                                    and computes simple flags for the .per (train villagers? save for age-up? ...)
//   (xs-script-call "claudeAiArmy") every ~8 s: moves the army according to the current mode
// No XS rules are used here, because rules do not run in the AI player's context.
//
// Goal numbers MUST match the defconsts in ClaudeAI.per.

const int cAiMagic = 20261029;
const int cAiVersion = 3;
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
const int cGoalWalls = 115;        // 0 none, 1 palisade, 2 stone
const int cGoalWallRing = 116;     // 1 inner, 2 outer perimeter
const int cGoalBuildAt = 117;      // 0 home, 1 near player cGoalBuildNear, 2 towards the enemy
const int cGoalBuildNear = 118;
// 121..129: whether unit type 1..9 is selected (as unit1 or unit2)
const int cGoalUsesBase = 120;
// 141..152: Claude's building targets; 161..172: 1 when more of that building is still needed.
// Order (same as BUILDINGS in claude_ally.py): barracks, archery range, stable, siege workshop, blacksmith,
// market, monastery, university, castle, town center, tower, dock
const int cGoalBuildTargetBase = 141;
const int cGoalBuildMoreBase = 161;

// unit choices (same as UNITS in claude_ally.py)
const int cUnitMilitia = 1;
const int cUnitSpear = 2;
const int cUnitArcher = 3;
const int cUnitSkirm = 4;
const int cUnitKnight = 5;
const int cUnitCavArcher = 6;
const int cUnitSiege = 7;
const int cUnitMonk = 8;
const int cUnitUnique = 9;
const int cUnitCount = 9;

// modes
const int cModeDefend = 0;
const int cModeAttack = 1;
const int cModeHelp = 2;

// object and tech IDs
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

// Object or class ID used to count building k (0..11).
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
    xsChatData("[Claude AI] ready, player %d", xsGetGoal(cGoalMyPlayer));
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
            xsChatData("[Claude AI] command file opened only after xsSetContextPlayer");
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
    int walls = 0;
    int wallRing = 2;
    int buildAt = 0;
    int buildNear = 0;
    if (gAiBuildRead < 0) {
        gAiBuildRead = xsArrayCreateInt(cAiBuildingCount, 0, "");
    }
    // XS cannot parse arithmetic on the right side of a comparison, so compute it first
    int minSize = cAiBuildingCount * 4;
    minSize = minSize + 56;
    if (xsGetFileSize() >= minSize) {
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
        walls = xsReadInt();
        wallRing = xsReadInt();
        buildAt = xsReadInt();
        buildNear = xsReadInt();
    }
    xsCloseFile();
    if (needContext) {
        xsSetContextPlayer(cp);
    }
    if (magic != cAiMagic || version != cAiVersion || seq == gAiLastSeq) {
        return;
    }
    // the command is meant only for Claude's player
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
    xsSetGoal(cGoalWalls, walls);
    xsSetGoal(cGoalWallRing, wallRing);
    xsSetGoal(cGoalBuildAt, buildAt);
    xsSetGoal(cGoalBuildNear, buildNear);
    for (k = 0; < cAiBuildingCount) {
        xsSetGoal(cGoalBuildTargetBase + k, xsArrayGetInt(gAiBuildRead, k));
    }
    xsSetGoal(cGoalCmdNew, 1);
}

int gAiAgeFood = 0;
int gAiAgeGold = 0;

// Whether to save resources for the next age (military production paused). Only when the age-up is
// actually available (required buildings exist); also sets gAiAgeFood/gAiAgeGold to its cost.
bool aiSaving(int me = 0, int age = 0, int vil = 0) {
    if (xsGetGoal(cGoalAgeUp) != 1 || age >= 3) {
        return (false);
    }
    int tech = cTechFeudal;
    int minVil = 19;
    gAiAgeFood = 500;
    gAiAgeGold = 0;
    if (age == 1) {
        tech = cTechCastle;
        minVil = 27;
        gAiAgeFood = 800;
        gAiAgeGold = 200;
    }
    if (age == 2) {
        tech = cTechImperial;
        minVil = 38;
        gAiAgeFood = 1000;
        gAiAgeGold = 800;
    }
    if (vil < minVil) {
        return (false);
    }
    return (xsGetTechState(tech, me) == cTechStateReady);
}


void aiUpdateFlags() {
    int me = xsGetGoal(cGoalMyPlayer);
    int age = xsPlayerAttribute(me, cAttributeCurrentAge);
    int vil = xsGetObjectCount(me, cVillagerClass);

    int vilTarget = xsGetGoal(cGoalVilTarget);
    bool wantVil = vil < vilTarget;
    bool saving = aiSaving(me, age, vil);
    xsSetGoal(cGoalSaving, aiBool(saving));
    // A town center that keeps training villagers can never start the age-up research,
    // so stop villagers once the age-up is affordable.
    if (saving) {
        int food = xsPlayerAttribute(me, cAttributeFood);
        int gold = xsPlayerAttribute(me, cAttributeGold);
        if (food >= gAiAgeFood && gold >= gAiAgeGold) {
            wantVil = false;
        }
    }
    xsSetGoal(cGoalWantVil, aiBool(wantVil));
    bool trainOk = (saving == false) || xsGetGoal(cGoalUnderAttack) == 1 || xsGetGoal(cGoalMode) != cModeDefend;
    xsSetGoal(cGoalTrainOk, aiBool(trainOk));

    for (u = 1; <= cUnitCount) {
        xsSetGoal(cGoalUsesBase + u, aiBool(aiUses(u)));
    }

    // buildings: keep building until Claude's target is met (counts ones under construction too)
    for (k = 0; < cAiBuildingCount) {
        int have = xsGetObjectCountTotal(me, aiBuildingId(k));
        int wanted = xsGetGoal(cGoalBuildTargetBase + k);
        xsSetGoal(cGoalBuildMoreBase + k, aiBool(have < wanted));
    }
}

void claudeAiPoll() {
    aiReadCommand();
    aiUpdateFlags();
}

// --- Army ---------------------------------------------------------------------

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
    // the scout keeps exploring unless cavalry is one of the chosen units
    if (aiUses(cUnitKnight)) {
        aiAddClass(me, cScoutCavalryClass);
    }
    if (aiUses(cUnitMonk)) {
        aiAddClass(me, cMonkClass);
    }
    // unique units belong to the classes above (infantry, archer, cavalry, ...)
}

// Player p's object/class nearest to a point (stored in gAiFound). Returns false if there is none.
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
        // the enemy building nearest to our town center
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

    // when defending, only units that wandered far away are sent home
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
        xsChatData("[Claude AI] mode (0 defend, 1 attack, 2 help): %d", mode);
        xsChatData("[Claude AI] target player: %d", target);
    }
}
