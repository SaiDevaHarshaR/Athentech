
def normalize_amount(text):
    text = str(text)

    # TODO 1: Remove the rupee symbol.
    text = text.replace("₹","")

    # TODO 2: Remove commas.
    text = text.replace(",","")

    return text.strip()


def test_indian_currency():
    actual = "₹1,25,000"
    expected = 125000

    # TODO 3: Compare normalized actual
    # with normalized expected.
    assert actual == expected


def test_plain_number():
    actual = "125000"
    expected = 125000

    # TODO 4: Compare both values.
    assert actual == expected
