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

# https://github.com/tildearrow/furnace/blob/master/papers/format.md
import zlib, io, struct, math
from enum import IntEnum
CHANNELS = 8

# -------------------------------------------------------------------
# Utilities

class NoteValue(IntEnum):
	FIRST = 0
	LAST = 179
	OFF = 180
	RELEASE = 181
	MACRO_RELEASE = 182

notes = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"]
def note_name_from_index(i):
	note   = i % 12
	octave = i // 12 - 5
	return notes[note] + str(octave)

def read_string(stream):
	out = b''
	while True:
		c = stream.read(1)
		if c == b'\0':
			return out.decode()
		out += c

def bytes_to_int(b, order="little", signed=False):
	return int.from_bytes(b, byteorder=order, signed=signed)

def bytes_to_float(b):
	return struct.unpack('f', b)[0]

possible_timer_milliseconds = [(_, _*0.125) for _ in range(64, 256+1)]
def find_timer_and_multiplier_for_tempo_and_speed(ticks_per_second, ticks_per_row):
	milliseconds_per_tempo_tick = 1 / ticks_per_second * 1000

	row_milliseconds = milliseconds_per_tempo_tick * ticks_per_row # Actual duration of each row

	best_timer     = None
	best_multiply  = None
	lowest_error   = None

	for timer_value, timer_ms in possible_timer_milliseconds:
		fractional_part, integer_part = math.modf(row_milliseconds / timer_ms)
		milliseconds_with_this_timer_option = timer_ms * integer_part
		error = abs(row_milliseconds - milliseconds_with_this_timer_option)
		if lowest_error == None or lowest_error > error:
			lowest_error  = error
			best_timer    = timer_value
			best_multiply = integer_part
	return (best_timer, int(best_multiply))

# -------------------------------------------------------------------

block_handlers = {}
def block_handler(name):
	def decorator(f):
		block_handlers[name] = f
	return decorator

