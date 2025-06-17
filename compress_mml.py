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

LOOP_PASSES = 3
MAX_LOOP_INSTRUCTIONS = 30

def add_loops(input):
	out = []

	start_loop_index = 0
	while start_loop_index < len(input):
		if input[start_loop_index] == "[" or input[start_loop_index].startswith("]"):
			out.append(input[start_loop_index])
			start_loop_index += 1
			continue

		# Determine the best loop that can go here
		best_loop_size    = None
		best_loop_repeats = None # amount of repeats, not the amount of loop iterations
		best_covered_size = None # best_loop_size * (best_loop_repeats+1)
		for loop_size in range(2, MAX_LOOP_INSTRUCTIONS+1):
			this_loop_data = input[start_loop_index:start_loop_index+loop_size]
			if this_loop_data[-1].startswith("]"):
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
				if try_index > len(input):
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

def compress_mml(mml):
	for _ in range(LOOP_PASSES):
		mml = add_loops(mml)
	return mml
