def handler(filename):
    with open(filename, encoding="utf-8") as f:
        lines = f.read().splitlines()
    sorted_unique = sorted(set(line for line in lines if line))
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_unique) + "\n")
