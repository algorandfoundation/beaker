def parseVAA(vaa: bytes):
    ret = {"version": int.from_bytes(vaa[0:1], "big"), "index": int.from_bytes(vaa[1:5], "big"), "siglen": int.from_bytes(vaa[5:6], "big")}
    ret["signatures"] = vaa[6:(ret["siglen"] * 66) + 6]
    ret["sigs"] = []
    for i in range(ret["siglen"]):
        ret["sigs"].append(vaa[(6 + (i * 66)):(6 + (i * 66)) + 66].hex())
    off = (ret["siglen"] * 66) + 6
    ret["digest"] = vaa[off:]  # This is what is actually signed...
    ret["timestamp"] = int.from_bytes(vaa[off:(off + 4)], "big")
    off += 4
    ret["nonce"] = int.from_bytes(vaa[off:(off + 4)], "big")
    off += 4
    ret["chainRaw"] = vaa[off:(off + 2)]
    ret["chain"] = int.from_bytes(vaa[off:(off + 2)], "big")
    off += 2
    ret["emitter"] = vaa[off:(off + 32)]
    off += 32
    ret["sequence"] = int.from_bytes(vaa[off:(off + 8)], "big")
    off += 8
    ret["consistency"] = int.from_bytes(vaa[off:(off + 1)], "big")
    off += 1

    ret["Meta"] = "Unknown"

    if vaa[off:(off + 32)].hex() == "000000000000000000000000000000000000000000546f6b656e427269646765":
        ret["Meta"] = "TokenBridge"
        ret["module"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["action"] = int.from_bytes(vaa[off:(off + 1)], "big")
        off += 1
        if ret["action"] == 1:
            ret["Meta"] = "TokenBridge RegisterChain"
            ret["targetChain"] = int.from_bytes(vaa[off:(off + 2)], "big")
            off += 2
            ret["EmitterChainID"] = int.from_bytes(vaa[off:(off + 2)], "big")
            off += 2
            ret["targetEmitter"] = vaa[off:(off + 32)].hex()
            off += 32
        if ret["action"] == 2:
            ret["Meta"] = "TokenBridge UpgradeContract"
            ret["targetChain"] = int.from_bytes(vaa[off:(off + 2)], "big")
            off += 2
            ret["newContract"] = vaa[off:(off + 32)].hex()
            off += 32

    if vaa[off:(off + 32)].hex() == "00000000000000000000000000000000000000000000000000000000436f7265":
        ret["Meta"] = "CoreGovernance"
        ret["module"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["action"] = int.from_bytes(vaa[off:(off + 1)], "big")
        off += 1
        ret["targetChain"] = int.from_bytes(vaa[off:(off + 2)], "big")
        off += 2
        if ret["action"] == 2:
            ret["NewGuardianSetIndex"] = int.from_bytes(vaa[off:(off + 4)], "big")
        else:
            ret["Contract"] = vaa[off:(off + 32)].hex()

    if ((len(vaa[off:])) == 100) and int.from_bytes((vaa[off:off+1]), "big") == 2:
        ret["Meta"] = "TokenBridge Attest"
        ret["Type"] = int.from_bytes((vaa[off:off+1]), "big")
        off += 1
        ret["Contract"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["FromChain"] = int.from_bytes(vaa[off:(off + 2)], "big")
        off += 2
        ret["Decimals"] = int.from_bytes((vaa[off:off+1]), "big")
        off += 1
        ret["Symbol"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["Name"] = vaa[off:(off + 32)].hex()

    if ((len(vaa[off:])) == 133) and int.from_bytes((vaa[off:off+1]), "big") == 1:
        ret["Meta"] = "TokenBridge Transfer"
        ret["Type"] = int.from_bytes((vaa[off:off+1]), "big")
        off += 1
        ret["Amount"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["Contract"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["FromChain"] = int.from_bytes(vaa[off:(off + 2)], "big")
        off += 2
        ret["ToAddress"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["ToChain"] = int.from_bytes(vaa[off:(off + 2)], "big")
        off += 2
        ret["Fee"] = vaa[off:(off + 32)].hex()

    if int.from_bytes((vaa[off:off+1]), "big") == 3:
        ret["Meta"] = "TokenBridge Transfer With Payload"
        ret["Type"] = int.from_bytes((vaa[off:off+1]), "big")
        off += 1
        ret["Amount"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["Contract"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["FromChain"] = int.from_bytes(vaa[off:(off + 2)], "big")
        off += 2
        ret["ToAddress"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["ToChain"] = int.from_bytes(vaa[off:(off + 2)], "big")
        off += 2
        ret["Fee"] = bytes(32) 
        ret["FromAddress"] = vaa[off:(off + 32)].hex()
        off += 32
        ret["Payload"] = vaa[off:].hex()
    
    return ret