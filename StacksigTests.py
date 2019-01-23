from importlib import reload
import Stacksig
import re
import TestData_FrameToString
import TestData_Signatures

def Runtests():
    utils = Stacksig.Stacksig()
    testsRun = 0
    testsPassed = 0

    print(reload(TestData_FrameToString))
    print(reload(TestData_Signatures))

    print("\n================================================================================")
    print("STACK SIGNATURE TESTS\n")

    for o in TestData_Signatures.tests:
        # make sure frame index is populated
        for i, x in enumerate(o["stackFrames"]):
            x["frame"] = i
        actual, debug = utils.StackToSignature(o["stackFrames"], None if "threadName" not in o else o["threadName"])
        print(o["desc"])
        part1 = actual == o["expectedSignature"]
        if part1:
            print("   PASS - expected: {}".format(o["expectedSignature"][:60]))
            testsPassed += 1
            if "debug" in o:
                print(    "            debug:")
                for s in debug:
                    print("                 : {}".format(s))
        else:
            print(    " ! FAIL - expected: {}".format(o["expectedSignature"]))
            print(    "            actual: {}".format(actual))
            print(    "            debug:")
            for s in debug:
                print("                 : {}".format(s))
        testsRun += 1

    print("\n================================================================================")
    print("FRAME TO STRING TESTS\n")

    for o in TestData_FrameToString.tests:
        actual = utils.StackFrameToString(
            o["module"] if "module" in o else "",
            o["module_offset"] if "module_offset" in o else "",
            o["function"] if "function" in o else "",
            o["function_offset"] if "function_offset" in o else "",
            o["forSignaturification"] if "forSignaturification" in o else False
        )

        print(o["desc"])
        if actual[0] == o["expected"]:
            print("   PASS - expected: {}".format(o["expected"]))
            testsPassed += 1
            if "debug" in o:
                print(    "            debug:")
                for s in actual[1]:
                    print("                 : {}".format(s))
        else:
            print(" ! FAIL - expected: {}".format(o["expected"]))
            print("            actual: {}".format(actual[0]))
            print(    "            debug:")
            for s in actual[1]:
                print("                 : {}".format(s))
        testsRun += 1

    print("")
    print("TOTAL: {} of {} tests passed ({}%)".format(testsPassed, testsRun, 100.0 * testsPassed / testsRun))
    print("  -> PASS" if testsRun == testsPassed else "  -> FAIL")

