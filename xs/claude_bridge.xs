// claude_bridge.xs - map-side XS (added to a random map script with: #includeXS claude_bridge.xs).
//
// 1) Every 5 game seconds writes the state file <map name>.xsdat:
//      int magic, int version, int counter, int gameTime, int lastCmdSeq, int claudePlayer,
//      int localPlayer, 8 x string (info for players 1..8 as "k=v;k=v;", empty if no such player)
//    Teammates (Claude + allies): resources, population, army, buildings, threat near town centers.
//    Enemies: age and ONLY the units currently visible to the local (human) player.
// 2) Every 2 game seconds reads claude_cmd.xsdat and, when seq is new, shows Claude's message
//    in chat. The command itself is carried out by the AI (claude_ai.xs + ClaudeAI.per).
//
// claude_cmd.xsdat (version 2): int magic, int version, int seq, int claudePlayer, int unit1, int unit2,
//                   int mode, int target, int ageUp, int vilTarget, 12 x int building targets, string message

const int cBrMagic = 20261029;
const int cBrVersion = 1;
const int cBrCmdVersion = 2;
const int cBrCmdInts = 22;
const int cBrTownCenter = 109;
const int cBrCastle = 82;
const int cBrThreatRadius = 20;
const int cBrMaxPos = 400;

int gBrCounter = 0;
int gBrLastSeq = -1;
int gBrClaude = 2;
int gBrIds = -1;
int gBrTcIds = -1;
int gBrPos = -1;
int gBrPosCount = 0;

int brCount(int p = 0, int c = 0) {
    return (xsGetObjectCount(p, c));
}

int brInf(int p = 0) {
    return (brCount(p, cInfantryClass) + brCount(p, cTwoHandedSwordsmanClass) + brCount(p, cPikemanClass) + brCount(p, cSpearmanClass));
}

int brArch(int p = 0) {
    return (brCount(p, cArcherClass) + brCount(p, cHandCannoneerClass));
}

int brCav(int p = 0) {
    return (brCount(p, cCavalryClass) + brCount(p, cScoutCavalryClass) + brCount(p, cWarElephantClass) + brCount(p, cRaiderClass) + brCount(p, cCavalryRaiderClass));
}

int brCavArch(int p = 0) {
    return (brCount(p, cCavalryArcherClass) + brCount(p, cElephantArcherClass) + brCount(p, cConquistadorClass));
}

int brSiege(int p = 0) {
    return (brCount(p, cSiegeWeaponClass) + brCount(p, cUnpackedSiegeUnitClass) + brCount(p, cScorpionClass) + brCount(p, cPetardClass));
}

int brMonk(int p = 0) {
    return (brCount(p, cMonkClass) + brCount(p, cMonkWithRelicClass));
}

int brShip(int p = 0) {
    return (brCount(p, cWarshipClass) + brCount(p, cBoardingShipClass));
}

// Counts player p's visible units of class c; military positions are stored for the threat calculation.
int brVisible(int p = 0, int c = 0, bool military = true) {
    gBrIds = xsGetPlayerUnitIds(p, c, gBrIds);
    int n = xsArrayGetSize(gBrIds);
    int seen = 0;
    for (i = 0; < n) {
        int id = xsArrayGetInt(gBrIds, i);
        if (xsUnsyncIsUnitVisible(id, false, -1)) {
            seen++;
            if (military && gBrPosCount < cBrMaxPos) {
                xsArraySetVector(gBrPos, gBrPosCount, xsGetUnitPosition(id));
                gBrPosCount++;
            }
        }
    }
    return (seen);
}

// How many visible enemy military units are near player p's town centers.
int brThreat(int p = 0) {
    gBrTcIds = xsGetPlayerUnitIds(p, cBrTownCenter, gBrTcIds);
    int nTc = xsArrayGetSize(gBrTcIds);
    int threat = 0;
    for (t = 0; < nTc) {
        vector tc = xsGetUnitPosition(xsArrayGetInt(gBrTcIds, t));
        for (k = 0; < gBrPosCount) {
            if (dist(tc, xsArrayGetVector(gBrPos, k)) < cBrThreatRadius) {
                threat++;
            }
        }
    }
    return (threat);
}

