def count_word(words, target):
    count = 0
    for w in words:
        if w == target:
            count += 1
    return count


words = ["apples", "pears", "apples", "pears", "apples"]
print(f"apples={count_word(words, 'apples')} pears={count_word(words, 'pears')}")