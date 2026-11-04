from tamlil.hebrew import fold, index_text, match, query_tokens, tokens, unfold, variants


def forms(word):
    return [unfold(f) for f in variants(fold(word))]


def test_niqqud_and_cantillation_are_stripped():
    assert unfold(fold("וְהָרָקִיעַ")) == "והרקיע"
    assert unfold(fold("בְּרֵאשִׁ֖ית")) == "בראשית"


def test_a_pointed_word_stays_one_token():
    assert [t.raw for t in tokens("וְהָרָקִיעַ שֶׁבַּשָּׁמַיִם")] == ["וְהָרָקִיעַ", "שֶׁבַּשָּׁמַיִם"]


def test_prefixes_are_peeled_up_to_three():
    assert forms("והרקיע") == ["והרקיע", "הרקיע", "רקיע"]
    assert forms("שבשמים") == ["שבשמים", "בשמים", "שמים", "מים"]
    assert forms("לרקיע") == ["לרקיע", "רקיע"]


def test_at_least_three_letters_remain():
    assert forms("משה") == ["משה"]
    assert forms("בית") == ["בית"]


def test_acronym_marks():
    assert fold("רמב״ם") == fold('רמב"ם') == fold("רמבם")


def test_maqaf_and_hyphen_split():
    assert [t.raw for t in tokens("ה-autoscaler של על־פני")] == ["autoscaler", "של", "על", "פני"]


def test_english_light_stem():
    assert fold("Rising") == "rising"
    assert variants("rising")[-1] == variants("rise")[-1] == variants("rises")[-1]
    assert variants("autoscaling")[-1] == variants("autoscaler")[-1]


def test_index_text_holds_forms_and_spellings():
    assert index_text("ויקרא אלהים לרקיע שמים").split() == [
        "ויקרא", "יקרא", "וקרא", "אלהימ", "אלהמ", "לרקיע", "רקיע", "לרקע", "רקע", "שמימ", "מימ", "שממ"]


def test_query_words_are_not_peeled():
    ranges, _, _ = match("והיא מבדיל בין מים למים", query_tokens("שמים"))
    assert ranges == []


def test_full_and_short_spellings_meet():
    _, why, _ = match("היה שמיים בראשית ברא אלוהים", query_tokens("שמים אלהים"))
    assert why == [["spelling", "שמיים"], ["spelling", "אלוהים"]]
    _, why, _ = match("ויקרא אלהים לרקיע שמים", query_tokens("אלוהים"))
    assert why == [["spelling", "אלהים"]]


def test_exact_outranks_form_outranks_spelling():
    q = query_tokens("שמים")
    exact = match("את השמים ואת הארץ", q)[2]
    assert match("ויקרא לרקיע שמים", q)[2] > match("היה שמיים", q)[2]
    assert exact > 0


def test_match_kinds():
    q = query_tokens("רקיע")
    ranges, why, score = match("ויקרא אלהים לרקיע שמים", q)
    assert [k for _, _, k in ranges] == ["form"]
    assert why == [["form", "ל+רקיע"]]
    ranges, why, _ = match("יהי רקיע בתוך המים", q)
    assert why == [["exact", ""]]


def test_query_with_niqqud_finds_plain_text():
    q = query_tokens("הָרָקִיעַ")
    ranges, _, _ = match("והרקיע הזה", q)
    assert ranges


def test_stop_words_dropped_unless_alone():
    assert [t.folded for t in query_tokens("sourdough starter not rising")] == ["sourdough", "starter", "rising"]
    assert [t.folded for t in query_tokens("not")] == ["not"]


def test_spelling_needs_only_added_vav_or_yod():
    assert match("אמר אליהם משה", query_tokens("אלהים"))[0] == []
    assert match("מי שעומד שם", query_tokens("עמודי"))[0] == []


def test_elokim_forms_meet_elohim():
    for said in ("ויאמר אלוקים יהי רקיע", "ברא אלקים", "אלוהים אמר"):
        assert match(said, query_tokens("אלהים"))[0], said
