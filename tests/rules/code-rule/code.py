def handler(filename):
    with open(filename, encoding="utf-8") as f:
        content = f.read()

    content = content.replace("pariatur", "FOO").replace("velit", "FOO")
    if not content.endswith("\n"):
        content += "\n"
    content += "this is an addition\n"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