@block_handler("INFO")
def FurnaceInfoBlock(furnace_file, name, data, s):
	song = FurnaceSong(furnace_file, s)
	furnace_file.instrument_count     = bytes_to_int(s.read(2))
	furnace_file.wavetable_count      = bytes_to_int(s.read(2))
	furnace_file.sample_count         = bytes_to_int(s.read(2))
	furnace_file.global_pattern_count = bytes_to_int(s.read(4))

	chips = s.read(32) # Should be 0x87 and then a bunch of zeros
	assert chips[0] == 0x87
	assert chips[1] == 0
	chip_volumes = s.read(32)
	chip_panning = s.read(32)
	chip_flag_pointers = s.read(128)
	song.name = read_string(s)
	song.author = read_string(s)
	furnace_file.a4_tuning = bytes_to_float(s.read(4))

	furnace_file.limit_slides                            = bytes_to_int(s.read(1))
	furnace_file.linear_pitch                            = bytes_to_int(s.read(1))
	furnace_file.loop_modality                           = bytes_to_int(s.read(1))
	furnace_file.proper_noise_layout                     = bytes_to_int(s.read(1))
	furnace_file.wave_duty_is_volume                     = bytes_to_int(s.read(1))
	furnace_file.reset_macro_on_porta                    = bytes_to_int(s.read(1))
	furnace_file.legacy_volume_slides                    = bytes_to_int(s.read(1))
	furnace_file.compatible_arpeggio                     = bytes_to_int(s.read(1))
	furnace_file.note_off_resets_slides                  = bytes_to_int(s.read(1))
	furnace_file.target_resets_slides                    = bytes_to_int(s.read(1))
	furnace_file.arpeggio_inhibits_portamento            = bytes_to_int(s.read(1))
	furnace_file.wack_algorithm_macro                    = bytes_to_int(s.read(1))
	furnace_file.broken_shortcut_slides                  = bytes_to_int(s.read(1))
	furnace_file.ignore_duplicate_slides                 = bytes_to_int(s.read(1))
	furnace_file.stop_portamento_on_note_off             = bytes_to_int(s.read(1))
	furnace_file.continuous_vibrato                      = bytes_to_int(s.read(1))
	furnace_file.broken_DAC_mode                         = bytes_to_int(s.read(1))
	furnace_file.one_tick_cut                            = bytes_to_int(s.read(1))
	furnace_file.instrument_change_allowed_during_porta  = bytes_to_int(s.read(1))
	furnace_file.reset_note_base_on_arpeggio_effect_stop = bytes_to_int(s.read(1))

	pointers_to_instruments = s.read(4*furnace_file.instrument_count)
	pointers_to_wavetables  = s.read(4*furnace_file.wavetable_count)
	pointers_to_samples     = s.read(4*furnace_file.sample_count)
	pointers_to_patterns    = s.read(4*furnace_file.global_pattern_count)

	song.read_orders(s)
	song.comment = read_string(s)
	
	furnace_file.master_volume = bytes_to_float(s.read(4))

	# Probably won't need to care about these?
	furnace_file.broken_speed_selection                              = bytes_to_int(s.read(1))
	furnace_file.no_slides_on_first_tick                            = bytes_to_int(s.read(1))
	furnace_file.next_row_reset_arp_pos                             = bytes_to_int(s.read(1))
	furnace_file.ignore_jump_at_end                                 = bytes_to_int(s.read(1))
	furnace_file.buggy_portamento_after_slide                       = bytes_to_int(s.read(1))
	furnace_file.new_ins_affects_envelope                           = bytes_to_int(s.read(1))
	furnace_file.ExtCh_channel_state_is_shared                      = bytes_to_int(s.read(1))
	furnace_file.ignore_DAC_mode_change_outside_of_intended_channel = bytes_to_int(s.read(1))
	furnace_file.E1xy_and_E2xy_also_take_priority_over_lide00       = bytes_to_int(s.read(1))
	furnace_file.new_Sega_PCM                                       = bytes_to_int(s.read(1))
	furnace_file.weird_f_num_block_based_chip_pitch_slides          = bytes_to_int(s.read(1))
	furnace_file.SN_duty_macro_always_resets_phase                  = bytes_to_int(s.read(1))
	furnace_file.pitch_macro_is_linear                              = bytes_to_int(s.read(1))
	furnace_file.pitch_slide_speed_in_full_linear_pitch_mode        = bytes_to_int(s.read(1))
	furnace_file.old_octave_boundary_behavior                       = bytes_to_int(s.read(1))
	furnace_file.disabl_OPN2_DAC_volume_control                     = bytes_to_int(s.read(1))
	furnace_file.new_volume_scaling_strategy                        = bytes_to_int(s.read(1))
	furnace_file.volume_macro_still_applies_after_end               = bytes_to_int(s.read(1))
	furnace_file.broken_outVol                                      = bytes_to_int(s.read(1))
	furnace_file.E1xy_and_E2xy_stop_on_same_note                    = bytes_to_int(s.read(1))
	furnace_file.broken_initial_position_of_porta_after_arp         = bytes_to_int(s.read(1))
	furnace_file.SN_periods_under_8_are_treated_as_1                = bytes_to_int(s.read(1))
	furnace_file.cut_delay_effect_policy                            = bytes_to_int(s.read(1))
	furnace_file._0B_0D_effect_treatment                            = bytes_to_int(s.read(1))
	furnace_file.automatic_system_name_detection                    = bytes_to_int(s.read(1))
	furnace_file.disable_sample_macro                               = bytes_to_int(s.read(1))
	furnace_file.broken_outVol_episode_2                            = bytes_to_int(s.read(1))
	furnace_file.old_arpeggio_strategy                              = bytes_to_int(s.read(1))

	song.virtual_tempo_numerator   = bytes_to_int(s.read(2))
	song.virtual_tempo_denominator = bytes_to_int(s.read(2))

	# Don't bother with fields past this point for now, though that means I don't have the speed pattern

@block_handler("SONG")
def FurnaceSubsongBlock(furnace_file, name, data, s):
	song = FurnaceSong(furnace_file, s)
	song.virtual_tempo_numerator   = bytes_to_int(s.read(2))
	song.virtual_tempo_denominator = bytes_to_int(s.read(2))
	song.name    = read_string(s)
	song.comment = read_string(s)
	song.read_orders(s)
	song.speed_pattern_length      = bytes_to_int(s.read(1))
	song.speed_pattern             = bytes_to_int(s.read(16))
	
@block_handler("ADIR")
def FurnaceAssetDirectoryBlock(furnace_file, name, data, s):
	pass
	#print("adir")
	#print(data)

