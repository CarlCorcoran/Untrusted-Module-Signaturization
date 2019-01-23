#!python3.6

from importlib import reload
import json
import os
import re
import Stacksig
import StacksigTests
import sys
import time

MAX_LIST_LEN = 40


totalStart = time.time()
pings = 0
results = 0
global currentStackId
global currentSigId
currentStackId = None
currentSigId = None

def GetLeafName(path):
    return os.path.split(path)[1].lower()

def GetData(aSkipStacks, aLimitStacks):
    global pings
    global results
    ret = []
    numStacksTouched = 0
    with open("big.json", 'r', errors = 'replace') as f:
        for line in f:
            line = line.replace(":true", ":True").replace(":false", ":False")
            data = eval(line)
            pings += 1
            if data["environment"]["system"]["is_wow64"]:
                continue
            if not ("symbolicated_stacks" in data) or not ("client_id" in data):
                continue
            stacks = data["symbolicated_stacks"]
            realstacks = eval(stacks)
            if "results" not in realstacks:
                continue
            results += len(realstacks["results"])
            for idx, result in enumerate(realstacks["results"]):
                event = data["payload"]["events"][idx]
                if not event:
                    print("No corresponding event!")
                    continue
                filtered = list(map(lambda stack: {
                    "frames": stack,
                    "clientID": data["client_id"],
                    "threadName": event["thread_name"],
                    "modules": list(map(lambda m: GetLeafName(m["module_name"]), event["modules"]))
                    }, filter(lambda stack: stack, result["stacks"])));
                numStacksTouched += len(filtered)
                if numStacksTouched > aSkipStacks:
                    ret.extend(filtered)
                    if len(ret) >= aLimitStacks:
                        return ret

def doGenData(aSkipStacks, aLimitStacks):
    start = time.time()

    if not os.path.isfile('big.json'):
        print("\n!!")
        print("You need a JSON data source called 'big.json' to generate data from,")
        print("where each line is raw JSON ping.")
        exit(0)

    stacks = GetData(aSkipStacks, aLimitStacks)
    end = time.time()
    print("Slow load ({}): {}".format(len(stacks), end - start))
    with open("outp.py", "w") as text_file:
        text_file.write("{}".format(stacks))

    print("{} pings found".format(pings))
    print("{} results found".format(results))
    print("{} stacks found".format(len(stacks)))

def dumpSigList():
    global uniqueSignatures
    with open("sigs.txt", "w") as text_file:
        text_file.write("\n".join(sorted(list(map(lambda s: s["signature"], uniqueSignatures)))))

def InitData():
    global stacks
    global uniqueSignatures

    utils = Stacksig.Stacksig()

    if not os.path.isfile('outp.py'):
        doGenData(0, 10)

    start = time.time()
    with open("outp.py", 'r') as f:
        stacks = eval(f.read());
    end = time.time()
    print("Fast load ({}): {}".format(len(stacks), end - start))
    print("Processing {} stacks in original data".format(len(stacks)))

    # Add signature to each stack
    for stack in stacks:
        if not stack:
            continue
        signature, debug = utils.StackToSignature(
            stack["frames"],
            stack["threadName"] if "threadName" in stack else None)

        stack["signature"] = signature
        stack["signatureDebug"] = debug

    # remove duplicate signatures per client_id, to not skew the data.
    # E.g. if a single user is sending us 10,000 of the same event. we want to get
    # unique events per user
    t = {}
    for stack in stacks:
        t["{}|{}".format(stack["clientID"], stack["signature"])] = stack;

    print("Removed {} duplicate-ish stacks".format(len(stacks) - len(t)))
    stacks = t.values()

    # get all unique signatures
    uniqueSignatures = list(map(lambda sig: {
        "signature": sig,
        "count": 0,
        "modules": set()
        }, set(map(lambda stack: stack["signature"], stacks))))

    # add occurrences and modules to the signatures
    for sig in uniqueSignatures:
            for stack in stacks:
                    if stack["signature"] == sig["signature"]:
                         sig["count"] += 1
                         sig["modules"] |= set(stack["modules"])

    # sort desc by occurrence
    uniqueSignatures.sort(key=lambda sig: sig["count"], reverse=True)

    # add a unique ID
    for c, sig in enumerate(uniqueSignatures):
            sig["id"] = c

def doSig(aSigFilter):
    global stacks
    global uniqueSignatures
    usigsFiltered = list(
        uniqueSignatures if not aSigFilter
            else filter(lambda s: aSigFilter.lower() in s["signature"].lower(), uniqueSignatures))
    #print("Found {} non-null stacks".format(len(stacks)))
    print("Found {} unique signatures".format(len(usigsFiltered)))
    for sig in filter(lambda s: True, usigsFiltered[:MAX_LIST_LEN]):
            print("  {:3d} stacks, {:3d} mods for sigID {:3d} : {}".format(
                sig["count"],
                len(sig["modules"]),
                sig["id"],
                sig["signature"]))

