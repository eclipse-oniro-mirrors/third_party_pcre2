#! /usr/bin/python

# Multistage table builder
# (c) Peter Kankowski, 2008

##############################################################################
# This script was submitted to the PCRE project by Peter Kankowski as part of
# the upgrading of Unicode property support. The new code speeds up property
# matching many times. The script is for the use of PCRE maintainers, to
# generate the pcre2_ucd.c file that contains a digested form of the Unicode
# data tables. A number of extensions have been added to the original script.
#
# The script has now been upgraded to Python 3 for PCRE2, and should be run in
# the maint subdirectory, using the command
#
# [python3] ./MultiStage2.py >../src/pcre2_ucd.c
#
# It requires six Unicode data tables: DerivedGeneralCategory.txt,
# GraphemeBreakProperty.txt, Scripts.txt, ScriptExtensions.txt,
# CaseFolding.txt, and emoji-data.txt. These must be in the
# maint/Unicode.tables subdirectory.
#
# DerivedGeneralCategory.txt is found in the "extracted" subdirectory of the
# Unicode database (UCD) on the Unicode web site; GraphemeBreakProperty.txt is
# in the "auxiliary" subdirectory. Scripts.txt, ScriptExtensions.txt, and
# CaseFolding.txt are directly in the UCD directory.
#
# The emoji-data.txt file is found in the "emoji" subdirectory even though it
# is technically part of a different (but coordinated) standard as shown
# in files associated with Unicode Technical Standard #51 ("Unicode Emoji"),
# for example:
#
# http://unicode.org/Public/emoji/13.0/ReadMe.txt
#
# -----------------------------------------------------------------------------
# Minor modifications made to this script:
#  Added #! line at start
#  Removed tabs
#  Made it work with Python 2.4 by rewriting two statements that needed 2.5
#  Consequent code tidy
#  Adjusted data file names to take from the Unicode.tables directory
#  Adjusted global table names by prefixing _pcre_.
#  Commented out stuff relating to the casefolding table, which isn't used;
#    removed completely in 2012.
#  Corrected size calculation
#  Add #ifndef SUPPORT_UCP to use dummy tables when no UCP support is needed.
#  Update for PCRE2: name changes, and SUPPORT_UCP is abolished.
#
# Major modifications made to this script:
#  Added code to add a grapheme break property field to records.
#
#  Added code to search for sets of more than two characters that must match
#  each other caselessly. A new table is output containing these sets, and
#  offsets into the table are added to the main output records. This new
#  code scans CaseFolding.txt instead of UnicodeData.txt, which is no longer
#  used.
#
#  Update for Python3:
#    . Processed with 2to3, but that didn't fix everything
#    . Changed string.strip to str.strip
#    . Added encoding='utf-8' to the open() call
#    . Inserted 'int' before blocksize/ELEMS_PER_LINE because an int is
#        required and the result of the division is a float
#
#  Added code to scan the emoji-data.txt file to find the Extended Pictographic
#  property, which is used by PCRE2 as a grapheme breaking property. This was
#  done when updating to Unicode 11.0.0 (July 2018).
#
#  Added code to add a Script Extensions field to records. This has increased
#  their size from 8 to 12 bytes, only 10 of which are currently used.
#
# 01-March-2010:     Updated list of scripts for Unicode 5.2.0
# 30-April-2011:     Updated list of scripts for Unicode 6.0.0
#     July-2012:     Updated list of scripts for Unicode 6.1.0
# 20-August-2012:    Added scan of GraphemeBreakProperty.txt and added a new
#                      field in the record to hold the value. Luckily, the
#                      structure had a hole in it, so the resulting table is
#                      not much bigger than before.
# 18-September-2012: Added code for multiple caseless sets. This uses the
#                      final hole in the structure.
# 30-September-2012: Added RegionalIndicator break property from Unicode 6.2.0
# 13-May-2014:       Updated for PCRE2
# 03-June-2014:      Updated for Python 3
# 20-June-2014:      Updated for Unicode 7.0.0
# 12-August-2014:    Updated to put Unicode version into the file
# 19-June-2015:      Updated for Unicode 8.0.0
# 02-July-2017:      Updated for Unicode 10.0.0
# 03-July-2018:      Updated for Unicode 11.0.0
# 07-July-2018:      Added code to scan emoji-data.txt for the Extended
#                      Pictographic property.
# 01-October-2018:   Added the 'Unknown' script name
# 03-October-2018:   Added new field for Script Extensions
# 27-July-2019:      Updated for Unicode 12.1.0
# 10-March-2020:     Updated for Unicode 13.0.0
# PCRE2-10.39:       Updated for Unicode 14.0.0
# ----------------------------------------------------------------------------
#
#
# The main tables generated by this script are used by macros defined in
# pcre2_internal.h. They look up Unicode character properties using short
# sequences of code that contains no branches, which makes for greater speed.
#
# Conceptually, there is a table of records (of type ucd_record), containing a
# script number, script extension value, character type, grapheme break type,
# offset to caseless matching set, offset to the character's other case, for
# every Unicode character. However, a real table covering all Unicode
# characters would be far too big. It can be efficiently compressed by
# observing that many characters have the same record, and many blocks of
# characters (taking 128 characters in a block) have the same set of records as
# other blocks. This leads to a 2-stage lookup process.
#
# This script constructs six tables. The ucd_caseless_sets table contains
# lists of characters that all match each other caselessly. Each list is
# in order, and is terminated by NOTACHAR (0xffffffff), which is larger than
# any valid character. The first list is empty; this is used for characters
# that are not part of any list.
#
# The ucd_digit_sets table contains the code points of the '9' characters in
# each set of 10 decimal digits in Unicode. This is used to ensure that digits
# in script runs all come from the same set. The first element in the vector
# contains the number of subsequent elements, which are in ascending order.
#
# The ucd_script_sets vector contains lists of script numbers that are the
# Script Extensions properties of certain characters. Each list is terminated
# by zero (ucp_Unknown). A character with more than one script listed for its
# Script Extension property has a negative value in its record. This is the
# negated offset to the start of the relevant list in the ucd_script_sets
# vector.
#
# The ucd_records table contains one instance of every unique record that is
# required. The ucd_stage1 table is indexed by a character's block number,
# which is the character's code point divided by 128, since 128 is the size
# of each block. The result of a lookup in ucd_stage1 a "virtual" block number.
#
# The ucd_stage2 table is a table of "virtual" blocks; each block is indexed by
# the offset of a character within its own block, and the result is the index
# number of the required record in the ucd_records vector.
#
# The following examples are correct for the Unicode 11.0.0 database. Future
# updates may make change the actual lookup values.
#
# Example: lowercase "a" (U+0061) is in block 0
#          lookup 0 in stage1 table yields 0
#          lookup 97 (0x61) in the first table in stage2 yields 17
#          record 17 is { 34, 5, 12, 0, -32, 34, 0 }
#            34 = ucp_Latin   => Latin script
#             5 = ucp_Ll      => Lower case letter
#            12 = ucp_gbOther => Grapheme break property "Other"
#             0               => Not part of a caseless set
#           -32 (-0x20)       => Other case is U+0041
#            34 = ucp_Latin   => No special Script Extension property
#             0               => Dummy value, unused at present
#
# Almost all lowercase latin characters resolve to the same record. One or two
# are different because they are part of a multi-character caseless set (for
# example, k, K and the Kelvin symbol are such a set).
#
# Example: hiragana letter A (U+3042) is in block 96 (0x60)
#          lookup 96 in stage1 table yields 90
#          lookup 66 (0x42) in table 90 in stage2 yields 564
#          record 564 is { 27, 7, 12, 0, 0, 27, 0 }
#            27 = ucp_Hiragana => Hiragana script
#             7 = ucp_Lo       => Other letter
#            12 = ucp_gbOther  => Grapheme break property "Other"
#             0                => Not part of a caseless set
#             0                => No other case
#            27 = ucp_Hiragana => No special Script Extension property
#             0                => Dummy value, unused at present
#
# Example: vedic tone karshana (U+1CD0) is in block 57 (0x39)
#          lookup 57 in stage1 table yields 55
#          lookup 80 (0x50) in table 55 in stage2 yields 458
#          record 458 is { 28, 12, 3, 0, 0, -101, 0 }
#            28 = ucp_Inherited => Script inherited from predecessor
#            12 = ucp_Mn        => Non-spacing mark
#             3 = ucp_gbExtend  => Grapheme break property "Extend"
#             0                 => Not part of a caseless set
#             0                 => No other case
#          -101                 => Script Extension list offset = 101
#             0                 => Dummy value, unused at present
#
# At offset 101 in the ucd_script_sets vector we find the list 3, 15, 107, 29,
# and terminator 0. This means that this character is expected to be used with
# any of those scripts, which are Bengali, Devanagari, Grantha, and Kannada.
#
#  Philip Hazel, 03 July 2008
##############################################################################


