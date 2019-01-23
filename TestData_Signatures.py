# SIGNATURE TESTS

tests = [
    {
        "desc": "test no stack frames",
        "expectedSignature": "<no useful stack frames>",
        "stackFrames": [
        ],
    },

    # THREAD NAME STUFF
    {
        "desc": "thread name",
        "expectedSignature": "<#A THREAD NAME>",
        "threadName": "a thread name",
        "stackFrames": [
        ],
    },
    {
        "desc": "thread name",
        "expectedSignature": "<#A THREAD NAME> | mod",
        "threadName": "a thread name",
        "stackFrames": [
          { "module": "mod" }
        ],
    },
    {
        "desc": "thread name 2",
        "expectedSignature": "<#THREAD> | mod",
        "threadName": "thread",
        "stackFrames": [
          { "module": "mod" },
          { "module": "mod2" }
        ],
    },
    {
        "desc": "thread name with unknown",
        "expectedSignature": "<#THREAD> | <unknown>",
        "threadName": "thread",
        "stackFrames": [
          { "module": "<unknown>" },
        ],
    },

    # no matches; take frame[0]
    {
        "desc": "no matches; take frame [0]",
        "expectedSignature": "shell32!WeirdFunction1",
        "stackFrames": [
          { "module": "shell32", "function": "WeirdFunction1" },
          { "module": "shell32", "function": "WeirdFunction2" },
        ],
    },
    {
        "desc": "first non-unknown frame",
        "expectedSignature": "shell32!WeirdFunction1",
        "stackFrames": [
          { "module": "<unknown>" },
          { "module": "shell32", "function": "WeirdFunction1" },
          { "module": "shell32", "function": "WeirdFunction2" },
        ],
    },
    {
        "desc": "only unknown",
        "expectedSignature": "<unknown>",
        "stackFrames": [
          { "module": "<unknown>" },
          { "module": "<unknown>" },
          { "module": "<unknown>" },
        ],
    },


    # floor
    {
        "desc": "test stack floor exclusive",
        "expectedSignature": "shell32!fnxyz",
        "stackFrames": [
          { "module": "shell32", "function": "LoadLibrary" },
          { "module": "shell32", "function": "CoCreateInstance" },
          { "module": "shell32", "function": "fnxyz" },
          { "module": "shell32", "function": "fnabc" },
        ],
    },
    {
        "desc": "test stack floor fallback to inclusive",
        "expectedSignature": "shell32!blah::CoCreateInstance",
        "stackFrames": [
          { "module": "shell32", "function": "blah::LoadLibrary" },
          { "module": "shell32", "function": "blah::CoCreateInstance" },
        ],
    },
    {
        "desc": "test stack floor doesn't render empty stack",
        #"debug": True,
        "expectedSignature": "shell32!CoCreateInstance",
        "stackFrames": [
          { "module": "shell32", "function": "CoCreateInstance" },
        ],
    },

    # floor + <unknown>.
    # in this case, also grab 1 more frame.
    {
        "desc": "test stack floor skips <unknown>",
        "expectedSignature": "shell32!WeirdFunction",
        "stackFrames": [
          { "module": "shell32", "function": "blah::LoadLibrary" },
          { "module": "shell32", "function": "blah::CoCreateInstance" },
          { "module": "<unknown>" },
          { "module": "shell32", "function": "WeirdFunction" },
        ],
    },

    # target
    {
        "desc": "target frames",
        "expectedSignature": "xul!someFn",
        "stackFrames": [
          { "module": "shell32", "function": "Blah" },
          { "module": "xul", "function": "someFn" },
        ],
    },
    {
        "desc": "target frames bounds",
        "expectedSignature": "xul!someFn",
        "stackFrames": [
          { "module": "shell32", "function": "Blah" },
          { "module": "xul", "function": "someFn" },
          { "module": "xul", "function": "someFnShallower" },
        ],
    },
    {
        "desc": "target frames bounds",
        "expectedSignature": "xul!someFn",
        "stackFrames": [
          { "module": "shell32", "function": "BlahDeeper" },
          { "module": "shell32", "function": "Blah" },
          { "module": "xul", "function": "someFn" },
        ],
    },
    {
        "desc": "target frames bounds",
        "expectedSignature": "xul!someFn",
        "stackFrames": [
          { "module": "shell32", "function": "BlahDeeper" },
          { "module": "shell32", "function": "Blah" },
          { "module": "xul", "function": "someFn" },
          { "module": "xul", "function": "someFnShallower" },
        ],
    },

    # target + <unknown>
    {
        "desc": "adj target frames contain <unknown>",
        "expectedSignature": "xul!someFn",
        "stackFrames": [
          { "module": "shell32", "function": "BlahDeeper" },
          { "module": "<unknown>" },
          { "module": "xul", "function": "someFn" },
          { "module": "xul", "function": "someFnShallower" },
        ],
    },

    # target + floor
    {
        "desc": "target frames and floor",
        "expectedSignature": "xul!someFn",
        "stackFrames": [
          { "module": "shell32", "function": "LoadLibrary" },
          { "module": "shell32", "function": "GetFileInfoOrSomething" },
          { "module": "xul", "function": "someFn" },
        ],
    },
    {
        "desc": "target frames IN floor 1",
        "expectedSignature": "xul!abc",
        "stackFrames": [
          { "module": "shell32", "function": "xyz" },
          { "module": "xul", "function": "LoadLibrary" },
          { "module": "xul", "function": "abc" },
        ],
    },
    {
        "desc": "target frames IN floor 0",
        "expectedSignature": "xul!someFn1",
        "stackFrames": [
          { "module": "xul", "function": "abc" },
          { "module": "xul", "function": "xyz" },
          { "module": "xul", "function": "LoadLibrary" },
          { "module": "xul", "function": "someFn1" },
        ],
    },

    # skip dupes + ignore
    {
        "desc": "ignore frames",
        "expectedSignature": "xul!someFn1",
        "stackFrames": [
          { "module": "xul", "function": "someFn2" },
          { "module": "xul", "function": "LoadLibrary" },
          { "module": "xul", "function": "LoadLibrary" },
          { "module": "xul", "function": "patched_LdrLoadDll" },
          { "module": "xul", "function": "patched_LdrLoadDll" },
          { "module": "xul", "function": "someFn1" },
        ],
    },

    # skip dupes + ignore + thread
    {
        "desc": "all ignored frames with thread name",
        "expectedSignature": "<#THREAD>",
        "threadName": "thread",
        "stackFrames": [
          { "module": "xul", "function": "patched_LdrLoadDll" },
          { "module": "xul", "function": "KiUserCallbackDispatcher" },
          { "module": "xul", "function": "patched_LdrLoadDll" },
          { "module": "xul", "function": "KiUserCallbackDispatcher" },
          { "module": "xul", "function": "patched_LdrLoadDll" },
        ],
    },
    {
        "desc": "all ignored frames with NO thread name",
        "expectedSignature": "<no useful stack frames>",
        "stackFrames": [
          { "module": "xul", "function": "patched_LdrLoadDll" },
          { "module": "xul", "function": "KiUserCallbackDispatcher" },
          { "module": "xul", "function": "patched_LdrLoadDll" },
          { "module": "xul", "function": "KiUserCallbackDispatcher" },
          { "module": "xul", "function": "patched_LdrLoadDll" },
        ],
    },

    # length-limiting
    {
        "desc": "length-limit 270 chars",
        "expectedSignature": "x_________10________20________30________40________50________60________70________80________90________100_______110_______120_______130_______140_______150_______160_______170_______180_______190_______200_______210_______220_______230_______",
        "stackFrames": [
          { "function":      "x_________10________20________30________40________50________60________70________80________90________100_______110_______120_______130_______140_______150_______160_______170_______180_______190_______200_______210_______220_______230_______240_______250_______260_______" },
        ],
    },
    {
        "desc": "length-limit 250 chars",
        "expectedSignature": "x_________10________20________30________40________50________60________70________80________90________100_______110_______120_______130_______140_______150_______160_______170_______180_______190_______200_______210_______220_______230_______",
        "stackFrames": [
          { "function":      "x_________10________20________30________40________50________60________70________80________90________100_______110_______120_______130_______140_______150_______160_______170_______180_______190_______200_______210_______220_______230_______" },
        ],
    },
    {
        "desc": "length-limit 239 chars",
        #"debug":1,
        "expectedSignature": "x_________10________20________30________40________50________60________70________80________90________100_______110_______120_______130_______140_______150_______160_______170_______180_______190_______200_______210_______220_______230______",
        "stackFrames": [
          { "function":      "x_________10________20________30________40________50________60________70________80________90________100_______110_______120_______130_______140_______150_______160_______170_______180_______190_______200_______210_______220_______230______" },
        ],
    },
]
