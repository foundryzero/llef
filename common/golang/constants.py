"""Go-specific constant definitions."""

from collections import namedtuple

# GO_MAGIC_* enumerates the possibilities for the first 4 bytes of the PCLNTAB.
GO_MAGIC_2_TO_15 = 0xFFFFFFFB
GO_MAGIC_16_TO_17 = 0xFFFFFFFA
GO_MAGIC_18_TO_19 = 0xFFFFFFF0
GO_MAGIC_20_TO_24 = 0xFFFFFFF1

# This list must include all the above magic numbers.
GO_MAGICS = [GO_MAGIC_2_TO_15, GO_MAGIC_16_TO_17, GO_MAGIC_18_TO_19, GO_MAGIC_20_TO_24]

# Sections in which the PCLNTAB can live.
GO_PCLNTAB_NAMES = [".gopclntab", "__gopclntab"]
# Sections in which the ModuleData structure can live.
GO_NOPTRDATA_NAMES = [".noptrdata", "__noptrdata", ".data"]

# GO_MD_* enumerates the offsets where useful fields live in the ModuleData section. They are version-specific.
# The offset is an index into the ModuleData structure, cast as an array of pointer-sized ints.

# Description of fields within ModuleData:
#   minpc, maxpc are lower/upper bounds for the program counter - i.e. denotes the text section.
#   types, etypes denote the bounds of the types section (storing type information structures)
#   typelinks is an array of offsets to these type information structures. The length is typelinks_len.
ModuleDataOffsets = namedtuple("ModuleDataOffsets", ["minpc", "maxpc", "types", "etypes", "typelinks", "typelinks_len"])
GO_MD_7_ONLY = ModuleDataOffsets(minpc=10, maxpc=11, types=25, etypes=26, typelinks=27, typelinks_len=28)
GO_MD_8_TO_15 = ModuleDataOffsets(minpc=10, maxpc=11, types=25, etypes=26, typelinks=30, typelinks_len=31)
GO_MD_16_TO_17 = ModuleDataOffsets(minpc=20, maxpc=21, types=35, etypes=36, typelinks=40, typelinks_len=41)
GO_MD_18_TO_19 = ModuleDataOffsets(minpc=20, maxpc=21, types=35, etypes=36, typelinks=42, typelinks_len=43)
GO_MD_20_TO_24 = ModuleDataOffsets(minpc=20, maxpc=21, types=37, etypes=38, typelinks=44, typelinks_len=45)

GO_MAX_SLICE_EXTRACT = 100  # don't extract more than this many elements of a slice
GO_MAX_STRING_READ = 1000  # don't extract more than this many bytes of string

# Parameters for rate_candidate_length when calculating heuristics.
GO_TUNE_SLICE_THRESHOLD = 1000
GO_TUNE_SLICE_RATE = 100
GO_TUNE_STRING_THRESHOLD = 40
GO_TUNE_STRING_RATE = 5

# We'll truncate strings if they're longer than this.
GO_STR_TRUNCATE_LEN = 32

# Threshold to separate pointer guesses from numbers by value.
GO_MIN_PTR = 0x1000

# Maximum number of directories in swiss map to extract.
GO_MAX_SWISSMAP_DIRS = 65536

# Exponent of probability for bitstring entropy, to permit more extraordinary strings.
GO_ENTROPY_SOFTNESS = 0.3

GO_DEFAULT_UNPACK_DEPTH = 3

# The depth to decode types found and annotated inline (substituting name for type constructors).
GO_TYPE_DECODE_DEPTH = 2
# The depth to unpack objects found and annotated inline. Strings will always be truncated if too long.
GO_OBJECT_UNPACK_DEPTH = 3

# These two control the capacities of least-recently-added dictionaries that store guess information.
# This is a balancing act of:
#   1. Not forgetting types / strings too quickly, possibly even with the same context display.
#   2. Hanging onto types for too long, when the pointer has been garbage collected and is now something else.
# Err on the side of (1), given that a bit of junk being displayed is okay.
GO_TYPE_GUESS_CAPACITY = 64
GO_STRING_GUESS_CAPACITY = 128