import re
import string
import sys

MAX_UNICODE = 0x110000
NOTACHAR = 0xffffffff


# Parse a line of Scripts.txt, GraphemeBreakProperty.txt or DerivedGeneralCategory.txt
def make_get_names(enum):
        return lambda chardata: enum.index(chardata[1])

# Parse a line of CaseFolding.txt
def get_other_case(chardata):
        if chardata[1] == 'C' or chardata[1] == 'S':
          return int(chardata[2], 16) - int(chardata[0], 16)
        return 0

# Parse a line of ScriptExtensions.txt
def get_script_extension(chardata):
        this_script_list = list(chardata[1].split(' '))
        if len(this_script_list) == 1:
          return script_abbrevs.index(this_script_list[0])

        script_numbers = []
        for d in this_script_list:
          script_numbers.append(script_abbrevs.index(d))
        script_numbers.append(0)
        script_numbers_length = len(script_numbers)

        for i in range(1, len(script_lists) - script_numbers_length + 1):
          for j in range(0, script_numbers_length):
            found = True
            if script_lists[i+j] != script_numbers[j]:
              found = False
              break
          if found:
            return -i

        # Not found in existing lists

        return_value = len(script_lists)
        script_lists.extend(script_numbers)
        return -return_value

# Read the whole table in memory, setting/checking the Unicode version
def read_table(file_name, get_value, default_value):
        global unicode_version

        f = re.match(r'^[^/]+/([^.]+)\.txt$', file_name)
        file_base = f.group(1)
        version_pat = r"^# " + re.escape(file_base) + r"-(\d+\.\d+\.\d+)\.txt$"
        file = open(file_name, 'r', encoding='utf-8')
        f = re.match(version_pat, file.readline())
        version = f.group(1)
        if unicode_version == "":
                unicode_version = version
        elif unicode_version != version:
                print("WARNING: Unicode version differs in %s", file_name, file=sys.stderr)

        table = [default_value] * MAX_UNICODE
        for line in file:
                line = re.sub(r'#.*', '', line)
                chardata = list(map(str.strip, line.split(';')))
                if len(chardata) <= 1:
                        continue
                value = get_value(chardata)
                m = re.match(r'([0-9a-fA-F]+)(\.\.([0-9a-fA-F]+))?$', chardata[0])
                char = int(m.group(1), 16)
                if m.group(3) is None:
                        last = char
                else:
                        last = int(m.group(3), 16)
                for i in range(char, last + 1):
                        # It is important not to overwrite a previously set
                        # value because in the CaseFolding file there are lines
                        # to be ignored (returning the default value of 0)
                        # which often come after a line which has already set
                        # data.
                        if table[i] == default_value:
                          table[i] = value
        file.close()
        return table

