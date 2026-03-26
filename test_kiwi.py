from kiwipiepy import Kiwi

kiwi = Kiwi()
texts = [
    "1,000",
    "3.14",
    "2024.03.26.",
    "세종대왕은 1397년에 태어났다.",
    "전화번호는 010-1234-5678입니다."
]

for t in texts:
    print(f"Text: {t}")
    tokens = kiwi.tokenize(t)
    for tok in tokens:
        print(f"  {tok.form} / {tok.tag}")
    print("-" * 20)