def doSigDetails(sigId):
    global stacks
    global uniqueSignatures
    matchSignature = next((sig for sig in uniqueSignatures if sig["id"] == sigId), None)
    if not matchSignature:
        print("No matching signature for ID {}".format(sigId))
        return
    print ("{} modules represented by signature: {}".format(
        len(matchSignature["modules"]),
        matchSignature["signature"]))
    for mod in sorted(matchSignature["modules"]):
        print("    " + mod)

def doModuleSignatures(mod):
    global stacks
    global uniqueSignatures
    for sig in uniqueSignatures:
        if any(mod in str for str in sig["modules"]):
            print ("ID {}, sig {}".format(sig["id"], sig["signature"]))

def doListModules():
    global stacks
    global uniqueSignatures
    uniqueModules = set()
    for sig in uniqueSignatures:
        uniqueModules |= sig["modules"]
    uniqueModules2 = []
    for mod in uniqueModules:
        count = 0
        # how many unique signatures contain this module
        for sig in uniqueSignatures:
            count += 1 if mod in sig["modules"] else 0
        uniqueModules2.append({
            "count": count,
            "module": mod
            })
    uniqueModules2.sort(key=lambda x: x["count"], reverse=True)
    print("N: M, where N stack signatures loaded module M")
    for mod in uniqueModules2[:MAX_LIST_LEN]:
        print("{:3d}: {}".format(mod["count"], mod["module"]))

def FrameToString(aFrame):
    utils = Stacksig.Stacksig()
    x = utils.StackFrameToString(
        aFrame["module"] if "module" in aFrame else "",
        aFrame["module_offset"] if "module_offset" in aFrame else "",
        aFrame["function"] if "function" in aFrame else "",
        aFrame["function_offset"] if "function_offset" in aFrame else "")
    return x

def doSearchStackFrames(aQuery):
    global stacks
    global uniqueSignatures

    for uniqueSig in uniqueSignatures:
        matchingStacks = list(filter(lambda s: s["signature"] == uniqueSig["signature"], stacks))
        for i, ms in enumerate(matchingStacks):
            ms["stackID"] = i

    class StackHashAdapter:
        def __init__(self, aStack):
            self.mStack = aStack
        def __str__(self):
            return str(self.mStack["signature"])
        def __hash__(self):
            return hash(self.mStack["signature"])
        def __eq__(self,other):
            return self.mStack["signature"] == other.mStack["signature"]

    matchingStacks = set() # of StackHashAdapter
    for stack in stacks:
        for frame in stack["frames"]:
            if (aQuery.lower() in FrameToString(frame)[0].lower()):
                matchingStacks.add(StackHashAdapter(stack))
                break

    matchingStacks = list(matchingStacks)
    #matchingStacks.sort(key=lambda x: x.mStack["count"], reverse=True)
    print("Found {} unique signatures".format(len(matchingStacks)))
    for stack2 in matchingStacks[:MAX_LIST_LEN]:
        stack = stack2.mStack
        usig = next(filter(lambda us: us["signature"] == stack["signature"], uniqueSignatures))
        print("  sigID {:3d} stackID {:3d} : {}".format(
            usig["id"],
            stack["stackID"],
            usig["signature"]))
                         #    if stack["signature"] == sig["signature"]:
                         # sig["count"] += 1
                         # sig["modules"] |= set(stack["modules"])
    # sigID {} stack {}

def doStackPrint(sigId):
    global stacks
    global uniqueSignatures
    global currentStackId
    global currentSigId

    if currentSigId is None:
        currentSigId = sigId
    else:
        if currentSigId == sigId:
            currentStackId += 1

    currentSigId = sigId

    matchSignature = next(sig for sig in uniqueSignatures if sig["id"] == sigId)
    print ("{} stacks represented by signature: {}".format(
        matchSignature["count"],
        matchSignature["signature"]))
    matchingStacks = list(filter(lambda s: s["signature"] == matchSignature["signature"], stacks))
    if not matchingStacks:
        print("!! No stacks found")
        return
    if currentStackId is None:
        currentStackId = 0
    if currentStackId < 0 or currentStackId >= len(matchingStacks):
        print("!! out of range of 0-{}; setting to 0".format(len(matchingStacks)))
        currentStackId = 0
    stack = matchingStacks[currentStackId]

    print ("\nDebug:")
    for msg in stack["signatureDebug"]:
        print("    " + msg)

    print ("\n{} modules.".format(len(stack["modules"])))
    for mod in stack["modules"]:
        print("    " + mod)

    print ("\nStack index {}".format(currentStackId))
    for frame in stack["frames"]:
        x = FrameToString(frame)
        print("    " + x[0])
        # for l in x[1]:
        #     print("    (debug): " + l)