# Get the smallest possible C language type for the values
def get_type_size(table):
        type_size = [("uint8_t", 1), ("uint16_t", 2), ("uint32_t", 4),
                                 ("signed char", 1), ("pcre_int16", 2), ("pcre_int32", 4)]
        limits = [(0, 255), (0, 65535), (0, 4294967295),
                          (-128, 127), (-32768, 32767), (-2147483648, 2147483647)]
        minval = min(table)
        maxval = max(table)
        for num, (minlimit, maxlimit) in enumerate(limits):
                if minlimit <= minval and maxval <= maxlimit:
                        return type_size[num]
        else:
                raise OverflowError("Too large to fit into C types")

def get_tables_size(*tables):
        total_size = 0
        for table in tables:
                type, size = get_type_size(table)
                total_size += size * len(table)
        return total_size

# Compress the table into the two stages
def compress_table(table, block_size):
        blocks = {} # Dictionary for finding identical blocks
        stage1 = [] # Stage 1 table contains block numbers (indices into stage 2 table)
        stage2 = [] # Stage 2 table contains the blocks with property values
        table = tuple(table)
        for i in range(0, len(table), block_size):
                block = table[i:i+block_size]
                start = blocks.get(block)
                if start is None:
                        # Allocate a new block
                        start = len(stage2) / block_size
                        stage2 += block
                        blocks[block] = start
                stage1.append(start)

        return stage1, stage2

# Print a table
def print_table(table, table_name, block_size = None):
        type, size = get_type_size(table)
        ELEMS_PER_LINE = 16

        s = "const %s %s[] = { /* %d bytes" % (type, table_name, size * len(table))
        if block_size:
                s += ", block = %d" % block_size
        print(s + " */")
        table = tuple(table)
        if block_size is None:
                fmt = "%3d," * ELEMS_PER_LINE + " /* U+%04X */"
                mult = MAX_UNICODE / len(table)
                for i in range(0, len(table), ELEMS_PER_LINE):
                        print(fmt % (table[i:i+ELEMS_PER_LINE] +
                          (int(i * mult),)))
        else:
                if block_size > ELEMS_PER_LINE:
                        el = ELEMS_PER_LINE
                else:
                        el = block_size
                fmt = "%3d," * el + "\n"
                if block_size > ELEMS_PER_LINE:
                        fmt = fmt * int(block_size / ELEMS_PER_LINE)
                for i in range(0, len(table), block_size):
                        print(("/* block %d */\n" + fmt) % ((i / block_size,) + table[i:i+block_size]))
        print("};\n")