bool brIsTeam(int p = 0) {
    if (p == gBrClaude) {
        return (true);
    }
    return (xsGetDiplomacy(gBrClaude, p) == cDiplomacyAlly);
}

string brCommon(int p = 0) {
    int age = xsPlayerAttribute(p, cAttributeCurrentAge);
    string s = "p=" + p + ";team=" + brIsTeam(p) + ";type=" + xsGetPlayerType(p) + ";civ=" + xsGetPlayerCivName(p, false) + ";age=" + age;
    return (s);
}

string brTeamInfo(int p = 0) {
    int food = xsPlayerAttribute(p, cAttributeFood);
    int wood = xsPlayerAttribute(p, cAttributeWood);
    int gold = xsPlayerAttribute(p, cAttributeGold);
    int stone = xsPlayerAttribute(p, cAttributeStone);
    int pop = xsPlayerAttribute(p, cAttributePopulation);
    int popcap = xsPlayerAttribute(p, cAttributePopulationCap);
    int kills = xsPlayerAttribute(p, cAttributeKills);
    string s = brCommon(p);
    s = s + ";food=" + food + ";wood=" + wood + ";gold=" + gold + ";stone=" + stone;
    s = s + ";pop=" + pop + ";popcap=" + popcap + ";vil=" + brCount(p, cVillagerClass);
    s = s + ";inf=" + brInf(p) + ";arch=" + brArch(p) + ";cav=" + brCav(p) + ";cavarch=" + brCavArch(p);
    s = s + ";siege=" + brSiege(p) + ";monk=" + brMonk(p) + ";ship=" + brShip(p);
    s = s + ";tc=" + brCount(p, cBrTownCenter) + ";castle=" + brCount(p, cBrCastle) + ";kills=" + kills;
    // buildings (including ones under construction)
    s = s + ";b_barracks=" + xsGetObjectCountTotal(p, 12) + ";b_range=" + xsGetObjectCountTotal(p, 87);
    s = s + ";b_stable=" + xsGetObjectCountTotal(p, 101) + ";b_workshop=" + xsGetObjectCountTotal(p, 49);
    s = s + ";b_blacksmith=" + xsGetObjectCountTotal(p, 103) + ";b_market=" + xsGetObjectCountTotal(p, 84);
    s = s + ";b_monastery=" + xsGetObjectCountTotal(p, 104) + ";b_university=" + xsGetObjectCountTotal(p, 209);
    s = s + ";b_castle=" + xsGetObjectCountTotal(p, cBrCastle) + ";b_tc=" + xsGetObjectCountTotal(p, cBrTownCenter);
    s = s + ";b_tower=" + xsGetObjectCountTotal(p, cTowerClass) + ";b_dock=" + xsGetObjectCountTotal(p, 45);
    s = s + ";b_house=" + xsGetObjectCountTotal(p, 70) + ";b_farm=" + xsGetObjectCountTotal(p, 50);
    return (s);
}

string brEnemyInfo(int p = 0) {
    string s = brCommon(p);
    int inf = brVisible(p, cInfantryClass, true) + brVisible(p, cTwoHandedSwordsmanClass, true) + brVisible(p, cPikemanClass, true) + brVisible(p, cSpearmanClass, true);
    int arch = brVisible(p, cArcherClass, true) + brVisible(p, cHandCannoneerClass, true);
    int cav = brVisible(p, cCavalryClass, true) + brVisible(p, cScoutCavalryClass, true) + brVisible(p, cWarElephantClass, true) + brVisible(p, cRaiderClass, true) + brVisible(p, cCavalryRaiderClass, true);
    int cavarch = brVisible(p, cCavalryArcherClass, true) + brVisible(p, cElephantArcherClass, true) + brVisible(p, cConquistadorClass, true);
    int siege = brVisible(p, cSiegeWeaponClass, true) + brVisible(p, cUnpackedSiegeUnitClass, true) + brVisible(p, cScorpionClass, true) + brVisible(p, cPetardClass, true);
    int monk = brVisible(p, cMonkClass, true);
    int ship = brVisible(p, cWarshipClass, true) + brVisible(p, cBoardingShipClass, true);
    int vil = brVisible(p, cVillagerClass, false);
    int tc = brVisible(p, cBrTownCenter, false);
    int castle = brVisible(p, cBrCastle, false);
    s = s + ";vis_inf=" + inf + ";vis_arch=" + arch + ";vis_cav=" + cav + ";vis_cavarch=" + cavarch;
    s = s + ";vis_siege=" + siege + ";vis_monk=" + monk + ";vis_ship=" + ship + ";vis_vil=" + vil;
    s = s + ";vis_tc=" + tc + ";vis_castle=" + castle;
    return (s);
}

