// bridge_test.xs - AoE2 DE <-> Claude silla 1. faasi test.
//
// Iga 5 s:
//   1) kirjutab seisufaili (xsCreateFile -> fail stsenaariumi/RMS-i nimega, nt default0.xsdat)
//   2) avab kasufaili claude_cmd.xsdat, loeb sealt taisarvu ja kirjutab chatti
//
// Seisufaili formaat (koik little-endian):
//   int   magic (20261029)
//   int   loendur
//   int   manguaeg sekundites
//   float manguaeg (formaadi kontrolliks)
//   string "bridge" (formaadi kontrolliks)
//
// Kasufaili formaat (kirjutab bridge_test.py):
//   int   magic (20261029)
//   int   jarjenumber
//   int   vaartus

const int cBridgeMagic = 20261029;

int gCounter = 0;
int gLastSeq = -1;

int writeState(int gameTime = 0) {
    if (xsCreateFile(false) == false) {
        return (0);
    }
    xsWriteInt(cBridgeMagic);
    xsWriteInt(gCounter);
    xsWriteInt(gameTime);
    xsWriteFloat(0.0 + gameTime);
    xsWriteString("bridge");
    xsCloseFile();
    return (1);
}

void readCommand(int gameTime = 0) {
    if (xsOpenFile("claude_cmd") == false) {
        xsChatData("[bridge] t=" + gameTime + " kirjutatud=" + gCounter + " claude_cmd: AVAMINE EBAONNESTUS");
        return;
    }
    int size = xsGetFileSize();
    if (size < 12) {
        xsCloseFile();
        xsChatData("[bridge] claude_cmd liiga lyhike, baite: %d", size);
        return;
    }
    int magic = xsReadInt();
    int seq = xsReadInt();
    int value = xsReadInt();
    xsCloseFile();

    if (magic != cBridgeMagic) {
        xsChatData("[bridge] vale magic: %d", magic);
        return;
    }
    if (seq == gLastSeq) {
        xsChatData("[bridge] t=" + gameTime + " sama seq=" + seq + " (Python pole vahepeal uut kasku kirjutanud)");
        return;
    }
    gLastSeq = seq;
    xsChatData("Claude utleb: %d", value);
}

rule bridgeTick
    active
    minInterval 5
{
    int gameTime = xsGetGameTime();
    gCounter++;
    if (writeState(gameTime) == 0) {
        xsChatData("[bridge] xsCreateFile EBAONNESTUS, t=%d", gameTime);
    }
    readCommand(gameTime);
}

void main() {
    xsChatData("[bridge] bridge_test.xs laaditud");
}