# Extract the unique combinations of properties into records
def combine_tables(*tables):
        records = {}
        index = []
        for t in zip(*tables):
                i = records.get(t)
                if i is None:
                        i = records[t] = len(records)
                index.append(i)
        return index, records

def get_record_size_struct(records):
        size = 0
        structure = '/* When recompiling tables with a new Unicode version, please check the\n' + \
        'types in this structure definition from pcre2_internal.h (the actual\n' + \
        'field names will be different):\n\ntypedef struct {\n'
        for i in range(len(records[0])):
                record_slice = [record[i] for record in records]
                slice_type, slice_size = get_type_size(record_slice)
                # add padding: round up to the nearest power of slice_size
                size = (size + slice_size - 1) & -slice_size
                size += slice_size
                structure += '%s property_%d;\n' % (slice_type, i)

        # round up to the first item of the next structure in array
        record_slice = [record[0] for record in records]
        slice_type, slice_size = get_type_size(record_slice)
        size = (size + slice_size - 1) & -slice_size

        structure += '} ucd_record;\n*/\n'
        return size, structure

def test_record_size():
        tests = [ \
          ( [(3,), (6,), (6,), (1,)], 1 ), \
          ( [(300,), (600,), (600,), (100,)], 2 ), \
          ( [(25, 3), (6, 6), (34, 6), (68, 1)], 2 ), \
          ( [(300, 3), (6, 6), (340, 6), (690, 1)], 4 ), \
          ( [(3, 300), (6, 6), (6, 340), (1, 690)], 4 ), \
          ( [(300, 300), (6, 6), (6, 340), (1, 690)], 4 ), \
          ( [(3, 100000), (6, 6), (6, 123456), (1, 690)], 8 ), \
          ( [(100000, 300), (6, 6), (123456, 6), (1, 690)], 8 ), \
        ]
        for test in tests:
            size, struct = get_record_size_struct(test[0])
            assert(size == test[1])
            #print struct

def print_records(records, record_size):
        print('const ucd_record PRIV(ucd_records)[] = { ' + \
              '/* %d bytes, record size %d */' % (len(records) * record_size, record_size))

        records = list(zip(list(records.keys()), list(records.values())))
        records.sort(key = lambda x: x[1])
        for i, record in enumerate(records):
                print(('  {' + '%6d, ' * len(record[0]) + '}, /* %3d */') % (record[0] + (i,)))
        print('};\n')

