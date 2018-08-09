"""
Copyright 2003-2010 Cort Stratton. All rights reserved.
Copyright 2015, 2016 Hanson Robotics

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:
 1. Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
 2. Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the
    distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE FREEBSD PROJECT OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

"""This module implements the WordSub class, modelled after a recipe
in "Python Cookbook" (Recipe 3.14, "Replacing Multiple Patterns in a
Single Pass" by Xavier Defrang).

Usage:
Use this class like a dictionary to add before/after pairs:
    > subber = TextSub()
    > subber["before"] = "after"
    > subber["begin"] = "end"
Use the sub() method to perform the substitution:
    > print subber.sub("before we begin")
    after we end
All matching is intelligently case-insensitive:
    > print subber.sub("Before we BEGIN")
    After we END
The 'before' words must be complete words -- no prefixes.
The following example illustrates this point:
    > subber["he"] = "she"
    > print subber.sub("he says he'd like to help her")
    she says she'd like to help her
Note that "he" and "he'd" were replaced, but "help" and "her" were
not.
"""

import re
import string

DEFAULT_ENGLISH_NORMAL = {
    "I'd": "I would",
    "I'll": "I will",
    "I'm": "I am",
    "I'm'a": "I am about to",
    "I'm'o": "I am going to",
    "I've": "I have",
    "ain't": "is not",
    "aren't": "are not",
    "can't": "can not",
    "cannot": "can not",
    "could've": "could have",
    "couldn't": "could not",
    "daresn't": "dare not",
    "dasn't": "dare not",
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "everyone's": "everyone is",
    "gimme": "give me",
    "gonna": "going to",
    "gotta": "got to",
    "hadn't": "had not",
    "hasn't": "has not",
    "haven't": "have not",
    "he'd": "he would",
    "he'll": "he will",
    "he's": "he is",
    "he've": "he have",
    "how'd": "how would",
    "how'll": "how will",
    "how're": "how are",
    "how's": "how is",
    "i'd": "I would",
    "i'll": "I will",
    "i'm": "I am",
    "i've": "I have",
    "isn't": "is not",
    "it'd": "it would",
    "it'll": "it will",
    "it's": "it is",
    "let's": "let us",
    "ma'am": "madam",
    "may've": "may have",
    "mayn't": "may not",
    "might've": "might have",
    "mightn't": "might not",
    "must've": "must have",
    "mustn't": "must not",
    "mustn't've": "must not have",
    "needn't": "need not",
    "oughtn't": "ought not",
    "shan't": "shall not",
    "she'd": "she would",
    "she'll": "she will",
    "she's": "she is",
    "should've": "should have",
    "shouldn't": "should not",
    "that'd": "that would",
    "that'll": "that will",
    "that're": "that are",
    "that's": "that is",
    "there'd": "there would",
    "there'll": "there will",
    "there're": "there are",
    "there's": "there is",
    "these're": "these are",
    "they'd": "they would",
    "they'll": "they will",
    "they're": "they are",
    "they've": "they have",
    "this's": "this is",
    "those're": "those are",
    "wanna": "want to",
    "wasn't": "was not",
    "we'd": "we would",
    "we'll": "we will",
    "we're": "we are",
    "we've": "we have",
    "weren't": "were not",
    "what'd": "what did",
    "what'll": "what will",
    "what're": "what are",
    "what's": "what is",
    "what've": "what have",
    "when'd": "when did",
    "when'll": "when will",
    "when's": "when is",
    "where'd": "where did",
    "where'll": "where will",
    "where're": "where are",
    "where's": "where is",
    "where've": "where have",
    "which's": "which is",
    "who'd": "who did",
    "who'd": "who would",
    "who'll": "who will",
    "who're": "who are",
    "who's": "who is",
    "who've": "who have",
    "why'd": "why did",
    "why'll": "why will",
    "why're": "why are",
    "why's": "why is",
    "won't": "will not",
    "would've": "would have",
    "wouldn't": "would not",
    "y'all": "you all",
    "you'd": "you would",
    "you'll": "you will",
    "you're": "you are",
    "you've": "you have",
}

class WordSub(dict):
    """All-in-one multiple-string-substitution class."""

    def _wordToRegex(self, word):
        """Convert a word to a regex object which matches the word."""
        if word != "" and word[0].isalpha() and word[-1].isalpha():
            return "\\b%s\\b" % re.escape(word)
        else:
            return r"\b%s\b" % re.escape(word)

    def _update_regex(self):
        """Build re object based on the keys of the current
        dictionary.

        """
        self._regex = re.compile("|".join(map(self._wordToRegex, self.keys())), re.UNICODE)
        self._regexIsDirty = False

    def __init__(self, defaults={}):
        """Initialize the object, and populate it with the entries in
        the defaults dictionary.

        """
        self._regex = None
        self._regexIsDirty = True
        for k, v in defaults.items():
            self[k] = v

    def __call__(self, match):
        """Handler invoked for each regex match."""
        return self[match.group(0)]

    def __setitem__(self, i, y):
        self._regexIsDirty = True
        # for each entry the user adds, we actually add three entrys:
        super(type(self), self).__setitem__(i.capitalize(), y.capitalize())  # Key = Value
        super(type(self), self).__setitem__(string.upper(i), string.upper(y))  # KEY = VALUE
        super(type(self), self).__setitem__(i, y)  # key = value

    def sub(self, text):
        """Translate text, returns the modified text."""
        if self._regexIsDirty:
            self._update_regex()
        return self._regex.sub(self, text)

english_word_sub = WordSub(DEFAULT_ENGLISH_NORMAL)

# self-test
if __name__ == "__main__":
    print english_word_sub.sub("What's new")
    print english_word_sub.sub("what's new")
    print english_word_sub.sub("how is it")
    print english_word_sub.sub("how's it")
    print english_word_sub.sub("maybe [I'll] go")

    subber = WordSub()
    subber["apple"] = "banana"
    subber["orange"] = "pear"
    subber["banana"] = "apple"
    subber["he"] = "she"
    subber["I'd"] = "I would"

    # test case insensitivity
    inStr = "I'd like one apple, one Orange and one BANANA."
    outStr = "I would like one banana, one Pear and one APPLE."
    if subber.sub(inStr) == outStr:
        print "Test #1 PASSED"
    else:
        print "Test #1 FAILED: '%s'" % subber.sub(inStr)

    inStr = "He said he'd like to go with me"
    outStr = "She said she'd like to go with me"
    if subber.sub(inStr) == outStr:
        print "Test #2 PASSED"
    else:
        print "Test #2 FAILED: '%s'" % subber.sub(inStr)
