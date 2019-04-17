import pstats

with open("prof/combined.txt", "w") as f:
    stats = pstats.Stats("prof/combined.prof", stream=f)
    stats.print_stats()
