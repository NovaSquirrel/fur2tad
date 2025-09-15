# fur2tad
#
# Copyright (c) 2025 NovaSquirrel
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# https://modland.com/pub/documents/format_documentation/Impulse%20Tracker%20v2.04%20(.it).html
# https://fileformats.fandom.com/wiki/Impulse_tracker
import io, os, json, glob
import xmodits # pip install xmodits-py
from fur2tad import *

IT_EFFECT_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ#\\" # 0x01 through 0x1C

class ImpulseTrackerInstrumentSampleMixin(object):
	def to_dict(self, sample_filenames, sample_num=None):
		if hasattr(self, "sample"):
			look_for = "%.2d - " % (sample_num+1)
		else:
			look_for = "%.2d - " % (sample_num+1)
		sample = self.tracker_file.tracker_samples[sample_num]

		for filename in sample_filenames:
			filename_to_use = filename
			brr_filename = os.path.splitext(filename)[0]+'.brr'
			if os.path.exists(brr_filename):
				filename_to_use = brr_filename

			wav_basename = os.path.basename(filename_to_use)
			if wav_basename.startswith(look_for):
				c4_rate = sample.c4_rate

				c4_freq = 261.626
				wavelength = c4_rate / c4_freq
				tuning_freq = 32000 / wavelength

				instrument_entry = {
					"name": self.name,
					"source": wav_basename,
					"freq": tuning_freq,
					"loop": "loop_with_filter" if sample.flags_looped else "none",
					"envelope": self.envelope,
				}
				if sample.flags_looped:
					instrument_entry["loop_setting"] = 0
				return instrument_entry
		print("Couldn't find file for sample number %d" % (sample_num+1))
		return None

	def apply_commands_from_name(self, filename):
		self.envelope = "gain F127"
		self.become_tad_sample = False

		if not filename.startswith("!"):
			return

		i = 1
		command_mode = False
		while i < len(filename):
			next_i = i+1
			command = filename[i]
			if command == 's':
				self.become_tad_sample = True
			elif command == 'g':
				self.envelope = "gain " + filename[next_i]
				next_i += 1
				while next_i < len(filename) and filename[next_i].isdigit():
					self.envelope += filename[next_i]
					next_i += 1
			elif command == 'a':
				attack  = int(filename[next_i+0], 16)
				decay   = int(filename[next_i+1], 16)
				sustain = int(filename[next_i+2], 16)
				release = int(filename[next_i+3:next_i+5], 16)
				self.envelope = "adsr %d %d %d %d" % (attack, decay, sustain, release)
				next_i += 5
			else:
				print("Unrecognized instrument name command:", command)
				return
			i = next_i

class ImpulseTrackerInstrument(ImpulseTrackerInstrumentSampleMixin, TrackerInstrument):
	def __init__(self):
		# Set defaults
		self.semitone_offset = 0                 # Taken from arpeggio macro if present
		self.volume_scale = 1                    # Stacks on top of note volume and envelope volume
		self.delayed_tad_sample_creation = False # Instead of creating TAD samples at instrument parse time, create them after the song is parsed
		self.note_remap = {}                     # Index is Furnace note (pre-offset), and value is Furnace note

		self.tracker_sample_number_for_note = {} # Index is Furnace note (pre-offset), and value is a tracker sample number
		self.tad_sample_for_note = {}            # Index is Furnace note (pre-offset), and value is a TerrificSample
		self.tad_instrument_for_note = {}        # Index is Furnace note (pre-offset), and value is a TerrificInstrument
		self.tad_instrument = None               # Single TAD instrument
		self.tad_sample = None                   # Single TAD sample

		self.instrument_is_used = False          # True if there is a note somewhere that uses this instrument

class ImpulseTrackerSample(TrackerSample, ImpulseTrackerInstrumentSampleMixin, TrackerInstrument):
	def __init__(self):
		# Set defaults
		self.semitone_offset = 0                 # Taken from arpeggio macro if present
		self.volume_scale = 1                    # Stacks on top of note volume and envelope volume
		self.delayed_tad_sample_creation = False # Instead of creating TAD samples at instrument parse time, create them after the song is parsed
		self.note_remap = {}                     # Index is Furnace note (pre-offset), and value is Furnace note

		self.tracker_sample_number_for_note = {} # Index is Furnace note (pre-offset), and value is a tracker sample number
		self.tad_sample_for_note = {}            # Index is Furnace note (pre-offset), and value is a TerrificSample
		self.tad_instrument_for_note = {}        # Index is Furnace note (pre-offset), and value is a TerrificInstrument
		self.tad_instrument = None               # Single TAD instrument
		self.tad_sample = None                   # Single TAD sample

		self.instrument_is_used = False          # True if there is a note somewhere that uses this instrument

