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

# Loop optimization
LOOP_PASSES = 4
MAX_LOOP_INSTRUCTIONS = 35

# Subroutine optimization
MAX_SUBROUTINE_LENGTH = 30
MIN_SUBROUTINE_LENGTH = 4
subroutine_count = 0

def token_is_note(token):
	return token.startswith("o") or token.startswith("{")

def find_recently_used_instrument(sequence, index):
	while index > 0:
		if sequence[index].startswith("@"):
			return sequence[index]
		index -= 1
	return None

def find_recently_used_vibrato(sequence, index):
	while index > 0:
		if sequence[index].startswith("MP"):
			return sequence[index]
		index -= 1
	return None

def replace_with_loops(input):
	out = []

	start_loop_index = 0
	while start_loop_index < len(input):
		if input[start_loop_index] == "[" or input[start_loop_index].startswith("]") or input[start_loop_index] == "L":
			out.append(input[start_loop_index])
			start_loop_index += 1
			continue

		# Determine the best loop that can go here
		best_loop_size    = None
		best_loop_repeats = None # amount of repeats, not the amount of loop iterations
		best_covered_size = None # best_loop_size * (best_loop_repeats+1)
		for loop_size in range(2, MAX_LOOP_INSTRUCTIONS+1):
			this_loop_data = input[start_loop_index:start_loop_index+loop_size]
			if this_loop_data[-1] == "[" or this_loop_data[-1] == "L" or this_loop_data[-1].startswith("]"):
				break
			if len(this_loop_data) != loop_size:
				continue
			# Figure out how many times this loop can happen
			possible_loop_repeats = 1
			while True:
				possible_loop_data = input[start_loop_index+loop_size*possible_loop_repeats : start_loop_index+loop_size*(possible_loop_repeats+1)]
				if possible_loop_data != this_loop_data:
					possible_loop_repeats -= 1
					break
				possible_loop_repeats += 1
			# Bail if no loops were possible at all
			if possible_loop_repeats == 0:
				continue
			covered = loop_size * (possible_loop_repeats+1)
			if best_loop_size == None or covered > best_covered_size:
				best_loop_size = loop_size
				best_loop_repeats = possible_loop_repeats
				best_covered_size = covered

		# Is it worthwhile to put a loop here?
		if best_covered_size != None and best_covered_size > 3:
			out.append("[")
			this_loop_data = input[start_loop_index:start_loop_index+best_loop_size]
			this_loop_inserted_at = len(out)
			out.extend(this_loop_data)
			start_loop_index += best_covered_size			

			# Insert a colon if the instructions after the loop contain a portion of the start of the loop
			put_colon_at = 0
			while True:
				try_index = start_loop_index+put_colon_at
				if try_index >= len(input):
					break
				if input[try_index] != this_loop_data[put_colon_at]:
					break
				put_colon_at += 1
			if put_colon_at > 0:
				out.insert(this_loop_inserted_at + put_colon_at, ":")
				best_loop_repeats += 1
				start_loop_index += put_colon_at

			out.append("]%d" % (best_loop_repeats+1))
		else:
			out.append(input[start_loop_index])
			start_loop_index += 1
	return out

def replace_with_subroutines(channel, mml_sequences):
	global subroutine_count
	sequence = mml_sequences[channel]

	# Find where every token type is
	token_locations = {}
	for index, token in enumerate(sequence):
		if not token_is_note(token): # Notes only
			continue
		if token not in token_locations:
			token_locations[token] = []
		token_locations[token].append(index)

	# Go through every token
	index = 0
	while index < len(sequence) - MIN_SUBROUTINE_LENGTH:
		this_token = sequence[index]
		if not token_is_note(this_token): # Notes only
			index += 1
			continue
		max_size = min(MAX_SUBROUTINE_LENGTH, len(sequence)-index)

		# Which places to check for a match at
		check_locations = [_ for _ in token_locations[this_token] if _ >= (index+MIN_SUBROUTINE_LENGTH)]
		if not check_locations:
			index += 1
			continue

		# Build the sequence to compare against
		try_sequence = []
		loop_level = 0
		has_invalid_tokens = False
		for i in range(index, index+max_size):
			t = sequence[i]
			if t == "[":
				loop_level += 1
			elif t == ":" and loop_level <= 0:
				has_invalid_tokens = True
				break
			elif t.startswith("]"):
				loop_level -= 1
				if loop_level < 0:
					break
			elif t == "L":
				break
			try_sequence.append(t)
		# Trim any unfinished loops
		while loop_level:
			if try_sequence == []:
				break
			t = try_sequence.pop()
			if t == "[":
				loop_level -= 1
		if loop_level or len(try_sequence) < MIN_SUBROUTINE_LENGTH:
			index += 1
			continue

		while len(try_sequence) >= MIN_SUBROUTINE_LENGTH:
			sequence_size = len(try_sequence)
			match_at = []
			for try_at in check_locations:
				if sequence[try_at] != this_token:
					continue
				if sequence[try_at:try_at+sequence_size] == try_sequence:
					match_at.append(try_at)

			if match_at: # Matches found, so do the replacements
				subroutine_name = "!sub%d" % subroutine_count
				subroutine_count += 1

				# Find the most recently used instrument
				recently_used_instrument = find_recently_used_instrument(sequence, index)
				recently_used_vibrato    = find_recently_used_vibrato(sequence, index)
				prefix_subroutine_with = []
				if recently_used_instrument != None:
					prefix_subroutine_with.append("?" + recently_used_instrument)
				if recently_used_vibrato    != None and recently_used_vibrato != "MP0":
					prefix_subroutine_with.append(recently_used_vibrato)

				mml_sequences[subroutine_name] = prefix_subroutine_with + try_sequence

				instrument_switch_in_subroutine = find_recently_used_instrument(try_sequence, len(try_sequence)-1)
				vibrato_switch_in_subroutine    = find_recently_used_vibrato(try_sequence, len(try_sequence)-1)

				for i in range(sequence_size):
					replace_with = subroutine_name if i == 0 else "" # Replace removed tokens with placeholders to keep token_locations useful
					if i == 1 and instrument_switch_in_subroutine != recently_used_instrument and instrument_switch_in_subroutine != None:
						replace_with = instrument_switch_in_subroutine # Instrument switches in subroutines don't stick, so carry it into the main sequence
					elif i == 2 and vibrato_switch_in_subroutine != recently_used_vibrato and vibrato_switch_in_subroutine != None:
						replace_with = vibrato_switch_in_subroutine
					sequence[index+i] = replace_with
					for m in match_at:
						sequence[m+i] = replace_with
				break

			# Remove one token
			t = try_sequence.pop()
			if t.startswith("]"):
				loop_level = 1
				while loop_level:
					if len(try_sequence):
						t = try_sequence.pop()
					else:
						break
					if t == "[":
						loop_level -= 1
					elif t.startswith("]"):
						loop_level.pop()
						loop_level += 1
				if loop_level:
					break
		index += 1
	mml_sequences[channel] = [_ for _ in sequence if _] # Remove placeholders

def optimize_subroutines(mml_sequences):
	# TODO
	pass

def compress_mml(channel, mml_sequences, loop_compression, sub_compression):
	if loop_compression:
		# Find loops
		for _ in range(LOOP_PASSES):
			mml_sequences[channel] = replace_with_loops(mml_sequences[channel])
	if sub_compression:
		replace_with_subroutines(channel, mml_sequences)
		optimize_subroutines(mml_sequences)