InitData()

end = time.time()
print("init took {} seconds".format(end - totalStart))

def doHelp():
    print("Untrusted Modules Signature Generator")
    print("Commands:")
    print("  ?              Show help")
    print("  q              Quit")
    print("  d              Dump signature list to sigs.txt")
    print("  r              Recompile the sig gen modules, re-process data")
    print("  len <N>        Set MAX_LIST_LEN")
    print("  gen <N>        Grab N stacks from 'big.json', output in outp.py,")
    print("  gen <S> <N>    Grab N stacks from 'big.json' after skipping S")
    print("                 stacks, output in outp.py,")
    print("                 and re-process data.")
    print("  t              Recompile tests and run them")
    print("")
    print("  \\ <Q>          Show a list of stack signatures, optionally matching")
    print("                 substring Q")
    print("  sig <ID>       Show info about the signature <ID>")
    print("  s <ID> <SID>   Show detailed stack report for signature <ID>,")
    print("                 and 0-based stack ID <SID>.")
    print("  fn <Q>         Test pretty-printing / sig for function name Q")
    print("")
    print("  ms <Q>         Show stacks signatures that loaded module Q")
    print("  lm             List all modules seen, sorted by prevalence")
    print("")
    print("  sf <Q>         Search for signatures whose stack frames match Q")
    print("")
    print("  sm             Sort signature list by # of unique modules loaded")
    print("  so             Sort signature list by # of occurrences")
    print("  sa             Sort signature list alphabetically")
    print("  sl <->         Sort signature list by length of signature")

lastCommand = "?"

while True:
    cmd = input("> ").strip()
    if not cmd:
        cmd = lastCommand

    args = cmd.split(" ");
    lastCommand = cmd

    if args[0] == "?":
        doHelp()
    elif args[0] == "q":
        break
    elif args[0] == "sig":
        doSigDetails(int(args[1]))
    elif args[0] == "len":
        MAX_LIST_LEN = int(args[1])
    elif args[0] == "ms":
        doModuleSignatures(args[1])
    elif args[0] == "d":
        dumpSigList()
    elif args[0] == "sm":
        uniqueSignatures.sort(key=lambda sig: -len(sig["modules"]))
        print("Sorting by modules")
    elif args[0] == "so":
        uniqueSignatures.sort(key=lambda sig: sig["count"], reverse=True)
        print("Sorting by occurrence")
    elif args[0] == "sa":
        uniqueSignatures.sort(key=lambda sig: sig["signature"])
        print("Sorting alphabetically")
    elif args[0] == "sl":
        uniqueSignatures.sort(key=lambda sig: len(sig["signature"]))
        print("Sorting by signature length")
    elif args[0] == "sl-":
        uniqueSignatures.sort(key=lambda sig: len(sig["signature"]), reverse=True)
        print("Sorting by signature length (DESC)")
    elif args[0] == "lm":
        doListModules()
    elif args[0] == "sf":
        doSearchStackFrames(args[1])
    elif args[0] == "fn":
        q = cmd[len(args[0]):].strip()
        print("Function : {}".format(q))
        utils = Stacksig.Stacksig()
        x = utils.StackFrameToString(None, None, q, None, True)
        print("\nFor sig  : {}".format(x[0]))
        for l in x[1]:
            print("  (debug): " + l)
        x = utils.StackFrameToString(None, None, q, None, False)
        print("\nFor print: {}".format(x[0]))
        for l in x[1]:
            print("  (debug): " + l)
        print("")
    elif args[0] == "gen":
        if len(args) == 2:
            doGenData(0, int(args[1]))
        if len(args) == 3:
            doGenData(int(args[1]), int(args[2]))
        InitData()
    elif args[0] == "\\":
        if len(args) == 2:
            doSig(args[1])
        else:
            doSig(None)
    elif args[0] == "s": # s 79 0
        sigId = int(args[1].strip())
        if len(args) == 3:
            currentSigId = None
            currentStackId = int(args[2].strip())
        doStackPrint(sigId)
    elif args[0] == "r":
        print("recompiling...")
        print(reload(Stacksig))
        InitData()
    elif args[0] == "t":
        print("recompiling tests...")
        print(reload(Stacksig))
        print(reload(StacksigTests))
        StacksigTests.Runtests()
    else:
        print("Unknown command. ? for help")

exit(0)

