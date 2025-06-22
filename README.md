# fur2tad
Furnace to [Terrific Audio Driver](https://github.com/undisbeliever/terrific-audio-driver) converter. Furnace and TAD are built on very different concepts, so in many cases a 1-to-1 conversion may not be possible, or timing or the exact way an effect sounds may not be perfect, but it should be possible to get pretty close.

This converter will attempt to compress the generated MML with loops and subroutine calls. It will not currently try to reuse note data across channels. The converter will attempt to pick a combination of a TAD tick rate and ticks-per-row setting that should cause rows to happen at a speed that's less than a millisecond off from how it is in Furnace, but this does mean that different speeds may increase or decrease the amount of precision that effects can have (especially for vibrato). In the future there could be a flag that prioritizes a higher amount of TAD ticks over row durations being as close as possible.

The converter currently takes one command line argument: the filename of a Furnace file.

# Effects supported
These effects may have limitations or even be implemented incorrectly, because Furnace's manual is missing a lot of details on how effects actually work and that required reverse engineering.

* 00: **Arpeggio** - Cannot be combined with portamento
* 01, 02: **Pitch slide up/down** - Ending point of the slide is rounded to the nearest semitone
* 03: **Portamento**
* 04: **Vibrato** - Uses TAD's "MP vibrato" feature
* 0A, FA, F3, F4: **Volume slide**
* 09, 0F, F0: **Speed change**
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

* 0D: **Jump to next pattern**
* 0B: **Jump to order row** - Sets a loop point if jumping backwards
* FF: **Stop song** - Stops the song from looping

Some Furnace features that are not supported:
* Macros
* Virtual tempo
* Wavetable
* Sample map
* Pitch and volume slides that would take more than 256 TAD timer ticks - Could be implemented by breaking the slide into parts
