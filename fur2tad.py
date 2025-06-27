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
import zlib, io, struct, math, argparse, sys
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
	FIRST_VALID_TAD = 12*5
	LAST_VALID_TAD = 12*(5 + 6) + 11


notes = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"]
def note_name_from_index(i, offset):
	i      += offset
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
	return token.startswith("o") or token.startswith("{")

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
	actual_row_milliseconds = milliseconds_per_tempo_tick * ticks_per_row # Actual duration of each row

	if auto_timer_mode == "lowest_error":
		options = sorted(timer_and_multiplier_search(actual_row_milliseconds))
		best_timer = options[0][1]
		best_multiply = options[0][2]

	else: # low_error
		best_timer     = None
		best_multiply  = None
		lowest_error   = None

		for timer_value, timer_ms in possible_timer_milliseconds:
			fractional_part, integer_part = math.modf(actual_row_milliseconds / timer_ms)
			milliseconds_with_this_timer_option = timer_ms * integer_part
			error = abs(actual_row_milliseconds - milliseconds_with_this_timer_option)
			if lowest_error == None or lowest_error > error:
				lowest_error  = error
				best_timer    = timer_value
				best_multiply = int(integer_part)

	cached_timer_and_multiplier[(ticks_per_second, ticks_per_row)] = (best_timer, best_multiply)
	return (best_timer, best_multiply)

def timer_and_multiplier_search(actual_row_milliseconds, maximum_error=2):
	low_error_options = set() # Indexed by multiplier
	for timer_option in possible_timer_milliseconds:
		for multiply in range(1, 60):
			milliseconds_with_this_timer_option = timer_option[1] * multiply
			error = abs(actual_row_milliseconds - milliseconds_with_this_timer_option)
			if error < maximum_error:
				low_error_options.add((error, timer_option[0], multiply))
	return low_error_options

cached_timer_and_multipliers_for_speed_pattern = {}
def find_timer_and_multipliers_for_speed_pattern(ticks_per_second, speed_pattern):
	cached = cached_timer_and_multipliers_for_speed_pattern.get((ticks_per_second, tuple(speed_pattern)))
	if cached != None:
		return cached
	maximum_error = 2
	speeds_used = set(speed_pattern)
	milliseconds_per_tempo_tick = 1 / ticks_per_second * 1000

	while True:
		options_for_speeds = []
		for ticks_per_row in speeds_used:
			actual_row_milliseconds = milliseconds_per_tempo_tick * ticks_per_row
			options_for_speeds.append(timer_and_multiplier_search(actual_row_milliseconds, maximum_error=maximum_error))

		# Which timer values are available to all speed settings?
		available_timer_values = set.intersection(*[ {_[1] for _ in speed} for speed in options_for_speeds ])
		if len(available_timer_values) == 0:
			if maximum_error == 5:
				return None
			maximum_error = 5
			continue

		# Decide on which timer value to use
		best_timer_value = None
		best_error = None
		options_for_speeds = [{_[1]:_ for _ in speed} for speed in options_for_speeds]
		for timer_value in sorted(available_timer_values):
			total_error = sum([_[timer_value][0] for _ in options_for_speeds])
			if best_error == None or best_error > total_error:
				best_error = total_error
				best_timer_value = timer_value

		multiplier_for_speed_value = {_[0]:_[1][best_timer_value][2] for _ in zip(speeds_used, options_for_speeds)}
		out = [multiplier_for_speed_value[_] for _ in speed_pattern]
		cached_timer_and_multipliers_for_speed_pattern[(ticks_per_second, tuple(speed_pattern))] = (best_timer_value, out)
		return (best_timer_value, out)

def furnace_ticks_to_tad_ticks(furnace_ticks, furnace_ticks_per_second, tad_timer):
	milliseconds_per_tempo_tick = 1 / furnace_ticks_per_second * 1000
	time = milliseconds_per_tempo_tick * furnace_ticks
	return round(time / (tad_timer * 0.125))

def any_effects_are_volume_slide(note):
	return any(lambda x:effect[0] in (0x0A, 0xFA, 0xF3, 0xF4, 0xFA) for effect in note.effects)
def any_effects_are_pitch_sweep(note):
	return any(lambda x:effect[0] in (0x01, 0x02) for effect in note.effects)

