// bridge_test.xs - low-level test of the XS <-> external program file bridge.
//
// Every 5 game seconds:
//   1) writes a state file (xsCreateFile -> file named after the scenario/map, e.g. default0.xsdat)
//   2) opens claude_cmd.xsdat, reads an int and prints it to chat
//
// State file (all little-endian):
//   int    magic (20261029)
//   int    counter
//   int    game time in seconds
//   float  game time (to verify the float format)
//   string "bridge" (to verify the string format)
//
// Command file (written by tools/bridge_test.py):
//   int magic (20261029), int sequence number, int value

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
        xsChatData("[bridge] t=" + gameTime + " written=" + gCounter + " claude_cmd: OPEN FAILED");
        return;
    }
    int size = xsGetFileSize();
    if (size < 12) {
        xsCloseFile();
        xsChatData("[bridge] claude_cmd too short, bytes: %d", size);
        return;
    }
    int magic = xsReadInt();
    int seq = xsReadInt();
    int value = xsReadInt();
    xsCloseFile();

    if (magic != cBridgeMagic) {
        xsChatData("[bridge] wrong magic: %d", magic);
        return;
    }
    if (seq == gLastSeq) {
        xsChatData("[bridge] t=" + gameTime + " same seq=" + seq + " (no new command written since last read)");
        return;
    }
    gLastSeq = seq;
    xsChatData("Claude says: %d", value);
}

rule bridgeTick
    active
    minInterval 5
{
    int gameTime = xsGetGameTime();
    gCounter++;
    if (writeState(gameTime) == 0) {
        xsChatData("[bridge] xsCreateFile FAILED, t=%d", gameTime);
    }
    readCommand(gameTime);
}

void main() {
    xsChatData("[bridge] bridge_test.xs loaded");
}
