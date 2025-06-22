import math

possible_timer_milliseconds = [_*0.125 for _ in range(64, 256+1)]
#print(possible_timer_milliseconds)

def tempo_to_milliseconds(tempo):
	return 1 / (tempo / 2.5) * 1000

def find_lowest_note_duration_error(tempo, furnace_ticks_per_row):
	milliseconds_per_tempo_tick = tempo_to_milliseconds(tempo)
	row_milliseconds = milliseconds_per_tempo_tick * furnace_ticks_per_row # Actual duration of each row

	lowest_error_timer     = None
	lowest_error_multiply  = None
	lowest_error_amount    = None
	for timer_option in possible_timer_milliseconds:
		fractional_part, integer_part = math.modf(row_milliseconds / timer_option)
		milliseconds_with_this_timer_option = timer_option * integer_part
		error = abs(row_milliseconds - milliseconds_with_this_timer_option)
		if lowest_error_amount == None or lowest_error_amount > error:
			lowest_error_amount   = error
			lowest_error_timer    = timer_option
			lowest_error_multiply = integer_part
	print("Speed %2d should take %10f ms; %9f ms * %2d = %10f ms | Error %8f ms" % (furnace_ticks_per_row, row_milliseconds, lowest_error_timer, lowest_error_multiply, lowest_error_timer * lowest_error_multiply, lowest_error_amount))

def find_multiple_options(tempo, furnace_ticks_per_row, show_best_per_multiplier=True):
	milliseconds_per_tempo_tick = tempo_to_milliseconds(tempo)
	actual_row_milliseconds = milliseconds_per_tempo_tick * furnace_ticks_per_row
	print("%d BPM at speed %d should take: %f" % (tempo, furnace_ticks_per_row, actual_row_milliseconds))

	low_error_options = {} # Indexed by multiplier
	for timer_option in possible_timer_milliseconds:
		for multiply in range(1, 60):
			milliseconds_with_this_timer_option = timer_option * multiply
			error = abs(actual_row_milliseconds - milliseconds_with_this_timer_option)
			if error < 2:
				if multiply not in low_error_options:
					low_error_options[multiply] = []
				low_error_options[multiply].append((timer_option, error))

	for multiply in sorted(low_error_options, reverse=True):
		for entry in sorted(low_error_options[multiply], key=lambda _:_[1]):
			timer_option, error = entry
			print("%9f ms * %2d = %10f ms | Error %8f ms" % (timer_option, multiply, timer_option * multiply, error))
			if show_best_per_multiplier:
				break

def test_fake_groove(tempo, speed1, speed2):
	milliseconds_per_tempo_tick = tempo_to_milliseconds(tempo)
	actual_row_milliseconds_speed1 = milliseconds_per_tempo_tick * speed1
	actual_row_milliseconds_speed2 = milliseconds_per_tempo_tick * speed2
	print("%d BPM at speed %d should take: %f ms" % (tempo, speed1, actual_row_milliseconds_speed1))
	print("%d BPM at speed %d should take: %f ms" % (tempo, speed2, actual_row_milliseconds_speed2))

	low_error_options = {} # Indexed by timer
	for timer_option in possible_timer_milliseconds:
		best_multiply_speed1 = None
		best_error_speed1    = None
		best_multiply_speed2 = None
		best_error_speed2    = None
		for multiply in range(1, 60):
			milliseconds_with_this_timer_option = timer_option * multiply
			error1 = abs(actual_row_milliseconds_speed1 - milliseconds_with_this_timer_option)
			error2 = abs(actual_row_milliseconds_speed2 - milliseconds_with_this_timer_option)
			if best_error_speed1 == None or error1 < best_error_speed1:
				best_multiply_speed1 = multiply
				best_error_speed1 = error1
			if best_error_speed2 == None or error2 < best_error_speed2:
				best_multiply_speed2 = multiply
				best_error_speed2 = error2
		combined_error = best_error_speed1 + best_error_speed2
		if best_error_speed1 < 2 and best_error_speed2 < 2:
			print("%9f ms * %2d = %10f ms | * %2d = %10f | Error %9f ms, %9f ms" % (timer_option, best_multiply_speed1, timer_option * best_multiply_speed1,best_multiply_speed2, timer_option * best_multiply_speed2, best_error_speed1, best_error_speed2))

"""
for tempo in range(40, 300+1, 10):
	print("BPM %d, or %f Hz" % (tempo, tempo/2.5))

	for furnace_ticks_per_row in range(1, 10+1):
		find_lowest_note_duration_error(tempo, furnace_ticks_per_row)
	print()
"""

"""
find_lowest_note_duration_error(150, 6)
find_multiple_options(150, 6)
"""

"""
for speed2 in range(2,7+1):
	#find_lowest_note_duration_error(150, 4)
	#find_lowest_note_duration_error(150, 6)
	test_fake_groove(150, 6, speed2)
"""