class ImpulseTrackerFile(object):
	def __init__(self, filename):
		# Storage for things defined in the file
		self.songs = []
		self.tracker_instruments = []
		self.tracker_samples = []
		self.tad_instruments = []
		self.tad_samples = []

		# Variables that are expected but not used
		self.groove_patterns = []

		# Open the file
		f = open(filename, "rb")
		self.bytes = f.read()
		f.close()
		s = io.BytesIO(self.bytes) # Set it up as a stream

		###################################################
		# Header
		###################################################

		magic = s.read(4)
		if magic != b'IMPM':
			raise Exception("Not an Impulse Tracker module")
		song_name = s.read(26).decode()
		rows_per_beat = bytes_to_int(s.read(1))
		rows_per_measure = bytes_to_int(s.read(1))

		order_count = bytes_to_int(s.read(2))
		instrument_count = bytes_to_int(s.read(2))
		sample_count = bytes_to_int(s.read(2))
		pattern_count = bytes_to_int(s.read(2))

		created_with_version = bytes_to_int(s.read(2))
		compatible_with_version = bytes_to_int(s.read(2))
		
		flags = bytes_to_int(s.read(2))
		special = bytes_to_int(s.read(2))
		self.use_instruments = bool(flags & 4)

		global_volume = bytes_to_int(s.read(1))
		mix_volume = bytes_to_int(s.read(1))

		initial_speed = bytes_to_int(s.read(1))
		initial_tempo = bytes_to_int(s.read(1))
		pan_separaration = bytes_to_int(s.read(1))
		pitch_wheel_depth = bytes_to_int(s.read(1))

		message_length = bytes_to_int(s.read(2))
		message_offset = bytes_to_int(s.read(4))

		reserved = bytes_to_int(s.read(4))

		initial_channel_pan = s.read(64)
		initial_channel_volume = s.read(64)

		orders = []
		for i in range(order_count):
			o = bytes_to_int(s.read(1))
			if o < 254: # 254 is separator and 255 is song end
				orders.append(o)

		instrument_offsets = []
		for i in range(instrument_count):
			instrument_offsets.append(bytes_to_int(s.read(4)))

		sample_offsets = []
		for i in range(sample_count):
			sample_offsets.append(bytes_to_int(s.read(4)))

		pattern_offsets = []
		for i in range(pattern_count):
			pattern_offsets.append(bytes_to_int(s.read(4)))

		###################################################
		# Set up song structure
		###################################################

		song = TrackerSong()
		song.name = song_name.replace(" ", "_").replace(chr(0), "")
		song.speed_pattern = [initial_speed]
		song.speed1 = initial_speed
		song.ticks_per_second = initial_tempo / 2.5
		song.orders = []
		for channel in range(CHANNELS):
			song.orders.append(orders)
		song.orders_length = len(orders)
		song.furnace_file = self
		self.song = song

		###################################################
		# Samples
		###################################################
		for sample_number in range(sample_count):
			sample = ImpulseTrackerSample()
			s.seek(sample_offsets[sample_number])
			magic = s.read(4)
			sample.dos_filename = s.read(12).decode().replace(chr(0), "")
			sample.apply_commands_from_name(sample.dos_filename)
			s.read(1) # Reserved
			sample.global_volume  = bytes_to_int(s.read(1))
			sample.flags          = bytes_to_int(s.read(1))
			sample.flags_is_16bit     = bool(sample.flags & 2)
			sample.flags_compressed   = bool(sample.flags & 8)
			sample.flags_looped       = bool(sample.flags & 16)
			sample.flags_sustain_loop = bool(sample.flags & 32)

			sample.default_volume = bytes_to_int(s.read(1))
			sample.name           = s.read(26).decode().replace(" ", "_").replace(chr(0), "")
			if args.remove_instrument_names:
				sample.name = "sample%d" % sample_number
			sample.convert_flags  = bytes_to_int(s.read(1))
			sample.data_is_signed     = bool(sample.convert_flags & 1)
			sample.data_is_big_endian = bool(sample.convert_flags & 2)
			sample.data_is_delta_encoded = bool(sample.convert_flags & 4)
			sample.data_is_byte_delta_encoded = bool(sample.convert_flags & 8)
			sample.prompt_left_right_all_stereo = bool(sample.convert_flags & 16)

			sample.default_pan    = bytes_to_int(s.read(1))
			sample.sample_length  = bytes_to_int(s.read(4))
			sample.loop_beginning = bytes_to_int(s.read(4))
			sample.loop_end       = bytes_to_int(s.read(4))
			sample.c4_rate        = bytes_to_int(s.read(4))
			if sample.flags_is_16bit: # IT sample rate is in bytes, whereas sample.c4_rate is in samples
				sample.c4_rate /= 2
			sample.sustain_beginning = bytes_to_int(s.read(4))
			sample.sustain_end    = bytes_to_int(s.read(4))
			sample.sample_pointer = bytes_to_int(s.read(4))
			sample.vibrato_speed  = bytes_to_int(s.read(1))
			sample.vibrato_depth  = bytes_to_int(s.read(1))
			sample.vibrato_sweep  = bytes_to_int(s.read(1))
			sample.vibrato_waveform = bytes_to_int(s.read(1))

			# Avoid duplicate names
			for other_sample in self.tracker_samples:
				if other_sample.name == sample.name:
					sample.name = "sample%d" % sample_number
					break

			sample.tracker_sample = sample_number
			sample.tracker_file = self
			self.tracker_samples.append(sample)

		###################################################
		# Instruments
		###################################################
		for instrument_number in range(instrument_count):
			instrument = ImpulseTrackerInstrument()
			s.seek(instrument_offsets[instrument_number])
			magic = s.read(4)
			instrument.dos_filename = s.read(12).decode().replace(chr(0), "")
			instrument.apply_commands_from_name(instrument.dos_filename)
			s.read(1) # Reserved
			instrument.new_note_action = bytes_to_int(s.read(1))
			instrument.duplicate_check_type = bytes_to_int(s.read(1))
			instrument.duplicate_check_action = bytes_to_int(s.read(1))
			instrument.fade_out = bytes_to_int(s.read(2), signed=True)
			instrument.pitch_pan_separation = bytes_to_int(s.read(1))
			instrument.pitch_pan_center = bytes_to_int(s.read(1))
			instrument.global_volume = bytes_to_int(s.read(1))
			instrument.default_pan = bytes_to_int(s.read(1))
			instrument.random_volume_variation = bytes_to_int(s.read(1))
			instrument.random_pan_variation = bytes_to_int(s.read(1))
			instrument.tracker_version = bytes_to_int(s.read(2))
			instrument.sample_count = bytes_to_int(s.read(1))
			s.read(1) # Reserved
			instrument.name = s.read(26).decode().replace(" ", "_").replace(chr(0), "")
			if args.remove_instrument_names:
				instrument.name = "instrument%d" % instrument_number
			s.read(6) # Skip ahead

			# Avoid duplicate names
			for other_instrument in self.tracker_instruments:
				if other_instrument.name == instrument.name:
					instrument.name = "instrument%d" % instrument_number
					break

			# Parse the sample map
			for i in range(120):
				note_to_play   = bytes_to_int(s.read(1)) + 12*5
				sample_to_play = bytes_to_int(s.read(1))
				if sample_to_play == 0:
					continue
				instrument.tracker_sample_number_for_note[i + 12*5] = sample_to_play - 1
				instrument.note_remap[i + 12*5] = note_to_play

			instrument.tracker_file = self
			self.tracker_instruments.append(instrument)

		###################################################
		# Song data
		###################################################
		for pattern_number in range(pattern_count):
			if pattern_offsets[pattern_number] == 0: # Unused pattern
				continue
			s.seek(pattern_offsets[pattern_number]) # Start reading from pattern
			packed_pattern_length = bytes_to_int(s.read(2))
			row_count = bytes_to_int(s.read(2))
			s.read(4) # Reserved
			# Now reading packed pattern data

			# Set up data structure
			channel_patterns = [FurnacePattern() for _ in range(CHANNELS)]
			for channel in range(CHANNELS):
				channel_patterns[channel].rows = [FurnaceNote() for _ in range(row_count)]
				song.patterns[channel][pattern_number] = channel_patterns[channel]

			# State to keep track of reading this pattern
			last_mask_variable = [0] * 64
			last_note          = [0] * 64
			last_instrument    = [0] * 64
			last_volume        = [0] * 64
			last_effect        = [0] * 64

			for row_number in range(row_count):
				mask_variable = 0
				while True:
					channel_mask = bytes_to_int(s.read(1))
					if channel_mask == 0:
						break
					channel = (channel_mask - 1) & 63
					if channel_mask & 0x80:
						last_mask_variable[channel] = bytes_to_int(s.read(1))
					mask_variable = last_mask_variable[channel]

					note = FurnaceNote()

					if mask_variable & 0x01:
						last_note[channel]         = bytes_to_int(s.read(1))
					if mask_variable & 0x02:
						last_instrument[channel]   = bytes_to_int(s.read(1))
					if mask_variable & 0x04:
						last_volume[channel]       = bytes_to_int(s.read(1))
					if mask_variable & 0x08:
						last_effect[channel]       = bytes_to_int(s.read(2)) # Effect byte, then effect value; will be read as little endian
					if mask_variable & 0x11: # Note
						if last_note[channel] == 255:
							note.note = NoteValue.OFF
						elif last_note[channel] == 254:
							note.note = NoteValue.RELEASE
						else:
							note.note = last_note[channel] + 12*5

					if mask_variable & 0x22: # Instrument
						note.instrument = last_instrument[channel] - 1
						song.instruments_used.add(note.instrument)

					effects = [] # Effects for this note
					if mask_variable & 0x44: # Volume
						# Convert 0-63 volume to 0-255
						volume = last_volume[channel]
						if   volume >= 0   and volume <= 64:  # Volume
							note.volume = volume * 4 + (volume & 3)
						elif volume >= 65  and volume <= 74:  # Fine volume up
							value = volume - 65
							effects.append(("D", (value << 4) | 0x0F)) # DxF
						elif volume >= 75  and volume <= 84:  # Fine volume down
							value = volume - 75
							effects.append(("D", value | 0xF0)) # DFy
						elif volume >= 85  and volume <= 94:  # Volume slide up
							value = volume - 85
							effects.append(("D", value << 4)) #Dx0
						elif volume >= 95  and volume <= 104: # Volume slide down
							value = volume - 95
							effects.append(("D", value)) # D0y
						elif volume >= 105 and volume <= 114: # Pitch slide down
							value = volume - 105
							effects.append(("E", value * 4))
						elif volume >= 115 and volume <= 124: # Pitch slide up
							value = volume - 115
							effects.append(("F", value * 4))
						elif volume >= 128 and volume <= 192: # Pan
							value = volume - 128 # -32L (0) to 0 (32) to 32R (64)
							effects.append(("X", value * 4)) # 32R (64) will become 128R (256), outside the byte range
						elif volume >= 193 and volume <= 202: # Portamento to note
							value = volume - 193
							effects.append(("G", (0x00, 0x01, 0x04, 0x08, 0x10, 0x20, 0x40, 0x60, 0x80, 0xFF)[value]))
						elif volume >= 203 and volume <= 212: # Vibrato depth (keep the same vibrato speed and only change the depth)
							value = volume - 203
							effects.append(("H", value)) # 0 for speed, so it will be "continue"
					else:
						note.volume = 255

					if mask_variable & 0x88: # Effect
						effect_id    = (last_effect[channel] & 255)
						if effect_id == 0 or effect_id > 0x1C:
							print("Invalid effect ID:", effect_id)
						else:
							effect_char  = IT_EFFECT_CHARS[effect_id - 1]
							effect_value = last_effect[channel] >> 8
							effects.append((effect_char, effect_value))

					for effect_char, effect_value in effects:
						if effect_char == "A": # Set Speed: Sets the module Speed (ticks per row)
							note.effects.append((0x09, effect_value))
						elif effect_char == "B": # Jump to different pattern
							note.effects.append((0x0B, effect_value))
						elif effect_char == "C": # Pattern Break: Jumps to row xx of the next pattern in the Order List. 
							note.effects.append((0x0D, effect_value))
						elif effect_char in ("D", "K", "L"): # Volume slide or fine volume slide
							if effect_value == 0 or (effect_value & 0xF0) == 0 or (effect_value & 0x0F) == 0:
								note.effects.append((0x0A, effect_value))
								# TODO: Figure out if it actually goes up or down at the same rate as Furnace
							elif (effect_value & 0xF0) == 0xF0: # Fine decrease
								note.effects.append((0xF9, effect_value & 15))
							elif (effect_value & 0x0F) == 0x0F: # Fine increase
								note.effects.append((0xF8, effect_value >> 4))
							else:
								print("Invalid volume slide %x" % effect_value)

							if effect_char == "K":
								note.effects.append((0x04, 0)) # Continue vibrato
							elif effect_char == "L":
								note.effects.append((0x03, 0)) # Continue portamento
						elif effect_char == "E": # Portamento Down or Fine Portamento Down or Extra Fine Portamento Down  
							if (effect_value & 0xF0) == 0xF0: # Fine: Only apply it on first tick of row, don't slide. Repeat it if E00 is used.
								note.effects.append((0xf2, effect_value/2)) # Single tick pitch down
							elif (effect_value & 0xF0) == 0xE0: # Extra fine: Four times the precision, but slide like normal
								note.effects.append((0x02, effect_value/2))
							else:
								note.effects.append((0x02, effect_value*2))
						elif effect_char == "F": # Portamento Up or Fine Portamento Up or Extra Fine Portamento  
							note.effects.append((0x01, effect_value*2))
							if (effect_value & 0xF0) == 0xF0: # Fine: Only apply it on first tick of row, don't slide. Repeat it if F00 is used.
								note.effects.append((0xf1, effect_value/2)) # Single tick pitch up
							elif (effect_value & 0xF0) == 0xE0: # Extra fine: Four times the precision, but slide like normal
								note.effects.append((0x01, effect_value/2))
							else:
								note.effects.append((0x01, effect_value*2))
						elif effect_char == "G": # Tone Portamento: Slides the pitch of the previous note towards the current note by xx units on every tick of the row except the first. 
							note.effects.append((0x03, effect_value))
						elif effect_char == "H": # Vibrato: Executes vibrato with speed x and depth y on the current note. 
							note.effects.append((0x04, effect_value))
						elif effect_char == "J": # Arpeggio
							note.effects.append((0x00, effect_value))
						elif effect_char == "P": # Pan slide
							note.effects.append((0x83, effect_value))
							if (effect_value & 0xF0) == 0xF0 or (effect_value & 0x0F) == 0x0F:
								print("Fine pan slide not supported")
						elif effect_char == "R": # Tremolo
							note.effects.append((0x07, effect_value))
						elif effect_char == "S" and (effect_value & 0xF0 == 0x80): # Panning; 8L to 1L, then 1R to 8R
							value = effect_value & 0xF
							if value >= 0 and value <= 0x7:
								note.effects.append((0x80, effect_value*16))
							else:
								note.effects.append((0x80, 0x80 + (effect_value+1)*16))
						elif effect_char == "S" and (effect_value & 0xF0 == 0xC0): # Note cut
							if effect_value == 0:
								effect_value = 1
							note.effects.append((0xEC, effect_value))
						elif effect_char == "S" and (effect_value & 0xF0 == 0xD0): # Note delay
							if effect_value == 0:
								effect_value = 1
							note.effects.append((0xED, effect_value))
						elif effect_char == "T" and effect_value >= 0x20: # Set Tempo: Sets the module Tempo if xx is greater than or equal to 20h.
							note.effects.append((0xF0, effect_value))
						elif effect_char == "X": # Set Panning
							note.effects.append((0x80, effect_value))
						elif effect_char == "Y": # Panbrello
							note.effects.append((0x84, effect_value))
						else:
							note.it_effect = (effect_char, effect_value)

					# Write the note
					if channel <= CHANNELS:
						channel_patterns[channel].rows[row_number] = note

		if not self.use_instruments:
			self.tracker_instruments = self.tracker_samples
			for instrument in self.tracker_instruments:
				tad_instrument = TerrificInstrument(instrument)
				tad_instrument.tracker_sample = instrument.tracker_sample
				tad_instrument.tracker_file = self
				tad_instrument.use_shortened_name = True
				self.tad_instruments.append(tad_instrument)
				instrument.tad_instrument = tad_instrument
		else:
			for instrument in self.tracker_instruments:
				if instrument.become_tad_sample:
					id_to_sample = {}

					for note, sample_to_play in instrument.tracker_sample_number_for_note.items():
						if sample_to_play in id_to_sample:
							tad_sample = id_to_sample[sample_to_play]
						else:
							tad_sample = TerrificSample(instrument)
							tad_sample.tracker_sample = sample_to_play
							tad_sample.tracker_file = self
							self.tad_samples.append(tad_sample)
							id_to_sample[sample_to_play] = tad_sample
						instrument.tad_sample_for_note[note] = tad_sample
					if len(id_to_sample) == 1:
						for _ in id_to_sample.values():
							_.use_shortened_name = True
							break
				else:
					id_to_instrument = {}

					for note, sample_to_play in instrument.tracker_sample_number_for_note.items():
						if sample_to_play in id_to_instrument:
							tad_instrument = id_to_instrument[sample_to_play]
						else:
							tad_instrument = TerrificInstrument(instrument)
							tad_instrument.tracker_sample = sample_to_play
							tad_instrument.tracker_file = self
							self.tad_instruments.append(tad_instrument)
							id_to_instrument[sample_to_play] = tad_instrument
						instrument.tad_instrument_for_note[note] = tad_instrument
					if len(id_to_instrument) == 1:
						for _ in id_to_instrument.values():
							_.use_shortened_name = True
							break

		#print(song.patterns[0][0].rows)

