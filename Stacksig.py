import re
from enum import Enum, auto

# Functions defined in class Stacksig:
#     IsolateFunctionName   a utility used by StackFrameToString
#     StackFrameToString    converts a single frame to a single string for either
#                           printing or signature generation
#     StackToSignature      Converts a whole stack into a single string
#                           signature
#
# NOTE that the "bottom" and "top" terminology can be confusing because stacks
# are often listed bottom-to-top. So the stack "bottom" is array element [0]

class Stacksig(object):
    def __init__(self):

        # to make guarantees on performance and data size, set maximum lengths
        # and maximum stack frames
        self.MAX_SIGNATURE_LEN = 240
        self.MAX_FRAMES_TO_SCAN = 40

        self.OPERATOR_SUBST = "@OPERATOR_SUBST@"
        self.SIG_TOKEN_DELIMITER = " | "
        self.UNKNOWN_MODULE = "<unknown>"

        # Frame substrings that should be discarded from the start. These are
        # not useful to signature generation or could even cause inaccurate
        # signatures.
        self.ignoreFrameSubstrings = [
            "KiUserCallbackDispatcher",
            "patched_LdrLoadDll",
            # almost every stack has this at the top but it's not helpful and
            # if we don't ignore it, it will act as a (very unhelpful) target
            # frame
            "BaseThreadInitThunk",
        ]

        # We want to search for frames "above" a certain floor. These "floor"
        # frame substrings mark the place in the stack where we already have
        # the detail we're looking for so there's no use going deeper.
        # An example stack:
        #
        #     ntdll!LdrLoadDll           <-- bottom-most stack frame
        #     kernelbase!LoadLibraryExW
        #     kernel32!LoadLibraryA
        #     combase!CoCreateInstance   <-- "floor" frame
        #     comdlg32!OpenPrintDialog   <-- an interesting stack frame
        #     kernelbase!BaseThreadInitThunk
        #
        # The idea is to avoid returing a signature of "LdrLoadDll" all the
        # time, because that will almost always be at the bottom of the stack.
        # Floor frames help us look up the stack and try to get out of the
        # "we know this is loading a DLL" zone.
        self.floorFrameSubstrings = [
            "CoCreateInstance",
            "LoadAssembly",
            "LoadLibrary",
        ]

        # A "target" frame is one where we are specifically interested in seeing
        # in a signature. Similar to Socorro's prefix signature, except we don't
        # also grab the next stack frame.
        #
        # These are tuned to match on any browser function call. The effect is
        # that in any stack, we find the point at which Firefox code calls into
        # non-Firefox code.
        #
        # Bottom line: This allows us to see where in Firefox code DLLs were
        # loaded from.
        self.targetFrameSubstrings = [
            "AccessibleHandler!",
            "AccessibleMarshal!",
            "firefox!",
            "mozavcodec!",
            "mozavutil!",
            "mozglue!",
            "nss3!",
            "xul!",
        ]

    # This function attempts to take any C-ish function signature from
    # symbolication and return the function name only. These symbols have a lot
    # of odd cases so here we try and get the best bang-for-the-buck.
    #
    # Returns a tuple (functionName, debug)
    # Where
    #     functionName is the isolated function name. Always valid, non-empty.
    #     debug is an array of messages generated during the parsing process.
    def IsolateFunctionName(self, aFunction):
        debug = [] # return debug info to caller
        function = aFunction.strip()

        # Consider unnamed namespaces and lambdas enclosed in `'
        # eg RunnableFunction<`lambda at z:\/build\/build\/src\/dom\/html\/HTMLMediaElement.cpp:7150:11'>::Run()
        # eg HMODULE `anonymous namespace'::LoadLibrary()

        # Replace anything between these quotes (non-greedy) with "unnamed"
        # eg RunnableFunction<unnamed>::Run()
        # eg HMODULE unnamed::LoadLibrary()
        function = re.sub(r"\`.*?\'", "unnamed", function)

        # How we deal with C++ operators.
        #
        # Our parsing is not a full C++ parser; a lot of shortcuts are taken
        # and things stripped out. For example all pointers and references are
        # deleted from the string. And the argument list, which is determined
        # by looking at parenthesis. But we want to preserve something like:
        # eg operator *()
        # eg operator ()()
        #
        # So, we look for the next open parenthesis after "operator.*" while
        # taking into account operator()().
        #
        # For example
        #     bool xyz::operator ==(int)
        #                          ^ the last paren which ends the regex
        #                        ^^ named group: op
        #               ^^^^^^^^^^^ named group: all
        #
        # We replace the whole operator string (eg "operator >>") with a
        # placeholder which we will later restore the real operator text. This
        # makes operators look like a normal function for the moment.
        # eg       int xyz::operator +(int)
        # becomes  int xyz::@OP_SUBST@(int)
        # and later after args are removed and other things are stripped,
        #          xyz::@OP_SUBST@
        # then restored with opText as
        #          xyz::operator +
        opText = None
        parens = r"(\(\s*\))"
        # search for word "operator", then either () or whatever-else (non-greedy) until we hit an open paren or the end of the string.
        match = re.search(r"(?P<all>\boperator\b(?P<op>(" + parens + r"|.*?)))(\(|$)", function)
        if match:
            # Though it's tempting to return match.group('all') here, we still
            # need to preserve other qualifiers like namespaces
            opText = match.group('op').strip()
            if opText: # Check that the parsing was actually successful

                # Replace the whole operator text with a placeholder
                function = function[:match.start('all')] + self.OPERATOR_SUBST + function[match.end('all'):]
                debug.append("opText                  : \"{}\"".format(opText)) # eg "<<", "->*", "+=", "()", "const bool *"
                debug.append("Remove ops              : {}".format(function))

        # Remove symbols that confuse parsing. Pointers, references, et al
        # It's important to remove indexers as well [], because it can be a part
        # of a non-contiguous type. For example:
        #     int myFunction()[]
        # This function returns an array of ints. Removing the [] simplifies
        # parsing.
        #
        # Replacing by string will make sure tokens stay separated.
        function = re.sub(r"\*|&|&&|\[.*?\]", " ", function)
        debug.append("Remove array,ptr,ref    : {}".format(function))

        # Now prepare to walk through the string. Remove template arguments,
        # paying attention to nesting levels.
        # At the same time gather info about parenthesis so we can later remove
        # the argument list.
        fn2 = ""
        templateBracketLevel = 0
        parenLevel = 0

        # lastIndexWithNoParens keeps track of the last top-level position in
        # the string with regard to parenthesis. In other words, the last
        # position where the parenthesis nesting level is 0.
        #     eg void fn(int)
        #              ^-- last position that's not within parenthesis
        #
        # This is needed to know where the argument list is.
        lastIndexWithNoParens = 0

        # firstParenLevel2 ensures we can handle functions that return function
        # pointers.
        #     eg: void (*fn(char))(int)
        # Here, the argument list looks like (int), but this is actually the
        # argument list of the returned function pointer type.
        #
        # The argument list to the function `fn` is (char). Normal parsing will
        # remove (int) here, which is actually fine but we need to remove more.
        #
        # In order to know where the real arg list is then, we search for the
        # first place in the string where the parenthesis depth becomes 2.
        # eg: void (*fn(char))(int)
        #               ^-- paren level 2
        # This gives a very good indication of where the real arg list is.

        # It doesn't work when there are extraneous parenthesis, or when a
        # nested return type contains parenthesis. These are acceptable
        # compromises because it's very unlikely we'll see symbols with
        # redundant parenthesis, and the other is just too rare to care about.
        #
        # Example of redundant parenthesis:
        #     void (((*fn(char))))(int)
        #            ^-- paren level 2. The function name will be returned as garbage, probably "("
        #
        # Example of function type nested in return type:
        #     std::function<void(int(*)(int))> fn()
        firstParenLevel2 = 0

        templateLevels = [] # just for debugging
        parenLevels = [] # just for debugging
        for ch in function:
            if ch == "<":
                templateBracketLevel += 1
                templateLevels.append(str(templateBracketLevel))
                parenLevels.append(str(parenLevel))
                continue
            elif ch == ">":
                templateBracketLevel -= 1
                if not templateBracketLevel:
                    fn2 += "<T>" # replace ALL nested templates with <T>. Even <A<B<C>>> just becomes <T>
                templateLevels.append(str(templateBracketLevel))
                parenLevels.append(str(parenLevel))
                continue

            if ch == "(":
                if parenLevel < 1:
                    lastIndexWithNoParens = len(fn2)
                parenLevel += 1
                if parenLevel == 2 and not firstParenLevel2:
                    firstParenLevel2 = len(fn2)
            elif ch == ")":
                parenLevel -= 1

            if templateBracketLevel < 1:
                fn2 += ch
            templateLevels.append(str(templateBracketLevel))
            parenLevels.append(str(parenLevel))

        function = fn2
        debug.append("template levels         : {}".format("".join(templateLevels)))
        debug.append("paren    levels         : {}".format("".join(parenLevels)))
        debug.append("Remove templates        : {}".format(function))

        # This will chop off the last plausible looking argument list
        if lastIndexWithNoParens:
            debug.append("lastIndexWithNoParens: {}".format(lastIndexWithNoParens))
            debug.append("                       {}".format(function[:lastIndexWithNoParens]))
            debug.append("                       {}".format(function[lastIndexWithNoParens:]))
            function = function[:lastIndexWithNoParens]

        # And for functions that return function pointers, this will remove the
        # actual argument list based on the above logic.
        if firstParenLevel2:
            debug.append("firstParenLevel2         : {}".format(firstParenLevel2))
            debug.append("                       {}".format(function[:firstParenLevel2]))
            debug.append("                       {}".format(function[firstParenLevel2:]))
            function = function[:firstParenLevel2]

        # The function name is now the last token.
        tokens = function.strip().rsplit(' ', 1)
        function = tokens[-1]

        # If we previously substituted an operator, replace it.
        if opText:
            function = function.replace(self.OPERATOR_SUBST, "operator " + opText)
            debug.append("restore operator       {}".format(function))

        return function, debug

    # Converts stack frame info to a string. This is needed for signature
    # generation, as well as basic human-readable-formatting for display.
    #
    # Parameters are all optional; the result uses what it can.
    #
    # Different cases of concatenation, based on which information is provided:
    # 1 mod!fn+fnoffset
    # 2 mod!fn
    # 3 mod+modoffset
    # 4 mod
    # 5 fn+fnoffset
    # 6 fn
    # 7 @modoffset
    # 8 <???>
    #
    # Parameters:
    #     module                  String
    #     moduleOffset            String, module offset (eg "0x123bcd")
    #     function                String
    #     functionOffset          String, eg "0x123abc"
    #     forSignaturification    Specifies whether this transformation should
    #                             be tuned for generating a stack signature.
    #                             If False, then the output is for
    #                             pretty-printing.
    #
    # Return value: tuple (result, debug)
    #
    # result   The string the caller is requesting
    # debug    An array of debug messages with info about the transformation
    #          process.
    def StackFrameToString(self, module, moduleOffset, function, functionOffset, forSignaturification = False):
        debug = []
        if function:
            if forSignaturification:
                # In order to structure and normalize function names, which can have
                # very crazy and unpredictable formatting, just attempt to find the
                # function name alone.
                function, debug = self.IsolateFunctionName(function)
            else:
                # For pretty printing just attempt to fix up some of the oddness
                # that come from symbolication

                # Remove from the front of the string: words "static", "void", or spaces
                leadingQualifiers = r"^(\s|\bstatic\b|\bvoid\b)+"
                # Remove from the end of the string: const, &, spaces
                trailingQualifiers = r"(\s|\bconst\b|&)+$"
                function = re.sub("({})|({})".format(leadingQualifiers, trailingQualifiers), "", function)

                # transform "unsigned __int16" into "uint16".
                # "unsigned", space, any number of underscore, then lookahead for the type token.
                function = re.sub(r"(unsigned\s+_*)(?=char|long|short|int|int64|int32|int16|int8)", "u", function)

                # Remove spaces before any asterisk. This turns things like
                # "char * * const *" into "char** const*" which is just prettier.
                function = re.sub(r"\s+\*", "*", function)

                # Make sure there is 1 space after commas. Again normalizing and
                # just more readable.
                function = re.sub(r",\s*", ", ", function)

                # And collapse multiple spaces into 1 space
                function = re.sub(r"\s+", " ", function)

        # from here, just concatenate strings for the result based on what
        # was provided by the caller.
        if function and functionOffset:
            function += "+" + functionOffset

        if module:
            module = re.sub(r"\.pdb$", "", module) # remove trailing .pdb extension

        if module and function: # case 1 & 2
            return (module + "!" + function), debug
        if module and moduleOffset: # case 3
            return (module + "+" + moduleOffset), debug
        if module: # case 4
            return module, debug
        if function: # case 5 & 6
            return function, debug
        if moduleOffset: # case 7
            return ("@" + moduleOffset), debug
        return "<???>", debug

    # StackToSignature converts a stack (an array of stack frames) into a single
    # string signature.
    #
    # aStack       Array of stack frames, how they are returned from the
    #              symbolication server. Each stack frame is a dict {
    #                  "frame" - required, the stack frame index where 0
    #                            represents the bottom of the stack.
    #                  "module" - string, optional
    #                  "function" - string, optional
    #              }
    # aThreadName  Optional, string. The name of the thread. It gets prepended
    #                                to the signature.
    #
    # returns (signature, debug) where
    #
    # signature  The signature(!)
    # debug      An array of strings with info about the signaturification
    #            process.
    def StackToSignature(self, aStack, aThreadName):
        debug = []
        frames = []

        # Initialize our frame list just with indices
        for frame in aStack[:self.MAX_FRAMES_TO_SCAN]:
            frames.append(
                {
                    "idx" : frame["frame"],
                    "source" : frame,
                })

        # sort
        frames = sorted(frames, key=lambda s: s["idx"])

        # Iterate over the list. We do a few things at once:
        # - get a signature for each frame
        # - ignore dupes
        # - ignore explicitly ignored frames
        # - look for floor frames
        # - look for target frames
        lastFloorFrameIndex = -1
        targetFrameIndex = -1
        lastTargetFrameIndex = -1
        filteredFrames = []
        for frame in frames:
            # generate the signature
            frameSource = frame["source"]
            frame["signature"], _ = self.StackFrameToString(
                frameSource["module"] if "module" in frameSource else "",
                None,
                frameSource["function"] if "function" in frameSource else "",
                None,
                True)

            # ignore list
            if any(str in frame["signature"] for str in self.ignoreFrameSubstrings):
                debug.append("ignoring {}".format(frame["signature"]))
                continue

            # skip duplicates
            if filteredFrames and frame["signature"] == filteredFrames[-1]["signature"]:
                debug.append("duplicate {}".format(frame["signature"]))
                continue

            # save this frame; it's not ignored or skipped
            filteredFrames.append(frame)

            # Is this a floor frame?
            if any(str in frame["signature"] for str in self.floorFrameSubstrings):
                debug.append("floor frame {}".format(frame["signature"]))
                # keep track of the top-most floor frame index.
                lastFloorFrameIndex = len(filteredFrames) - 1

            # Is it a target frame?
            elif any(str in frame["signature"] for str in self.targetFrameSubstrings):
                debug.append("target frame {}".format(frame["signature"]))
                lastTargetFrameIndex = len(filteredFrames) - 1 # it is; save the index.
                if targetFrameIndex == -1:
                    targetFrameIndex = lastTargetFrameIndex

                # If we found a target frame before we found a floor frame, keep
                # looking. We want to try and find frames "above" floor frames.
                # But if we've found a floor frame already, then we don't need
                # to look further in the stack.

                if lastFloorFrameIndex != -1:
                    # we have seen floor frames before. we know this is the signature we'll use.
                    targetFrameIndex = lastTargetFrameIndex
                    break

        frames = filteredFrames

        sigTokens = [] # tokens that will be joined to create the final signature

        # If we found a target frame, use it.
        if targetFrameIndex != -1:
            sigTokens = [frames[targetFrameIndex]["signature"]]
        elif frames:
            # If we didn't find a target frame, try to use the frame after the
            # floor frame. The floor frame itself is not that useful; use the
            # frame above it.
            i = lastFloorFrameIndex + 1
            if i >= len(frames): # clamp to bounds
                i = len(frames) - 1
            elif i < (len(frames) - 1) and frames[i]["signature"] == self.UNKNOWN_MODULE:
                # if there's another element available, and the one we're
                # pointing at is "<unknown>", then skip it because that's not
                # very useful.
                i += 1
            sigTokens.append(frames[i]["signature"])

        # prepend the thread name
        if aThreadName:
            sigTokens = ["<#{}>".format(aThreadName.upper())] + sigTokens #   <#WINSOCK THREAD> | 

        if not sigTokens:
            return "<no useful stack frames>", debug # we filtered everything out

        # Join and limit length to self.maxSignatureLength.
        joined = self.SIG_TOKEN_DELIMITER.join(sigTokens)

        debug.append("> frame dump:")
        debug.append("> -----------------------------------------")
        for frame in frames:
            debug.append("> id:{:3d} {}".format(
                frame["idx"],
                frame["signature"]))

        return joined[:self.MAX_SIGNATURE_LEN], debug