script_names = ['Unknown', 'Arabic', 'Armenian', 'Bengali', 'Bopomofo', 'Braille', 'Buginese', 'Buhid', 'Canadian_Aboriginal',
 'Cherokee', 'Common', 'Coptic', 'Cypriot', 'Cyrillic', 'Deseret', 'Devanagari', 'Ethiopic', 'Georgian',
 'Glagolitic', 'Gothic', 'Greek', 'Gujarati', 'Gurmukhi', 'Han', 'Hangul', 'Hanunoo', 'Hebrew', 'Hiragana',
 'Inherited', 'Kannada', 'Katakana', 'Kharoshthi', 'Khmer', 'Lao', 'Latin', 'Limbu', 'Linear_B', 'Malayalam',
 'Mongolian', 'Myanmar', 'New_Tai_Lue', 'Ogham', 'Old_Italic', 'Old_Persian', 'Oriya', 'Osmanya', 'Runic',
 'Shavian', 'Sinhala', 'Syloti_Nagri', 'Syriac', 'Tagalog', 'Tagbanwa', 'Tai_Le', 'Tamil', 'Telugu', 'Thaana',
 'Thai', 'Tibetan', 'Tifinagh', 'Ugaritic', 'Yi',
# New for Unicode 5.0
 'Balinese', 'Cuneiform', 'Nko', 'Phags_Pa', 'Phoenician',
# New for Unicode 5.1
 'Carian', 'Cham', 'Kayah_Li', 'Lepcha', 'Lycian', 'Lydian', 'Ol_Chiki', 'Rejang', 'Saurashtra', 'Sundanese', 'Vai',
# New for Unicode 5.2
 'Avestan', 'Bamum', 'Egyptian_Hieroglyphs', 'Imperial_Aramaic',
 'Inscriptional_Pahlavi', 'Inscriptional_Parthian',
 'Javanese', 'Kaithi', 'Lisu', 'Meetei_Mayek',
 'Old_South_Arabian', 'Old_Turkic', 'Samaritan', 'Tai_Tham', 'Tai_Viet',
# New for Unicode 6.0.0
 'Batak', 'Brahmi', 'Mandaic',
# New for Unicode 6.1.0
 'Chakma', 'Meroitic_Cursive', 'Meroitic_Hieroglyphs', 'Miao', 'Sharada', 'Sora_Sompeng', 'Takri',
# New for Unicode 7.0.0
 'Bassa_Vah', 'Caucasian_Albanian', 'Duployan', 'Elbasan', 'Grantha', 'Khojki', 'Khudawadi',
 'Linear_A', 'Mahajani', 'Manichaean', 'Mende_Kikakui', 'Modi', 'Mro', 'Nabataean',
 'Old_North_Arabian', 'Old_Permic', 'Pahawh_Hmong', 'Palmyrene', 'Psalter_Pahlavi',
 'Pau_Cin_Hau', 'Siddham', 'Tirhuta', 'Warang_Citi',
# New for Unicode 8.0.0
 'Ahom', 'Anatolian_Hieroglyphs', 'Hatran', 'Multani', 'Old_Hungarian',
 'SignWriting',
# New for Unicode 10.0.0
 'Adlam', 'Bhaiksuki', 'Marchen', 'Newa', 'Osage', 'Tangut', 'Masaram_Gondi',
 'Nushu', 'Soyombo', 'Zanabazar_Square',
# New for Unicode 11.0.0
  'Dogra', 'Gunjala_Gondi', 'Hanifi_Rohingya', 'Makasar', 'Medefaidrin',
  'Old_Sogdian', 'Sogdian',
# New for Unicode 12.0.0
  'Elymaic', 'Nandinagari', 'Nyiakeng_Puachue_Hmong', 'Wancho',
# New for Unicode 13.0.0
  'Chorasmian', 'Dives_Akuru', 'Khitan_Small_Script', 'Yezidi',
# New for Unicode 14.0.0
  'Cypro_Minoan', 'Old_Uyghur', 'Tangsa', 'Toto', 'Vithkuqi'
 ]

script_abbrevs = [
  'Zzzz', 'Arab', 'Armn', 'Beng', 'Bopo', 'Brai', 'Bugi', 'Buhd', 'Cans',
  'Cher', 'Zyyy', 'Copt', 'Cprt', 'Cyrl', 'Dsrt', 'Deva', 'Ethi', 'Geor',
  'Glag', 'Goth', 'Grek', 'Gujr', 'Guru', 'Hani', 'Hang', 'Hano', 'Hebr',
  'Hira', 'Zinh', 'Knda', 'Kana', 'Khar', 'Khmr', 'Laoo', 'Latn', 'Limb',
  'Linb', 'Mlym', 'Mong', 'Mymr', 'Talu', 'Ogam', 'Ital', 'Xpeo', 'Orya',
  'Osma', 'Runr', 'Shaw', 'Sinh', 'Sylo', 'Syrc', 'Tglg', 'Tagb', 'Tale',
  'Taml', 'Telu', 'Thaa', 'Thai', 'Tibt', 'Tfng', 'Ugar', 'Yiii',
#New for Unicode 5.0
  'Bali', 'Xsux', 'Nkoo', 'Phag', 'Phnx',
#New for Unicode 5.1
  'Cari', 'Cham', 'Kali', 'Lepc', 'Lyci', 'Lydi', 'Olck', 'Rjng', 'Saur',
  'Sund', 'Vaii',
#New for Unicode 5.2
  'Avst', 'Bamu', 'Egyp', 'Armi', 'Phli', 'Prti', 'Java', 'Kthi', 'Lisu',
  'Mtei', 'Sarb', 'Orkh', 'Samr', 'Lana', 'Tavt',
#New for Unicode 6.0.0
  'Batk', 'Brah', 'Mand',
#New for Unicode 6.1.0
  'Cakm', 'Merc', 'Mero', 'Plrd', 'Shrd', 'Sora', 'Takr',
#New for Unicode 7.0.0
  'Bass', 'Aghb', 'Dupl', 'Elba', 'Gran', 'Khoj', 'Sind', 'Lina', 'Mahj',
  'Mani', 'Mend', 'Modi', 'Mroo', 'Nbat', 'Narb', 'Perm', 'Hmng', 'Palm',
  'Phlp', 'Pauc', 'Sidd', 'Tirh', 'Wara',
#New for Unicode 8.0.0
  'Ahom', 'Hluw', 'Hatr', 'Mult', 'Hung', 'Sgnw',
#New for Unicode 10.0.0
  'Adlm', 'Bhks', 'Marc', 'Newa', 'Osge', 'Tang', 'Gonm', 'Nshu', 'Soyo',
  'Zanb',
#New for Unicode 11.0.0
  'Dogr', 'Gong', 'Rohg', 'Maka', 'Medf', 'Sogo', 'Sogd',
#New for Unicode 12.0.0
  'Elym', 'Nand', 'Hmnp', 'Wcho',
#New for Unicode 13.0.0
  'Chrs', 'Diak', 'Kits', 'Yezi',
#New for Unicode 14.0.0
  'Cpmn', 'Ougr', 'Tngs', 'Toto', 'Vith'
 ]