it_file = ImpulseTrackerFile(args.filename)

dump_folder = args.dump_samples or args.project_folder
if dump_folder:
	os.makedirs(dump_folder, exist_ok=True)

	wavs = glob.glob(os.path.join(dump_folder, '*.wav'))
	for filename in wavs:
		wav_basename = os.path.basename(filename)
		if len(wav_basename) > 4 and wav_basename[0:2].isdigit() and wav_basename[2] == " " and wav_basename[3] == "-":
			os.remove(filename)

	xmodits.dump(args.filename, dump_folder, index_raw=True)
if args.project_folder:
	os.makedirs(args.project_folder, exist_ok=True)

	mml_path = os.path.join(args.project_folder, "song.mml")
	mml_text = it_file.song.convert_to_tad(impulse_tracker = True)
	with open(mml_path, 'w') as f:
		f.write(mml_text)

	terrificaudio_path = os.path.join(args.project_folder, "project.terrificaudio")
	project = {
		"_about": {
			"file_type": "Terrific Audio Driver project file",
			"version": "0.1.1"
		},
		"instruments": [],
		"samples": [],
		"default_sfx_flags": {"one_channel": True, "interruptible": True},
		"high_priority_sound_effects": [],
		"sound_effects": [],
		"low_priority_sound_effects": [],
		"sound_effect_file": "sound-effects.txt",
		"songs": [{"name": it_file.song.name, "source": "song.mml"}]
	}

	# Write the instruments
	wavs = glob.glob(os.path.join(args.project_folder, '*.wav'))
	for instrument in it_file.tad_instruments:
		if not instrument.is_used and not args.keep_all_instruments:
			continue
		d = instrument.to_dict(wavs)
		if d != None:
			project["instruments"].append(d)
	for sample in it_file.tad_samples:
		if not sample.is_used and not args.keep_all_instruments:
			continue
		d = sample.to_dict(wavs)
		if d != None:
			project["samples"].append(d)

	# Write the final project file
	with open(terrificaudio_path, 'w') as f:
		json.dump(project, f, indent=2)

	sfx_path = os.path.join(args.project_folder, "sound-effects.txt")
	if not os.path.exists(sfx_path):
		f = open(sfx_path, "w")
		f.close()

if not args.project_folder:
	print(it_file.song.convert_to_tad(impulse_tracker = True))