def convert_volume(furnace_volume):
	if furnace_volume == None:
		return None
	if furnace_volume == 0:
		return 0
	return furnace_volume*2 + (furnace_volume & 1)

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

	read_string(s) # First subsong name
	read_string(s) # First subsong comment
	number_of_subsongs = bytes_to_int(s.read(1))
	s.read(3)
	s.read(4 * number_of_subsongs) # Subsong pointers
	read_string(s) # System name
	read_string(s) # Album/category/game name
	read_string(s) # Song name (Japanese)
	read_string(s) # Song author (Japanese)
	read_string(s) # System name (Japanese)
	read_string(s) # Album/category/game name(Japanese)
	s.read(4 * 3)  # Extra chip output settings
	patchbay_count = bytes_to_int(s.read(4))
	s.read(4 * patchbay_count)
	s.read(1)      # Automatic patchbay
	s.read(8)      # Compatibility flags

	song.speed_pattern_length = bytes_to_int(s.read(1))
	song.speed_pattern        = list(s.read(16))[0:song.speed_pattern_length]

	furnace_file.groove_patterns = []
	number_of_groove_patterns = bytes_to_int(s.read(1))
	for _ in range(number_of_groove_patterns):
		groove_size = bytes_to_int(s.read(1))
		groove_pattern = list(s.read(16))[0:groove_size]
		furnace_file.groove_patterns.append(groove_pattern)

@block_handler("SONG")
def FurnaceSubsongBlock(furnace_file, name, data, s):
	song = FurnaceSong(furnace_file, s)
	song.virtual_tempo_numerator   = bytes_to_int(s.read(2))
	song.virtual_tempo_denominator = bytes_to_int(s.read(2))
	song.name    = read_string(s)
	song.comment = read_string(s)
	song.read_orders(s)

	song.speed_pattern_length = bytes_to_int(s.read(1))
	song.speed_pattern        = list(s.read(16))[0:song.speed_pattern_length]

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
			instrument.name = read_string(sf).replace(" ", "_")
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
		elif feature == b'MA':
			sf.read(2) # Macro data size
			while True:
				macro_code = sf.read(1)
				if len(macro_code) == 0:
					break
				if macro_code[0] == 255:
					break
				macro_length = bytes_to_int(sf.read(1))
				macro_loop = bytes_to_int(sf.read(1))
				macro_release = bytes_to_int(sf.read(1))
				macro_mode = bytes_to_int(sf.read(1))
				macro_open_type_word_size = bytes_to_int(sf.read(1))
				macro_delay = bytes_to_int(sf.read(1))
				macro_speed = bytes_to_int(sf.read(1))

				signed = True
				word_size = 1
				if macro_open_type_word_size & 0xC0 == 0x00:
					signed = False
				elif macro_open_type_word_size & 0xC0 == 0x40:
					word_size = 1
				elif macro_open_type_word_size & 0xC0 == 0x80:
					word_size = 2
				elif macro_open_type_word_size & 0xC0 == 0xC0:
					word_size = 4

				macro_data = []
				for _ in range(macro_length):
					macro_data.append(bytes_to_int(sf.read(word_size), signed=signed))

				if macro_code[0] == 1: # Arpeggio
					if args.ignore_arp_macro != True:
						instrument.semitone_offset = macro_data[-1]
				else:
					print("Unsupported macro type", macro_code[0])
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
			effect1, effect2 = None, None
			if b & 32:
				effect1 = bytes_to_int(s.read(1))
			if b & 64:
				effect2 = bytes_to_int(s.read(1))
			if b & 1:
				note.note = bytes_to_int(s.read(1))
			if b & 2:
				note.instrument = bytes_to_int(s.read(1))
				song.instruments_used.add(note.instrument)
			if b & 4:
				note.volume = bytes_to_int(s.read(1))
			read_effect(note, b & 8, b & 16)
			if effect1 != None:
				#read_effect(note, effect1 & 1,  effect1 & 2)
				read_effect(note, effect1 & 4,  effect1 & 8)
				read_effect(note, effect1 & 16, effect1 & 32)
				read_effect(note, effect1 & 64, effect1 & 128)
			if effect2 != None:
				read_effect(note, effect2 & 1,  effect2 & 2)
				read_effect(note, effect2 & 4,  effect2 & 8)
				read_effect(note, effect2 & 16, effect2 & 32)
				read_effect(note, effect2 & 64, effect2 & 128)
			index += 1

	song.empty = empty_pattern
	song.patterns[channel][pattern_index] = pattern

# -------------------------------------------------------------------