category_names = ['Cc', 'Cf', 'Cn', 'Co', 'Cs', 'Ll', 'Lm', 'Lo', 'Lt', 'Lu',
  'Mc', 'Me', 'Mn', 'Nd', 'Nl', 'No', 'Pc', 'Pd', 'Pe', 'Pf', 'Pi', 'Po', 'Ps',
  'Sc', 'Sk', 'Sm', 'So', 'Zl', 'Zp', 'Zs' ]

# The Extended_Pictographic property is not found in the file where all the
# others are (GraphemeBreakProperty.txt). It comes from the emoji-data.txt
# file, but we list it here so that the name has the correct index value.

break_property_names = ['CR', 'LF', 'Control', 'Extend', 'Prepend',
  'SpacingMark', 'L', 'V', 'T', 'LV', 'LVT', 'Regional_Indicator', 'Other',
  'ZWJ', 'Extended_Pictographic' ]

test_record_size()
unicode_version = ""

script = read_table('Unicode.tables/Scripts.txt', make_get_names(script_names), script_names.index('Unknown'))
category = read_table('Unicode.tables/DerivedGeneralCategory.txt', make_get_names(category_names), category_names.index('Cn'))
break_props = read_table('Unicode.tables/GraphemeBreakProperty.txt', make_get_names(break_property_names), break_property_names.index('Other'))
other_case = read_table('Unicode.tables/CaseFolding.txt', get_other_case, 0)

# The grapheme breaking rules were changed for Unicode 11.0.0 (June 2018). Now
# we need to find the Extended_Pictographic property for emoji characters. This
# can be set as an additional grapheme break property, because the default for
# all the emojis is "other". We scan the emoji-data.txt file and modify the
# break-props table.

file = open('Unicode.tables/emoji-data.txt', 'r', encoding='utf-8')
for line in file:
        line = re.sub(r'#.*', '', line)
        chardata = list(map(str.strip, line.split(';')))
        if len(chardata) <= 1:
                continue

        if chardata[1] != "Extended_Pictographic":
                continue

        m = re.match(r'([0-9a-fA-F]+)(\.\.([0-9a-fA-F]+))?$', chardata[0])
        char = int(m.group(1), 16)
        if m.group(3) is None:
                last = char
        else:
                last = int(m.group(3), 16)
        for i in range(char, last + 1):
                if break_props[i] != break_property_names.index('Other'):
                   print("WARNING: Emoji 0x%x has break property %s, not 'Other'",
                     i, break_property_names[break_props[i]], file=sys.stderr)
                break_props[i] = break_property_names.index('Extended_Pictographic')
file.close()

# The Script Extensions property default value is the Script value. Parse the
# file, setting 'Unknown' as the default (this will never be a Script Extension
# value), then scan it and fill in the default from Scripts. Code added by PH
# in October 2018. Positive values are used for just a single script for a
# code point. Negative values are negated offsets in a list of lists of
# multiple scripts. Initialize this list with a single entry, as the zeroth
# element is never used.

script_lists = [0]
script_abbrevs_default = script_abbrevs.index('Zzzz')
scriptx = read_table('Unicode.tables/ScriptExtensions.txt', get_script_extension, script_abbrevs_default)

for i in range(0, MAX_UNICODE):
  if scriptx[i] == script_abbrevs_default:
    scriptx[i] = script[i]

# With the addition of the new Script Extensions field, we need some padding
# to get the Unicode records up to 12 bytes (multiple of 4). Set a value
# greater than 255 to make the field 16 bits.

padding_dummy = [0] * MAX_UNICODE
padding_dummy[0] = 256

# This block of code was added by PH in September 2012. I am not a Python
# programmer, so the style is probably dreadful, but it does the job. It scans
# the other_case table to find sets of more than two characters that must all
# match each other caselessly. Later in this script a table of these sets is
# written out. However, we have to do this work here in order to compute the
# offsets in the table that are inserted into the main table.