void brWriteState() {
    if (gBrPos < 0) {
        gBrPos = xsArrayCreateVector(cBrMaxPos, vector(0, 0, 0), "brEnemyPos");
    }
    gBrPosCount = 0;

    // enemies first, so their positions are known for the threat calculation
    string info1 = "";
    string info2 = "";
    string info3 = "";
    string info4 = "";
    string info5 = "";
    string info6 = "";
    string info7 = "";
    string info8 = "";
    for (pass = 0; < 2) {
        for (p = 1; <= 8) {
            if (xsGetPlayerInGame(p) == false) {
                continue;
            }
            string s = "";
            if (pass == 0 && brIsTeam(p) == false) {
                s = brEnemyInfo(p);
            }
            if (pass == 1 && brIsTeam(p)) {
                s = brTeamInfo(p) + ";threat=" + brThreat(p);
            }
            if (s == "") {
                continue;
            }
            if (p == 1) { info1 = s; }
            if (p == 2) { info2 = s; }
            if (p == 3) { info3 = s; }
            if (p == 4) { info4 = s; }
            if (p == 5) { info5 = s; }
            if (p == 6) { info6 = s; }
            if (p == 7) { info7 = s; }
            if (p == 8) { info8 = s; }
        }
    }

    if (xsCreateFile(false) == false) {
        return;
    }
    xsWriteInt(cBrMagic);
    xsWriteInt(cBrVersion);
    xsWriteInt(gBrCounter);
    xsWriteInt(xsGetGameTime());
    xsWriteInt(gBrLastSeq);
    xsWriteInt(gBrClaude);
    xsWriteInt(xsUnsyncGetLocalPlayerId());
    xsWriteString(info1);
    xsWriteString(info2);
    xsWriteString(info3);
    xsWriteString(info4);
    xsWriteString(info5);
    xsWriteString(info6);
    xsWriteString(info7);
    xsWriteString(info8);
    xsCloseFile();
}

void brReadCommand() {
    if (xsOpenFile("claude_cmd") == false) {
        return;
    }
    // XS cannot parse arithmetic on the right side of a comparison, so compute it first
    int minSize = cBrCmdInts * 4;
    minSize = minSize + 4;
    if (xsGetFileSize() < minSize) {
        xsCloseFile();
        return;
    }
    int magic = xsReadInt();
    int version = xsReadInt();
    int seq = xsReadInt();
    int claude = xsReadInt();
    // the remaining ints (units, mode, buildings) are used by the AI
    int msgPos = cBrCmdInts * 4;
    xsSetFilePosition(msgPos);
    string msg = xsReadString();
    xsCloseFile();

    if (magic != cBrMagic || version != cBrCmdVersion || seq == gBrLastSeq) {
        return;
    }
    gBrLastSeq = seq;
    gBrClaude = claude;
    if (msg != "") {
        xsChatData(xsGetPlayerColorTag(claude) + "Claude: " + msg);
    }
}

rule brStateTick
    active
    minInterval 5
{
    gBrCounter++;
    brWriteState();
}

rule brCommandTick
    active
    minInterval 2
{
    brReadCommand();
}

void main() {
    xsChatData("[Claude] bridge active");
}