class FurnaceInstrument(object):
	def __init__(self):
		# Set defaults
		self.initial_sample = 0
		self.semitone_offset = 0

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
				if token_is_note(token) or token.startswith("N"):
					if token != "N-" and (not token.endswith("&")):
						out[index] += "&"
					return

		def add_rest(tad_ticks):
			if len(out):
				index = -1
				total_wait_amount = 0

				# Are there waits between the note and the rest that's being added?
				while True:
					if index < -len(out):
						out.append("r%%%d" % (tad_ticks))
						return
					if out[index].startswith("w"):
						total_wait_amount += int(out[index].split("%")[1])
						index -= 1
					else:
						break

				previous = out[index]
				if token_is_note(previous) and previous.endswith("&"):
					s = previous.rstrip("&").split("%")
					new_duration = int(s[1]) + tad_ticks + total_wait_amount
					s[1] = str(new_duration)
					out[index] = "%".join(s)
					if new_duration < 2: # 2 ticks are required for a key-off note
						out[index] += "&"

					# Clean up the waits that were combined together
					pop_amount = (-index)-1
					for i in range(0, pop_amount):
						out.pop()
					return
			out.append("r%%%d" % (tad_ticks))

		def find_next_note_with(condition, wrap_around=False):
			search_index = row_index + 1
			while True:
				if search_index >= len(self.rows):
					if wrap_around:
						search_index = loop_point
					else:
						return None
				if search_index == row_index:
					return None
				if condition(self.rows[search_index]):
					return search_index
				search_index += 1

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
				total_ticks += speed_at_each_row[check_index][3]
				check_index += 1
				if check_index >= len(self.rows):
					check_index = loop_point
					if loop_point == None:
						check_index = len(self.rows)-1 # Keep using the last row's speed I guess?
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
		arpeggio_enabled = False
		arpeggio_note1 = None
		arpeggio_note2 = None
		arpeggio_speed = 1
		most_recent_note = None
		pitch_slide_rate = None
		vibrato_range = 15
		portamento_speed = None
		portamento_from = None
		portamento_target = None
		noise_mode = False
		noise_frequency = 0
		already_wrote_loop = False

		while row_index < len(self.rows):
			previous_most_recent_note = most_recent_note
			note = self.rows[row_index]
			if note.note != None:
				most_recent_note = note.note

			# Find next note
			next_index = find_next_note_with(lambda _:not _.is_empty())
			if loop_point:
				next_note = self.rows[next_index if next_index != None else loop_point]
			else:
				next_note = self.rows[next_index] if next_index != None else None
			if next_index == None:
				next_index = len(self.rows)
			duration = next_index - row_index

			furnace_ticks_per_second, furnace_ticks_per_row, tad_timer_value, tad_ticks_per_row = speed_at_each_row[row_index]
			duration_in_tad_ticks = row_count_to_tad_ticks(duration)
			
			if ("loop", None) in note.effects and not already_wrote_loop:
				out.append("L")
				already_wrote_loop = True # TODO: Figure out why it's attempting to insert it multiple times?

			# Write any instrument changes
			if note.instrument != current_instrument and note.instrument != None:
				current_instrument = note.instrument
				out.append("@%s" % song.furnace_file.instruments[current_instrument].name)
			semitone_offset = song.furnace_file.instruments[current_instrument].semitone_offset if current_instrument != None else 0

			# Write any volume changes
			if (current_volume == None or convert_volume(note.volume) != current_volume) and note.volume != None:
				current_volume = convert_volume(note.volume)
				out.append("V%d" % current_volume)

			if note.note: # Seems that any note without 03xx on it stops portamento
				portamento_speed = None
			no_portamento_legato = False
			already_changed_timer = False

			# Effects
			for effect_type, effect_value in note.effects:
				if effect_type == 0x00: # Arpeggio
					if effect_value == 0:
						arpeggio_enabled = False
						if note.note == None and most_recent_note != None:
							note.note = most_recent_note
							apply_legato()
					else:
						arpeggio_enabled = True
						arpeggio_note1 = effect_value >> 4
						arpeggio_note2 = effect_value & 15
						if note.note == None and most_recent_note != None:
							note.note = most_recent_note
							apply_legato()
				elif effect_type in (0x01, 0x02): # Pitch slide up/down
					if effect_value == 0:
						pitch_slide_rate = None
					else:
						pitch_slide_rate = (effect_value / 32) if effect_type == 0x01 else (-effect_value / 32)
						if note.note == None and most_recent_note != None:
							note.note = most_recent_note
							apply_legato()
				elif effect_type == 0x03: # Portamento
					# effect_value is an amount of pitch to add/subtract per Furnace tick, in 1/32 semitone units
					portamento_speed = effect_value
					if portamento_speed == 0:
						portamento_speed = None
					else:
						if note.note:
							portamento_from = previous_most_recent_note
							portamento_target = note.note
				elif effect_type == 0x04: # Vibrato
					# Furnace seems to have a 64-entry sequence for vibrato, and every Furnace tick, it adds the speed number to the index for this
					if (effect_value & 0xF0 == 0) or (effect_value & 0x0F == 0):
						out.append("MP0")
					else:
						for check_effect in note.effects: # Make sure vibrato range gets applied even if it's in a later effect column
							if check_effect[0] == 0xE4: # Vibrato range
								vibrato_range = check_effect[1]
								break
						# MP<depth_in_cents>, <quarter_wavelength_in_ticks> [, delay_in_ticks]
						vibrato_speed = effect_value >> 4
						vibrato_depth = effect_value & 15
						# 6.25 is 1/16*100
						depth_in_cents = round(vibrato_depth/15 * vibrato_range * 6.25)
						quarter_wavelength_in_ticks = furnace_ticks_to_tad_ticks(64/vibrato_speed/4, furnace_ticks_per_second, tad_timer_value)
						out.append("MP%d,%d" % (depth_in_cents, quarter_wavelength_in_ticks))
				elif effect_type in (0x0A, 0xFA, 0xF3, 0xF4): # Volume slide up/down
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
								too_far_amount = abs(total_slide_amount) - 255
								tad_ticks -= furnace_ticks_to_tad_ticks(too_far_amount / (slide_amount*2), furnace_ticks_per_second, tad_timer_value)
								total_slide_amount = 255 if slide_amount > 0 else -255
							if tad_ticks > 256:
								print("Volume slide at %d took too long" % row_index)
								tad_ticks = 256
							if slide_rows != None:
								out.append("Vs%s%d,%d" % ("+" if total_slide_amount>=0 else "", total_slide_amount, tad_ticks))
				elif effect_type in (0x09, 0x0F, 0xF0): # Speed change
					if ((row_index == 0 and tad_timer_value != song.tad_timer_value_at_start) or (row_index != 0 and tad_timer_value != speed_at_each_row[row_index-1][2])) and not already_changed_timer:
						out.append("T%d" % tad_timer_value)
						already_changed_timer = True
				elif effect_type == 0x11: # Toggle noise
					noise_mode = bool(effect_value)
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
					noise_frequency = effect_value & 31
					if not note.note and most_recent_note != NoteValue.OFF:
						apply_legato()
						note.note = most_recent_note
				elif effect_type == 0x80: # Set pan
					out.append("p%d" % int(effect_value / 255 * 128))
				elif effect_type == 0x83: # Pan slide
					if effect_value != 0:
						slide_amount = 0
						if effect_value & 0x0F == 0:
							slide_amount = -(effect_value >> 4)
						elif effect_value & 0xF0 == 0:
							slide_amount = effect_value

						if slide_amount:
							slide_rows = count_rows_until_note_with(any_effects_are_volume_slide)
							furnace_ticks = row_count_to_furnace_ticks(slide_rows)
							tad_ticks = row_count_to_tad_ticks(slide_rows)
							total_slide_amount = round(furnace_ticks * (slide_amount / 2))
							if abs(total_slide_amount) > 128:
								total_slide_amount = 128 if total_slide_amount > 0 else -128
							if tad_ticks > 256:
								print("Pan slide at %d took too long" % row_index)
								tad_ticks = 256
							if slide_rows != None:
								out.append("ps%s%d,%d" % ("+" if total_slide_amount>=0 else "", total_slide_amount, tad_ticks))
				elif effect_type == 0xE0: # Arpeggio speed
					arpeggio_speed = max(1, effect_value)
					if note.note == None and most_recent_note != None:
						note.note = most_recent_note
						apply_legato()
				elif effect_type in (0xE1, 0xE2): # Note slide up/down
					semitones = effect_value & 15
					portamento_speed = (effect_value >> 4) * 4
					no_portamento_legato = note.note != None

					if portamento_speed == 0:
						portamento_speed = None
					else:
						portamento_from = note.note if note.note != None else most_recent_note
						portamento_target = (portamento_from + semitones) if effect_type == 0xE1 else (portamento_from - semitones)
				elif effect_type == 0xE4: # Vibrato range
					vibrato_range = effect_value
				elif effect_type == 0xEA: # Legato
					legato = bool(effect_value)
				elif effect_type == 0xF8: # Single tick volume up
					out.append("V+%d" % (effect_value*2))
				elif effect_type == 0xF9: # Single tick volume down
					out.append("V-%d" % (effect_value*2))

			# Write the note itself
			next_note_is_actually_a_note = next_note and next_note.note and (next_note.note == NoteValue.OFF or (next_note.note >= NoteValue.FIRST and next_note.note <= NoteValue.LAST))
			if portamento_speed != None:
				if not no_portamento_legato:
					apply_legato()

				furnace_ticks_from_rows = row_count_to_furnace_ticks(duration)
				furnace_ticks_to_get_to_target = round(abs(portamento_target - portamento_from) * 32 / portamento_speed)
				if furnace_ticks_from_rows >= furnace_ticks_to_get_to_target:
					slide_tad_ticks = furnace_ticks_to_tad_ticks(furnace_ticks_to_get_to_target, furnace_ticks_per_second, tad_timer_value)
					leftover_tad_ticks = duration_in_tad_ticks - slide_tad_ticks
					note_start_name = note_name_from_index(portamento_from, semitone_offset)
					note_stop_name = note_name_from_index(portamento_target, semitone_offset)

					if slide_tad_ticks > 0:
						out.append("{%s %s}%%%d" % (note_start_name, note_stop_name, slide_tad_ticks))
						if leftover_tad_ticks:
							apply_legato()
							if next_note_is_actually_a_note:
								add_rest(leftover_tad_ticks)
							else:
								out.append("w%%%d" % (leftover_tad_ticks))
						elif not(next_note_is_actually_a_note):
							apply_legato()
					else: # If it's a zero tick portamento then just do the target note
						out.append("%s%%%d" % (note_stop_name, duration_in_tad_ticks))
						if not(next_note_is_actually_a_note):
							apply_legato()
					most_recent_note = portamento_target
				else:
					# Note enough time to finish the portamento - so how far does it actually get?
					slide_amount = round(furnace_ticks_from_rows / 32 * portamento_speed)
					if portamento_target < portamento_from:
						slide_amount = -slide_amount
					ending_note = portamento_from + slide_amount

					note_start_name = note_name_from_index(portamento_from, semitone_offset)
					note_stop_name = note_name_from_index(ending_note, semitone_offset)
					most_recent_note = ending_note

					out.append("{%s %s}%%%d%s" % (note_start_name, note_stop_name, duration_in_tad_ticks, "&" if not next_note_is_actually_a_note else ""))
			elif pitch_slide_rate != None and most_recent_note != None and note.note != NoteValue.OFF and most_recent_note != NoteValue.OFF:
				furnace_ticks = row_count_to_furnace_ticks(duration)
				total_slide_amount = round(furnace_ticks * pitch_slide_rate)

				if note.note == None or legato:
					apply_legato()
				starting_note = note.note if note.note != None else most_recent_note
				ending_note = min(NoteValue.LAST_VALID_TAD, max(NoteValue.FIRST_VALID_TAD, starting_note + total_slide_amount))
				note_start_name = note_name_from_index(starting_note, semitone_offset)
				note_stop_name = note_name_from_index(ending_note, semitone_offset)
				most_recent_note = ending_note

				out.append("{%s %s}%%%d" % (note_start_name, note_stop_name, duration_in_tad_ticks))
			elif (note.note == None or note.note == NoteValue.OFF) and next_note_is_actually_a_note: # The next non-empty row is either a note cut or a note
				add_rest(duration_in_tad_ticks)
			elif note.note != None and note.note >= NoteValue.FIRST and note.note <= NoteValue.LAST:
				if legato:
					apply_legato()
				if arpeggio_enabled:
					out.append("{{%s %s %s}}%%%d,%%%d" % (note_name_from_index(note.note, semitone_offset), note_name_from_index(note.note + arpeggio_note1, semitone_offset), note_name_from_index(note.note + arpeggio_note2, semitone_offset), duration_in_tad_ticks, math.ceil(max(1, arpeggio_speed * (tad_ticks_per_row / furnace_ticks_per_row))) ))
				else:
					if noise_mode:
						note_name = "N%d," % noise_frequency
					else:
						note_name = note_name_from_index(note.note, semitone_offset)
					if not next_note or next_note.note != None:
						out.append("%s%%%d" % (note_name, duration_in_tad_ticks))
					else:
						out.append("%s%%%d&" % (note_name, duration_in_tad_ticks))
			else:
				out.append("w%%%d" % duration_in_tad_ticks)
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

		groove_mode = len(song.speed_pattern) > 1
		multiple_groove_patterns = self.furnace_file.groove_patterns != []

		if groove_mode:
			tad_timer_value, tad_ticks_per_row = find_timer_and_multipliers_for_speed_pattern(self.ticks_per_second, self.speed_pattern)
		else:
			tad_timer_value, tad_ticks_per_row = find_timer_and_multiplier_for_tempo_and_speed(self.ticks_per_second, self.speed1)
			tad_ticks_per_row = [tad_ticks_per_row]

		out += "#Timer %d\n" % tad_timer_value
		self.tad_timer_value_at_start = tad_timer_value

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
		speed_pattern_index = 0
		new_order = True
		current_ticks_per_second = song.ticks_per_second
		current_speed_pattern = song.speed_pattern
		need_to_remake_tad_ticks_per_row = False

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
					elif effect_type == 0x09: # Set ticks-per-row (speed 1) - or change groove pattern
						if multiple_groove_patterns:
							if effect_value < len(self.furnace_file.groove_patterns) and current_speed_pattern != self.furnace_file.groove_patterns[effect_value]:
								current_speed_pattern = self.furnace_file.groove_patterns[effect_value]
								speed_pattern_index = 0
								need_to_remake_tad_ticks_per_row = True
						elif current_speed_pattern[0] != effect_value:
							current_speed_pattern[0] = effect_value
							need_to_remake_tad_ticks_per_row = True
					elif effect_type == 0x0F: # Set ticks-per-row (speed 2)
						if not multiple_groove_patterns and song.speed_pattern[-1] != effect_value:
							song.speed_pattern[-1] = effect_value
							need_to_remake_tad_ticks_per_row = True
					elif effect_type == 0xF0: # Set BPM
						current_ticks_per_second = effect_value / 2.5
						need_to_remake_tad_ticks_per_row = True
			if need_to_remake_tad_ticks_per_row:
				if groove_mode:
					tad_timer_value, tad_ticks_per_row = find_timer_and_multipliers_for_speed_pattern(self.ticks_per_second, current_speed_pattern)
				else:
					tad_timer_value, tad_ticks_per_row = find_timer_and_multiplier_for_tempo_and_speed(self.ticks_per_second, current_speed_pattern[0])
					tad_ticks_per_row = [tad_ticks_per_row]
				need_to_remake_tad_ticks_per_row = False
			speed_at_each_row.append( (current_ticks_per_second, current_speed_pattern[speed_pattern_index % len(current_speed_pattern)], tad_timer_value, tad_ticks_per_row[speed_pattern_index % len(tad_ticks_per_row)]) )
			speed_pattern_index += 1
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
				out += k + " " + " ".join(v).replace("%0 r%", "%") + "\n"

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