# The CaseFolding.txt file lists pairs, but the common logic for reading data
# sets only one value, so first we go through the table and set "return"
# offsets for those that are not already set.

for c in range(MAX_UNICODE):
  if other_case[c] != 0 and other_case[c + other_case[c]] == 0:
    other_case[c + other_case[c]] = -other_case[c]

# Now scan again and create equivalence sets.

sets = []

for c in range(MAX_UNICODE):
  o = c + other_case[c]

  # Trigger when this character's other case does not point back here. We
  # now have three characters that are case-equivalent.

  if other_case[o] != -other_case[c]:
    t = o + other_case[o]

    # Scan the existing sets to see if any of the three characters are already
    # part of a set. If so, unite the existing set with the new set.

    appended = 0
    for s in sets:
      found = 0
      for x in s:
        if x == c or x == o or x == t:
          found = 1

      # Add new characters to an existing set

      if found:
        found = 0
        for y in [c, o, t]:
          for x in s:
            if x == y:
              found = 1
          if not found:
            s.append(y)
        appended = 1

    # If we have not added to an existing set, create a new one.

    if not appended:
      sets.append([c, o, t])

# End of loop looking for caseless sets.

# Now scan the sets and set appropriate offsets for the characters.

caseless_offsets = [0] * MAX_UNICODE

offset = 1;
for s in sets:
  for x in s:
    caseless_offsets[x] = offset
  offset += len(s) + 1

# End of block of code for creating offsets for caseless matching sets.


# Combine the tables

table, records = combine_tables(script, category, break_props,
  caseless_offsets, other_case, scriptx, padding_dummy)

record_size, record_struct = get_record_size_struct(list(records.keys()))

# Find the optimum block size for the two-stage table
min_size = sys.maxsize
for block_size in [2 ** i for i in range(5,10)]:
        size = len(records) * record_size
        stage1, stage2 = compress_table(table, block_size)
        size += get_tables_size(stage1, stage2)
        #print "/* block size %5d  => %5d bytes */" % (block_size, size)
        if size < min_size:
                min_size = size
                min_stage1, min_stage2 = stage1, stage2
                min_block_size = block_size

print("/* This module is generated by the maint/MultiStage2.py script.")
print("Do not modify it by hand. Instead modify the script and run it")
print("to regenerate this code.")
print()
print("As well as being part of the PCRE2 library, this module is #included")
print("by the pcre2test program, which redefines the PRIV macro to change")
print("table names from _pcre2_xxx to xxxx, thereby avoiding name clashes")
print("with the library. At present, just one of these tables is actually")
print("needed. */")
print()
print("#ifndef PCRE2_PCRE2TEST")
print()
print("#ifdef HAVE_CONFIG_H")
print("#include \"config.h\"")
print("#endif")
print()
print("#include \"pcre2_internal.h\"")
print()
print("#endif /* PCRE2_PCRE2TEST */")
print()
print("/* Unicode character database. */")
print("/* This file was autogenerated by the MultiStage2.py script. */")
print("/* Total size: %d bytes, block size: %d. */" % (min_size, min_block_size))
print()
print("/* The tables herein are needed only when UCP support is built,")
print("and in PCRE2 that happens automatically with UTF support.")
print("This module should not be referenced otherwise, so")
print("it should not matter whether it is compiled or not. However")
print("a comment was received about space saving - maybe the guy linked")
print("all the modules rather than using a library - so we include a")
print("condition to cut out the tables when not needed. But don't leave")
print("a totally empty module because some compilers barf at that.")
print("Instead, just supply some small dummy tables. */")
print()
print("#ifndef SUPPORT_UNICODE")
print("const ucd_record PRIV(ucd_records)[] = {{0,0,0,0,0,0,0 }};")
print("const uint16_t PRIV(ucd_stage1)[] = {0};")
print("const uint16_t PRIV(ucd_stage2)[] = {0};")
print("const uint32_t PRIV(ucd_caseless_sets)[] = {0};")
print("#else")
print()
print("const char *PRIV(unicode_version) = \"{}\";".format(unicode_version))
print()
print("/* If the 32-bit library is run in non-32-bit mode, character values")
print("greater than 0x10ffff may be encountered. For these we set up a")
print("special record. */")
print()
print("#if PCRE2_CODE_UNIT_WIDTH == 32")
print("const ucd_record PRIV(dummy_ucd_record)[] = {{")
print("  ucp_Unknown,    /* script */")
print("  ucp_Cn,         /* type unassigned */")
print("  ucp_gbOther,    /* grapheme break property */")
print("  0,              /* case set */")
print("  0,              /* other case */")
print("  ucp_Unknown,    /* script extension */")
print("  0,              /* dummy filler */")
print("  }};")
print("#endif")
print()
print(record_struct)