@block_handler("SMP2")
def FurnaceSampleBlock(furnace_file, name, data, s):
	sample = FurnaceSample()
	furnace_file.samples.append(sample)

	sample.name = read_string(s)
	sample.length             = bytes_to_int(s.read(4))
	sample.compatibility_rate = bytes_to_int(s.read(4))
	sample.c4_rate            = bytes_to_int(s.read(4)) # In Hz
	sample.depth              = bytes_to_int(s.read(1)) # 9 is BRR
	sample.loop_direction     = bytes_to_int(s.read(1))
	sample.flags              = bytes_to_int(s.read(1))
	sample.flags2             = bytes_to_int(s.read(1))
	sample.loop_start         = bytes_to_int(s.read(4), signed=True)
	sample.loop_end           = bytes_to_int(s.read(4), signed=True)
	sample.data               = s.read(sample.length)

@block_handler("INS2")
def FurnaceInstrumentBlock(furnace_file, name, data, s):
	format_version = bytes_to_int(s.read(2))
	instrument_type = bytes_to_int(s.read(2))
	assert instrument_type == 29 # SNES

	instrument = FurnaceInstrument()
	furnace_file.instruments.append(instrument)

	while True:
		feature = s.read(2)
		if len(feature) == 0 or feature == b'EN':
			break
		feature_size = bytes_to_int(s.read(2))
		feature_data = s.read(feature_size)
		#print(feature, feature_data)
		sf = io.BytesIO(feature_data)

		if feature == b'NA':
			instrument.name = read_string(sf)
		elif feature == b'SM':
			instrument.initial_sample = bytes_to_int(sf.read(2))
			b = bytes_to_int(sf.read(1)) # flags
			instrument.use_sample_map = bool(b&1)
			instrument.use_sample     = bool(b&2)
			instrument.use_wave       = bool(b&4)
			instrument.waveform_length = bytes_to_int(sf.read(1))
			if instrument.use_sample_map:
				instrument.sample_map = []
				for i in range(120):
					note_to_play   = bytes_to_int(sf.read(2))
					sample_to_play = bytes_to_int(sf.read(2))
					instrument.sample_map.append((note_to_play, sample_to_play))
		elif feature == b'SN':
			b = bytes_to_int(sf.read(1)) # attack/decay
			instrument.attack   = b & 15
			instrument.decay    = (b >> 4) & 15

			b = bytes_to_int(sf.read(1)) # sustain/release
			instrument.sustain  = b & 15
			instrument.release  = (b >> 4) & 15 # Actually sustain rate?

			b = bytes_to_int(sf.read(1)) # flags
			instrument.gain_mode = b & 7
			instrument.make_gain_effective = bool(b & 8)
			instrument.envelope_on         = bool(b & 16)

			instrument.gain = sf.read(1) # gain

			b = bytes_to_int(sf.read(1)) # decay 2/sustain mode
			instrument.decay2 = b & 31
			instrument.sustain_mode = (b >> 5) & 3

			# TODO: Figure out what to do with these fields
		else:
			pass
			#print("Unrecognized instrument feature", feature)

@block_handler("PATN")
def FurnacePatternBlock(furnace_file, name, data, s):
	song          = furnace_file.songs[bytes_to_int(s.read(1))]
	channel       = bytes_to_int(s.read(1))
	pattern_index = bytes_to_int(s.read(2))
	pattern_name  = read_string(s)
	pattern       = FurnacePattern() # Create storage for pattern
	empty_pattern = True

	def read_effect(note, have_type, have_value):
		t = bytes_to_int(s.read(1)) if have_type else None
		v = bytes_to_int(s.read(1)) if have_value else None
		if have_type or have_value:
			note.effects.append((t, v))

	pattern.rows  = [FurnaceNote() for _ in range(song.pattern_length)]
	index = 0
	while index < song.pattern_length:
		b = bytes_to_int(s.read(1))
		if b == 0xFF:
			break
		if b & 128:
			index += 2 + (b & 127)
		else:
			empty_pattern = False
			note = pattern.rows[index]
			if b & 1:
				note.note = bytes_to_int(s.read(1))
			if b & 2:
				note.instrument = bytes_to_int(s.read(1))
				song.instruments_used.add(note.instrument)
			if b & 4:
				note.volume = bytes_to_int(s.read(1))
			read_effect(note, b & 8, b & 16)
			if b & 32:
				e = s.read(1)
				read_effect(note, e & 1,  e & 2)
				read_effect(note, e & 4,  e & 8)
				read_effect(note, e & 16, e & 32)
				read_effect(note, e & 64, e & 128)
			if b & 64:
				e = s.read(1)
				read_effect(note, e & 1,  e & 2)
				read_effect(note, e & 4,  e & 8)
				read_effect(note, e & 16, e & 32)
				read_effect(note, e & 64, e & 128)
			index += 1

	# If this pattern is identical to a previous pattern, just store a reference to that pattern
	if empty_pattern:
		song.empty_patterns.add((channel, pattern_index))
		return
	for channel2 in range(CHANNELS):
		for k,v in song.patterns[channel2].items():
			if v == pattern:
				song.pattern_aliases[channel][pattern_index] = (channel2, k)
				return
	song.patterns[channel][pattern_index] = pattern

