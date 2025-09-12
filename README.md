# fur2tad
Furnace to [Terrific Audio Driver](https://github.com/undisbeliever/terrific-audio-driver) converter. Furnace and TAD are built on very different concepts, so in many cases a 1-to-1 conversion may not be possible, or timing or the exact way an effect sounds may not be perfect, but it should be possible to get pretty close.

This converter will attempt to compress the generated MML with loops and subroutine calls. It will not currently try to reuse note data across channels. The converter will attempt to pick a combination of a TAD tick rate and ticks-per-row setting that should cause rows to happen at a speed that's less than a millisecond off from how it is in Furnace, but this does mean that different speeds may increase or decrease the amount of precision that effects can have (especially for vibrato). In the future there could be a flag that prioritizes a higher amount of TAD ticks over row durations being as close as possible.

The converter currently takes one command line argument: the filename of a Furnace file.

# Effects supported
These effects may have limitations or even be implemented incorrectly, because Furnace's manual is missing a lot of details on how effects actually work and that required reverse engineering.

Note effects:
* 00: **Arpeggio** - Cannot be combined with portamento
* 01, 02: **Pitch slide up/down** - Ending point of the slide is rounded to the nearest semitone
* 03: **Portamento**
* 04: **Vibrato** - Uses TAD's "MP vibrato" feature
* 0A, FA, F3, F4: **Volume slide**
* 09, 0F, F0: **Speed change** - Works for switching between groove patterns
* 11: **Toggle noise mode** - Should have 11 and 1D on the same channel
* 12: **Echo on/off**
* 13: **Pitch modulation**
* 14: **Invert** - Currently signals that the invert should only happen on surround sound mode
* 1D: **Noise frequency** - When not accompanied by a note, the converter will assume you want to play noise with legato
* 80: **Set pan**
* 83: **Pan slide**
* E0: **Arpeggio speed**
* E1, E2: **Note slide up/down**
* E4: **Vibrato range**
* EA: **Legato**
* F8, F9: **Single tick volume up/down**

Jumping between patterns:
* 0D: **Jump to next pattern**
* 0B: **Jump to order row** - Sets a loop point if jumping backwards
* FF: **Stop song** - Stops the song from looping

Other supported features:
* Groove/speed patterns

Some Furnace features that are not supported:
* Macros (Except for arpeggio macros that have only one step)
* Virtual tempo
* Wavetable
* Sample map
* Pitch and volume slides that would take more than 256 TAD timer ticks - Could be implemented by breaking the slide into parts

# Terrific Audio Driver's pitch table
Terrific Audio Driver precalculates pitches and stores them in a "pitch table" which can hold up to 256 entries and is shared across songs that share the same Common Audio Data. Each TAD instrument has a range of octaves it can use (which this converter automatically chooses based on what octaves the song data uses) and each octave takes up space in the pitch table. Instruments with the same sample rate can share data, so you can save space in the pitch table by having multiple Furnace instruments use the same sample rate. Arpeggio macros can be used to adjust the tuning of an instrument separately from the sample rate.

In addition to instruments, Terrific Audio Driver has "samples" (see [the TAD documentation](https://github.com/undisbeliever/terrific-audio-driver/blob/main/docs/samples.md)) which work similarly to instruments but have a specific list of sample rates the sample can be played at, instead of using notes. This means that only the specific rates specified end up in the pitch table, not an entire octave that may not be used. This is a good option for drums and other sounds that a song only intends to play at a few different pitches.

To specify that you want a Furnace instrument to turn into a TAD sample, use a sample map on the Furnace instrument, and only assign a Furnace sample to the notes that you would like to use. You can use a mix of different Furnace samples (helpful for setting up a drum kit), and the output note doesn't have to match the input note. The converter may not correctly handle using TAD samples in combination with some effects that alter pitch (such as portamento.)

# Metadata in instrument names
The converter checks for commands in each instrument's name, which will affect how the instrument is treated in the conversion process.

* `!remap`: Do not change the instrument into a TAD sample; instead, treat a sample map (if provided) as a table that lists what notes to change into which other notes. The samples on each entry in the sample map are ignored.
* `!sample`: Change the instrument into a TAD sample by looking at the song data to determine which notes (and consequently, sample rates) are needed. Will only currently work on Furnace files that contain a single song.

# Command line arguments
* `--auto-timer-mode low_error/lowest_error`: Choose a strategy for automatically choosing TAD timer values from Furnace speeds and tempos.
* `--timer-override bpm,speed=ticks bpm,speed=ticks bpm,speed=ticks`: Allows overriding the automatic Furnace speed conversions by providing your own timer values.
* `--ignore-arp-macro`: Do not use the arpeggio macros on instruments to determine the semitone offset.
* `--disable-loop-compression`: Do not attempt to compress the MML with loops.
* `--disable-sub-compression`: Do not attempt to compress the MML with subroutines.
* `--remove-instrument-names`: Rename all instruments to have a number instead of using the instrument's stored name.

`fur2tad` can set up a Terrific Audio Driver project file for you, and can dump samples. Samples must be in BRR format in Furnace when using either of these features.
* `--project-folder foldername`: Dump all of the samples to the folder, create .mml files for all of the included songs, and create a Terrific Audio Driver project file.
* `--dump-samples foldername`: Dump all of the samples to the folder as BRR files. These files are prefixed with the loop point if the sample is looped.
* `--keep-all-instruments`: Include all instruments in the project file, even if they aren't used in any of the songs.
* `--default-instrument-first-octave 0-7`: If using `--keep-all-instruments`, use this as the `first_octave` on instruments that weren't used.
* `--default-instrument-last-octave 0-7`: If using `--keep-all-instruments`, use this as the `last_octave` on instruments that weren't used.

# Impulse Tracker module support
An `it2tad.py` is provided, which can run Impulse Tracker music through the same conversion logic. `xmodits` is required and is used to extract samples from the file; `pip install xmodits-py` can be used to install it. The converter will use the single song contained in the `.it` file and multiple songs are not supported yet. `it2tad` will not fix your samples for you; the sample file length must be a multiple of 16 samples.

Caution: xmodits seems to throw an error when the wav files it's attempting to create already exist, so this tool will remove all wav files in the output directory whose name starts with two digits, a space, and a hyphen.

Impulse Tracker effects are converted into Furnace effects; not all Furnace effects are currently supported, and there may be mistakes.
* Volume effects become normal `D`, `E`, `F`, `G`, `H`, `X` effects
* `A` --> `09` (Speed)
* `B` --> `0B` (Switch pattern - cannot be used on the same row as `C` yet)
* `C` --> `0D` (Pattern break - cannot be used on the same row as `B` yet)
* `D` --> `0A` or `F8` or `F9` (Volume slide)
* `E` --> `02` or `F2` (Portamento down)
* `F` --> `01` or `F1` (Portamento up)
* `G` --> `03` (Portamento)
* `H` --> `04` (Vibrato)
* `J` --> `00` (Arpeggio)
* `K` --> `0A` or `F8` or `F9` plus `04` (Volume slide plus vibrato)
* `L` --> `0A` or `F8` or `F9` plus `03` (Volume slide plus portamento)
* `P` --> `83` (Pan slide; fine pan not supported yet)
* `R` --> `07` (Tremolo) - not supported by MML converter yet
* `S8x` --> `80` (Pan)
* `SCx` --> `EC` (Delayed note cut) - not supported by MML converter yet
* `SDx` --> `ED` (Delayed note start) - not supported by MML converter yet
* `T` --> `F0` (Change tempo; T0x and T1x unsupported)
* `X` --> `80` (Pan)
* `Y` --> `84` (Panbrello) - not supported by MML converter yet

Some Impules Tracker features that are not supported:
* New note actions
* Sample map
* Instrument loop points that are not at the start of the sample (could be added later)
* Instrument envelopes (instruments will use `gain F127`)