# --- Added by PH: output the table of caseless character sets ---

print("/* This table contains lists of characters that are caseless sets of")
print("more than one character. Each list is terminated by NOTACHAR. */\n")

print("const uint32_t PRIV(ucd_caseless_sets)[] = {")
print("  NOTACHAR,")
for s in sets:
  s = sorted(s)
  for x in s:
    print('  0x%04x,' % x, end=' ')
  print('  NOTACHAR,')
print('};')
print()

# ------

print("/* When #included in pcre2test, we don't need the table of digit")
print("sets, nor the the large main UCD tables. */")
print()
print("#ifndef PCRE2_PCRE2TEST")
print()

# --- Added by PH: read Scripts.txt again for the sets of 10 digits. ---

digitsets = []
file = open('Unicode.tables/Scripts.txt', 'r', encoding='utf-8')

for line in file:
  m = re.match(r'([0-9a-fA-F]+)\.\.([0-9a-fA-F]+)\s+;\s+\S+\s+#\s+Nd\s+', line)
  if m is None:
    continue
  first = int(m.group(1),16)
  last  = int(m.group(2),16)
  if ((last - first + 1) % 10) != 0:
    print("ERROR: %04x..%04x does not contain a multiple of 10 characters" % (first, last),
      file=sys.stderr)
  while first < last:
    digitsets.append(first + 9)
    first += 10
file.close()
digitsets.sort()

print("/* This table lists the code points for the '9' characters in each")
print("set of decimal digits. It is used to ensure that all the digits in")
print("a script run come from the same set. */\n")
print("const uint32_t PRIV(ucd_digit_sets)[] = {")

print("  %d,  /* Number of subsequent values */" % len(digitsets), end='')
count = 8
for d in digitsets:
  if count == 8:
    print("\n ", end='')
    count = 0
  print(" 0x%05x," % d, end='')
  count += 1
print("\n};\n")

print("/* This vector is a list of lists of scripts for the Script Extension")
print("property. Each sublist is zero-terminated. */\n")
print("const uint8_t PRIV(ucd_script_sets)[] = {")

count = 0
print("  /*   0 */", end='')
for d in script_lists:
  print(" %3d," % d, end='')
  count += 1
  if d == 0:
    print("\n  /* %3d */" % count, end='')
print("\n};\n")

# Output the main UCD tables.

print("/* These are the main two-stage UCD tables. The fields in each record are:")
print("script (8 bits), character type (8 bits), grapheme break property (8 bits),")
print("offset to multichar other cases or zero (8 bits), offset to other case")
print("or zero (32 bits, signed), script extension (16 bits, signed), and a dummy")
print("16-bit field to make the whole thing a multiple of 4 bytes. */\n")

print_records(records, record_size)
print_table(min_stage1, 'PRIV(ucd_stage1)')
print_table(min_stage2, 'PRIV(ucd_stage2)', min_block_size)
print("#if UCD_BLOCK_SIZE != %d" % min_block_size)
print("#error Please correct UCD_BLOCK_SIZE in pcre2_internal.h")
print("#endif")
print("#endif  /* SUPPORT_UNICODE */")
print()
print("#endif  /* PCRE2_PCRE2TEST */")


# This code was part of the original contribution, but is commented out as it
# was never used. A two-stage table has sufficed.

"""

# Three-stage tables:

# Find the optimum block size for 3-stage table
min_size = sys.maxint
for stage3_block in [2 ** i for i in range(2,6)]:
        stage_i, stage3 = compress_table(table, stage3_block)
        for stage2_block in [2 ** i for i in range(5,10)]:
                size = len(records) * 4
                stage1, stage2 = compress_table(stage_i, stage2_block)
                size += get_tables_size(stage1, stage2, stage3)
                # print "/* %5d / %3d  => %5d bytes */" % (stage2_block, stage3_block, size)
                if size < min_size:
                        min_size = size
                        min_stage1, min_stage2, min_stage3 = stage1, stage2, stage3
                        min_stage2_block, min_stage3_block = stage2_block, stage3_block

print "/* Total size: %d bytes" % min_size */
print_records(records)
print_table(min_stage1, 'ucd_stage1')
print_table(min_stage2, 'ucd_stage2', min_stage2_block)
print_table(min_stage3, 'ucd_stage3', min_stage3_block)

"""