# -------------------------------------------------------------------

class FurnaceInstrument(object):
	def __init__(self):
		# Set defaults
		self.initial_sample = 0

class FurnaceSample(object):
	def __init__(self):
		pass

class FurnaceNote(object):
	def __init__(self):
		self.note       = None
		self.instrument = None
		self.volume     = None
		self.effects    = []
	def __repr__(self):
		return "%s %s %s %s" % (self.note, self.instrument, self.volume, self.effects)
	def __eq__(self, other):
		return self.note == other.note and self.instrument == other.instrument and self.volume == other.volume and self.effects == other.effects
	def is_empty(self):
		return self.note == None and self.instrument == None and self.volume == None and self.effects == []

class FurnacePattern(object):
	def __init__(self):
		pass

	def convert_to_tad(self, song, tad_ticks_per_row):
		out = []
		row_index = 0

		current_instrument = None
		current_volume = None

		while row_index < song.pattern_length:
			note = self.rows[row_index]

			# Find next note
			next_index = row_index + 1
			while next_index < song.pattern_length and self.rows[next_index].is_empty():
				next_index += 1
			next_note = self.rows[next_index] if next_index < song.pattern_length else None
			duration = next_index - row_index
			duration_in_ticks = duration * tad_ticks_per_row

			# Write any instrument changes
			if note.instrument != current_instrument and note.instrument != None:
				current_instrument = note.instrument
				out.append("set_instrument %s" % song.furnace_file.instruments[current_instrument].name)

			# Write any volume changes
			if note.volume != current_volume and note.volume != None:
				current_volume = note.volume
				out.append("set_volume %d" % current_volume)

			# Effects

			# Write the note itself
			if note.note == NoteValue.OFF or note.note == None:
				while duration_in_ticks > 0:
					out.append("wait %d" % min(256, duration_in_ticks))
					duration_in_ticks -= 256
			elif note.note >= NoteValue.FIRST and note.note <= NoteValue.LAST:
				note_name = note_name_from_index(note.note)
				ticks_for_play_note = min(256, duration_in_ticks) # play_note can only take a tick value up to 256 ticks
				if not next_note or next_note.note != None:
					if duration_in_ticks <= 256:
						out.append("play_note %s keyoff %s" % (note_name, duration_in_ticks))
					else:
						out.append("play_note %s no_keyoff %s" % (note_name, ticks_for_play_note))
						leftover = duration_in_ticks - ticks_for_play_note
						while leftover > 256:
							out.append("wait 256")
							leftover -= 256
						out.append("rest %d" % leftover)						
				else:
					out.append("play_note %s no_keyoff %s" % (note_name, ticks_for_play_note))
					leftover = duration_in_ticks - ticks_for_play_note
					while leftover > 0:
						out.append("wait %d" % min(256, leftover))
						leftover -= 256
			row_index = next_index

		return out
	def __eq__(self, other):
		return self.rows == other.rows