# -------------------------------------------------------------------
parser = argparse.ArgumentParser(prog='fur2tad', description='Converts Furnace files to Terrific Audio Driver MML')
parser.add_argument('filename')
parser.add_argument('--auto-timer-mode', type=str) # Options: low_error lowest_error
parser.add_argument('--timer-override', action='extend', nargs="+", type=str) # Format: bpm,speed=tad timer rate, tad ticks
parser.add_argument('--ignore-arp-macro', action='store_true')
args = parser.parse_args()

auto_timer_mode = (args.auto_timer_mode or "low_error").lower()
if auto_timer_mode not in ("low_error", "lowest_error"):
	sys.exit("Invalid --auto-timer-mode setting:" % auto_timer_mode)

if args.timer_override != None:
	for timer_override_string in args.timer_override:
		timer_override_split = timer_override_string.split("=")
		assert len(timer_override_split) == 2
		timer_override_split_input  = timer_override_split[0].split(",")
		timer_override_split_output = timer_override_split[1].split(",")
		furnace_tempo = int(timer_override_split_input[0])
		furnace_speed = int(timer_override_split_input[1])
		if "." in timer_override_split_output[0]:
			tad_rate = int(round(float(timer_override_split_output[0]) / 0.125))
		else:
			tad_rate = int(timer_override_split_output[0])
		if tad_rate < 64 or tad_rate > 256:
			sys.exit("Invalid TAD timer rate in --timer-override: %s" % timer_override_string)
		tad_ticks = int(timer_override_split_output[1])
		
		cached_timer_and_multiplier[(furnace_tempo/2.5, furnace_speed)] = (tad_rate, tad_ticks)

f = FurnaceFile(args.filename)
for song in f.songs:
	print(song.convert_to_tad())
	print()
