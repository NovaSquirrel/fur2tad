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
import zlib, io, struct, math, sys
from compress_mml import compress_mml
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
	return "o" + str(octave) + notes[note]

def read_string(stream):
	out = b''
	while True:
		c = stream.read(1)
		if c == b'\0':
			return out.decode()
		out += c

def token_is_note(token):
	return token.startswith("o")

def bytes_to_int(b, order="little", signed=False):
	return int.from_bytes(b, byteorder=order, signed=signed)

def bytes_to_float(b):
	return struct.unpack('f', b)[0]

possible_timer_milliseconds = [(_, _*0.125) for _ in range(64, 256+1)]
cached_timer_and_multiplier = {}
def find_timer_and_multiplier_for_tempo_and_speed(ticks_per_second, ticks_per_row):
	if (ticks_per_second, ticks_per_row) in cached_timer_and_multiplier:
		return cached_timer_and_multiplier[(ticks_per_second, ticks_per_row)]
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
			best_multiply = int(integer_part)
	cached_timer_and_multiplier[(ticks_per_second, ticks_per_row)] = (best_timer, best_multiply)
	return (best_timer, best_multiply)

def any_effects_are_volume_slide(note):
	return any(lambda x:effect[0] in (0x0A, 0xFA, 0xF3, 0xF4, 0xFA) for effect in note.effects)

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
		if t != None and v == None:
			v = 0
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

	song.empty = empty_pattern
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
		self.rows = []

	# Convert a pattern to MML without attempting to do any compression
	def convert_to_tad(self, song, speed_at_each_row, loop_point):
		out = []

		# Utilities
		def apply_legato():
			if out[-1].startswith("r"): # Rest
				out[-1] = "w" + out[-1][1:] # If there's a rest before this, turn it into a wait
				return
			for index in range(len(out)-1, -1, -1): # Otherwise, find the most recent note
				token = out[index]
				if token_is_note(token):
					if not token.endswith("&"):
						out[index] += "&"
					return

		def find_next_note_with(condition, wrap_around=False):
			search_index = row_index + 1
			while True:
				if search_index == row_index:
					return None
				if condition(self.rows[search_index]):
					return search_index
				search_index += 1
				if search_index >= len(self.rows):
					if wrap_around:
						search_index = loop_point
					else:
						return None

		def count_rows_until_note_with(condition):
			row_count = 0
			search_index = row_index + 1
			while True:
				if search_index == row_index:
					return None
				if condition(self.rows[search_index]):
					return row_count
				search_index += 1
				row_count += 1
				if search_index >= len(self.rows):
					search_index = loop_point

		def row_count_to_tad_ticks(row_count):
			total_ticks = 0
			check_index = row_index
			for _ in range(row_count):
				tad_timer_value, tad_ticks_per_row = find_timer_and_multiplier_for_tempo_and_speed(speed_at_each_row[check_index][0], speed_at_each_row[check_index][1])
				total_ticks += tad_ticks_per_row
				check_index += 1
				if check_index >= len(self.rows):
					check_index = loop_point
			return total_ticks

		def row_count_to_furnace_ticks(row_count):
			total_ticks = 0
			check_index = row_index
			for _ in range(row_count):
				total_ticks += speed_at_each_row[check_index][1]
				check_index += 1
				if check_index >= len(self.rows):
					check_index = loop_point
			return total_ticks

		# Variables to track
		row_index = 0

		current_instrument = None
		current_volume = None

		# Furnace state
		legato = False

		while row_index < len(self.rows):
			note = self.rows[row_index]

			# Find next note
			next_index = find_next_note_with(lambda _:not _.is_empty())
			if loop_point:
				next_note = self.rows[next_index if next_index != None else loop_point]
			else:
				next_note = self.rows[next_index] if next_index != None else None
			if next_index == None:
				next_index = len(self.rows)
			duration = next_index - row_index

			tad_timer_value, tad_ticks_per_row = find_timer_and_multiplier_for_tempo_and_speed(speed_at_each_row[row_index][0], speed_at_each_row[row_index][1])
			duration_in_ticks = row_count_to_tad_ticks(duration)

			if ("loop", None) in note.effects:
				out.append("L")

			# Write any instrument changes
			if note.instrument != current_instrument and note.instrument != None:
				current_instrument = note.instrument
				out.append("@%s" % song.furnace_file.instruments[current_instrument].name)

			# Write any volume changes
			if note.volume != current_volume and note.volume != None:
				current_volume = note.volume
				out.append("V%d" % current_volume)

			# Effects
			for effect_type, effect_value in note.effects:
				if effect_type in (0x0A, 0xFA, 0xF3, 0xF4): # Volume slide up/down
					if effect_value != 0:
						slide_amount = 0
						if effect_type in (0x0A, 0xFA):
							if effect_value & 0x0F == 0:
								slide_amount = effect_value >> 4
							elif effect_value & 0xF0 == 0:
								slide_amount = -effect_value
						elif effect_type == 0xF3:
							slide_amount = effect_value / 64
						elif effect_type == 0xF4:
							slide_amount = -(effect_value / 64)
						if effect_type == 0xFA:
							slide_amount *= 4

						if slide_amount:
							slide_rows = count_rows_until_note_with(any_effects_are_volume_slide)
							furnace_ticks = row_count_to_furnace_ticks(slide_rows)
							tad_ticks = row_count_to_tad_ticks(slide_rows)
							total_slide_amount = round(furnace_ticks * (slide_amount / 2))
							if abs(total_slide_amount) > 255:
								total_slide_amount = 255 if total_slide_amount > 0 else -255
							if tad_ticks > 256:
								print("Volume slide at %d took too long" % row_index)
								tad_ticks = 256
							if slide_rows != None:
								out.append("Vs%s%d,%d" % ("+" if total_slide_amount>=0 else "", total_slide_amount, tad_ticks))
				elif effect_type == 0x11: # Toggle noise
					noise_mode = bool(effect_value) # TODO
				elif effect_type == 0x12: # Echo
					out.append("E1" if effect_value else "E0")
				elif effect_type == 0x13: # Pitch modulation
					out.append("PM" if effect_value else "PM0")
				elif effect_type == 0x14: # Invert
					if effect_value == 0:
						out.append("i0")
					else:
						out.append("i" + ("L" if effect_value & 0xF0 else "") + ("R" if effect_value & 0x0F else ""))
				elif effect_type == 0x1D: # Noise frequency
					noise_frequency = effect_value & 31 # TODO
				elif effect_type == 0x80: # Set pan
					out.append("p%d" % int(effect_value / 255 * 128))					
				elif effect_type == 0xEA: # Legato
					legato = bool(effect_value)
				elif effect_type == 0xF8: # Single tick volume up
					out.append("V+%d" % (effect_value*2))
				elif effect_type == 0xF9: # Single tick volume down
					out.append("V-%d" % (effect_value*2))

			# Write the note itself
			if (note.note == None or note.note == NoteValue.OFF) and next_note and next_note.note and (next_note.note == NoteValue.OFF or (next_note.note >= NoteValue.FIRST and next_note.note <= NoteValue.LAST)): # The next non-empty row is either a note cut or a note
				out.append("r%%%d" % duration_in_ticks)
			elif note.note != None and note.note >= NoteValue.FIRST and note.note <= NoteValue.LAST:
				if legato: 
					apply_legato()
				note_name = note_name_from_index(note.note)
				if not next_note or next_note.note != None:
					out.append("%s%%%d" % (note_name, duration_in_ticks))
				else:
					out.append("%s%%%d&" % (note_name, duration_in_ticks))
			else:
				out.append("w%%%d" % duration_in_ticks)
			row_index = next_index
		if legato:
			apply_legato()
	
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
		self.empty_patterns = set()                          # each entry is (channel, pattern_id)

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
		tad_timer_value, tad_ticks_per_row = find_timer_and_multiplier_for_tempo_and_speed(self.ticks_per_second, self.speed1)
		out += "#Timer %d\n" % tad_timer_value

		out += "\n"

		# Define the instruments
		out += "; Instrument definitions\n"
		for instrument_index in self.instruments_used:
			instrument = self.furnace_file.instruments[instrument_index]
			out += "@%s %s\n" % (instrument.name, instrument.name)

		out += "\n"

		# Convert the orders and patterns into one long pattern per channel, plus information about loop points and speeds
		combined_patterns = [FurnacePattern() for _ in range(CHANNELS)]
		combined_pattern_offset_for_order_row = []
		speed_at_each_row = []
		loop_point = 0

		order_index = 0  # Order row
		row_index = 0    # Pattern row
		new_order = True
		current_ticks_per_second = song.ticks_per_second
		current_ticks_per_row = song.speed1
		stop_order_processing = False
		while order_index < song.orders_length:
			if new_order:
				channel_patterns = [song.patterns[channel][song.orders[channel][order_index]] for channel in range(CHANNELS)]
				combined_pattern_offset_for_order_row.append(len(combined_patterns[0].rows))
				new_order = False

			# Check on what each channel is doing on this row
			next_row_index = row_index + 1
			for channel in range(CHANNELS):
				note = channel_patterns[channel].rows[row_index]
				combined_patterns[channel].rows.append(note)
				for effect_type, effect_value in note.effects:
					if effect_type == 0x0D: # Jump to next pattern
						order_index += 1
						next_row_index = effect_value
						new_order = True
					elif effect_type == 0x0B: # Jump to order row
						if effect_value > order_index: # Skip forward
							order_index = effect_value
							next_row_index = 0
							new_order = True
						else: # If jumping backwards, set loop point
							loop_point = combined_pattern_offset_for_order_row[effect_value]
							stop_order_processing = True
					elif effect_type == 0xFF: # Don't loop
						loop_point = None
						stop_order_processing = True
					elif effect_type == 0x09: # Set ticks-per-row (speed 1)
						current_ticks_per_row = effect_value
					elif effect_type == 0xF0: # Set BPM
						current_ticks_per_second = effect_value / 2.5
			speed_at_each_row.append((current_ticks_per_second, current_ticks_per_row))
			if stop_order_processing:
				break
			# Onto the next row, and potentially the next order row
			row_index = next_row_index
			if row_index >= song.pattern_length:
				row_index = 0
				order_index += 1
				new_order = True
		# Insert loop point as a fake effect
		if loop_point != None:
			for channel in range(CHANNELS):
				combined_patterns[channel].rows[loop_point].effects.append(("loop",None))

		# Now we have one long pattern for each channel
		mml_sequences = {"ABCDEFGH"[channel]:pattern.convert_to_tad(self, speed_at_each_row, loop_point) for channel,pattern in enumerate(combined_patterns)}
		for k in "ABCDEFGH":
			compress_mml(k, mml_sequences)
		for k,v in mml_sequences.items():
			if any(not _.startswith("w%") and _ != "L" for _ in v): # Sequence must not consist entirely of waits
				out += k + " " + " ".join(v) + "\n"

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

if len(sys.argv) < 1:
	sys.exit("Please provide a filename")
f = FurnaceFile(sys.argv[1])
for song in f.songs:
	print(song.convert_to_tad())