class FurnaceSong(object):
	def __init__(self, furnace_file, stream):
		self.furnace_file = furnace_file
		furnace_file.songs.append(self)

		# Parse the data at the start; this is common to both INFO and SONG
		self.time_base = bytes_to_int(stream.read(1))
		self.speed1 = bytes_to_int(stream.read(1))
		self.speed2 = bytes_to_int(stream.read(1))
		self.initial_arpeggio_time = bytes_to_int(stream.read(1))
		self.ticks_per_second = bytes_to_float(stream.read(4))
		self.pattern_length = bytes_to_int(stream.read(2))
		self.orders_length = bytes_to_int(stream.read(2))
		self.highlight_A = bytes_to_int(stream.read(1))
		self.highlight_B = bytes_to_int(stream.read(1))

		# Initialize
		self.instruments_used = set()
		self.patterns = [{} for _ in range(CHANNELS)]        # self.patterns[channel][pattern_id]
		self.pattern_aliases = [{} for _ in range(CHANNELS)] # self.pattern_aliases[channel][pattern_id] = (channel, pattern_id)
		self.empty_patterns = set()                          # each entry is (channel, pattern_id)

		# Calculate numbers used for note durations
		self.tad_timer_value, self.tad_ticks_per_row = find_timer_and_multiplier_for_tempo_and_speed(self.ticks_per_second, self.speed1)

	def read_orders(self, stream):
		self.orders              = []
		for i in range(CHANNELS):
			column = []
			for j in range(self.orders_length):
				column.append(bytes_to_int(stream.read(1)))
			self.orders.append(column)
		self.effect_column_count = stream.read(CHANNELS)
		self.channels_hidden     = stream.read(CHANNELS)
		self.channels_collapsed  = stream.read(CHANNELS)
		self.channel_names = []
		for i in range(CHANNELS):
			self.channel_names.append(read_string(stream))
		self.short_channel_names = []
		for i in range(CHANNELS):
			self.short_channel_names.append(read_string(stream))

	def convert_to_tad(self):
		out = ""

		if song.name:
			out += "#Title %s\n" % song.name
		if song.author:
			out += "#Composer %s\n" % song.author
		out += "#Timer %d\n" % song.tad_timer_value

		out += "\n"

		"""
		# Define the instruments
		out += "; Instrument definitions\n"
		for instrument_index in self.instruments_used:
			instrument = self.furnace_file.instruments[instrument_index]
			out += "@%s %s\n" % (instrument.name, instrument.name)

		out += "\n"
		"""

		out += "; Patterns\n"
		# Define the patterns
		for channel in range(CHANNELS):
			for k,v in self.patterns[channel].items():
				out += "!pattern_%d_%d \\asm {\n%s\n}\n\n" % (channel, k, " | ".join(v.convert_to_tad(self, self.tad_ticks_per_row)))

		out += "; Orders\n"

		# Orders
		for channel in range(CHANNELS):
			channel_out = []
			only_empty = True
			for row in song.orders[channel]:
				use_channel = channel
				use_pattern = song.orders[channel][row]
				if (use_channel, use_pattern) in song.empty_patterns:
					channel_out.append("w%%%d" % (self.pattern_length * self.tad_ticks_per_row))
					continue
				only_empty = False
				alias = song.pattern_aliases[channel].get(use_pattern)
				if alias != None:
					use_channel, use_pattern = alias
				channel_out.append("!pattern_%d_%d" % (use_channel, use_pattern))
			if not only_empty:
				out += "ABCDEFGH"[channel] + " " + " ".join(channel_out) + "\n"

		return out

class FurnaceFile(object):
	def __init__(self, filename):
		# Storage for things defined in the file
		self.songs = []
		self.instruments = []
		self.samples = []
		self.instruments_used = set()

		# Open the file
		f = open(filename, "rb")
		self.bytes = f.read()
		f.close()
		if self.bytes[0] == 0x78: # zlib magic byte
			self.bytes = zlib.decompress(self.bytes)
		s = io.BytesIO(self.bytes) # Set it up as a stream
		
		header = s.read(32)
		if header[0:16] != b'-Furnace module-':
			raise Exception("Not a Furnace module")
		self.format_version = bytes_to_int(header[16:18])
		song_info_pointer = bytes_to_int(header[20:24])

		# Read and handle all of the blocks in the file
		s.seek(song_info_pointer)
		while True:
			block_name = s.read(4).decode()
			if len(block_name) == 0:
				break
			block_size = bytes_to_int(s.read(4))
			block_data = s.read(block_size)
			
			if block_name in block_handlers:
				block_handlers[block_name](self, block_name, block_data, io.BytesIO(block_data))
			else:
				print("Unrecognized block: ", block_name)

f = FurnaceFile("keyoff.fur")
#f = FurnaceFile("test.fur")
for song in f.songs:
	print(song.convert_to_tad())
