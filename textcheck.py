"""Checks on review text beyond the English word list of better_profanity:

- Russian and Azerbaijani swearing, written in Cyrillic or in Latin letters ("suka", "gijdillax"),
  with stretched letters ("suuuka"), digits for letters ("bl9t", "p1zda") or split letters ("s.u.k.a").
- Reviews must be in English, so other scripts and transliterated Russian or Azerbaijani are refused.
"""
import re
import unicodedata

# Characters people swap in to dodge filters, and Azerbaijani letters folded to plain Latin.
LOOKALIKES = str.maketrans({
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '6': 'b', '7': 't', '8': 'b', '9': 'ya',
    '@': 'a', '$': 's', '!': 'i', '|': 'i',
    'ə': 'e', 'ı': 'i', 'ö': 'o', 'ü': 'u', 'ş': 'sh', 'ç': 'ch', 'ğ': 'g', 'ё': 'е',
})
WORD = re.compile(r'[^\W_]+')
REPEATS = re.compile(r'(.)\1+')
# Single letters split by dots, spaces or dashes: "s.u.k.a", "s u k a".
SPLIT_LETTERS = re.compile(r'\b(?:\w[\s.*_-]){2,}\w\b')

# A word is rude when, with repeated letters squeezed ("suuka" -> "suka"), it starts with one of these.
RUDE_PREFIXES = (
    # Russian in Latin letters
    'blya', 'blia', 'blja', 'pizd', 'pisd', 'ebat', 'yebat', 'ebal', 'yebal', 'eban', 'yeban',
    'yoban', 'ioban', 'nahui', 'nahuy', 'mudak', 'mudil', 'zalup', 'ublyud', 'ublud', 'gandon',
    'pidor', 'pidar', 'pidr', 'shluh', 'shlyuh', 'dolboe', 'dolbayo', 'dalbayo', 'huesos', 'huil',
    'xuy', 'xui', 'khui', 'khuy', 'suchk', 'sucka', 'otsos', 'uebok', 'ueban',
    # Azerbaijani in Latin letters
    'gijdil', 'gicdil', 'qehbe', 'gehbe', 'qahba', 'gahba', 'kahpe', 'sikdir', 'siker', 'sikib',
    'sikil', 'sikis', 'amcig', 'amciq', 'amcik', 'amjig', 'gotver', 'qotver', 'qanciq', 'ganciq',
    'gancig', 'qancig', 'oqras', 'ogras', 'itogl', 'peyse', 'orospu', 'pezeveng',
    # Russian in Cyrillic
    'бля', 'пизд', 'пезд', 'хуй', 'хуе', 'хуя', 'хуи', 'ебат', 'ебал', 'ебан', 'ёбан', 'ебл', 'нахуй',
    'нахер', 'мудак', 'мудил', 'залуп', 'ублюд', 'гандон', 'пидор', 'пидар', 'пидр', 'шлюх', 'долбое',
    'долбаё', 'сучк', 'отсос', 'уебок', 'уёбок', 'уебан',
    # Azerbaijani in Cyrillic
    'гиждил', 'гиждыл', 'гыждыл', 'гиджил', 'гичдил', 'гехбе', 'гахба', 'гёхбе', 'сикдир', 'сикер',
    'сикиб', 'амджыг', 'амчыг', 'амджиг', 'гётвер', 'гетвер', 'ганджыг', 'ограш', 'итоглу', 'пейсер',
)
# Short words that would hit innocent words as prefixes ("sik" in "sikh"), so they must match whole.
RUDE_WORDS = {
    'suka', 'suki', 'hui', 'huy', 'huya', 'huyu', 'blyat', 'blyad', 'bliat', 'bljad', 'mraz', 'tvar',
    'urod', 'debil', 'chmo', 'govno', 'gavno', 'dermo', 'sosi', 'sik', 'sikim', 'nahu', 'eblan',
    'сука', 'суки', 'хер', 'мразь', 'тварь', 'урод', 'дебил', 'чмо', 'говно', 'дерьмо', 'соси', 'сик',
    'сиким',
}


def _fold(text):
    return text.lower().translate(LOOKALIKES)


def _squeeze(word):
    return REPEATS.sub(r'\1', _fold(word))


def has_rude_words(text):
    """Russian or Azerbaijani swearing in either alphabet, including stretched and leetspeak spellings."""
    joined = SPLIT_LETTERS.sub(lambda m: re.sub(r'[\s.*_-]', '', m.group()), text)
    for word in WORD.findall(_fold(joined)):
        squeezed = REPEATS.sub(r'\1', word)
        if word in RUDE_WORDS or squeezed in RUDE_WORDS or squeezed.startswith(RUDE_PREFIXES):
            return True
    return False


# Short English words that carry most English sentences. Words that are also everyday transliterated
# Russian or Azerbaijani ("a", "i", "on", "no", "to", "da", "ne", "bu", "o") are left out on purpose.
ENGLISH_WORDS = set('''
the be is are was were been being am has have had do does did will would can could should may might
must shall and or but if then than so because as of in at by for with about from into over after
before under between through during without he she they we you me him her them us his hers their our
your my mine its this that these those there here what which who whom whose when where why how all
any some each every most more less very really much many few not only also just too still even
good great bad nice best better worse worst well hard easy fair clear helpful boring interesting
class classes course courses lecture lectures exam exams grade grades grading teacher professor prof
teaches teaching explains explained homework assignment assignments student students recommend
recommended take took learn learned learnt get gets got give gives gave make makes made like liked
love loved know knows think thinks feel felt want need one two lot lots time always never sometimes
often people subject material quiz quizzes project projects midterm final office hours
'''.split())

# Common words of Russian or Azerbaijani written in Latin letters ("ochen", "prepod", "cox", "muellim").
FOREIGN_MARKERS = set('''
ochen ocen prepod prepodavatel horosho khorosho xorosho horoshiy khoroshiy xoroshiy normalno chto shto
eto kak tak vse vsyo vsem ili esli mne menya emu ego yego bil byl bila bilo bylo prosto mojno mozhno
nado nuzhno dazhe tozhe uje uzhe sovsem kogda potomu zachem pochemu tolko voobshe luchshe silno
ponyatno obyasnyaet ocenki ocenka cox chox yaxsi yaxshi yahshi muellim muallim mellim deyil yox yoxdu
vardi amma ile cunki chunki gozel gozal pis cetin chetin asan dersi ders dersler imtahan qiymet
qiymetler bilmir anladir izah tovsiye hec hech hamisi hamisa heqiqeten
'''.split()) - ENGLISH_WORDS

ENGLISH_ONLY_ERROR = 'Please write your review in English. Reviews in other languages are not accepted.'


def is_english(text):
    """True for text written in English. Other scripts (Cyrillic, Arabic...) and Russian or Azerbaijani
    typed in Latin letters are refused. A name with accents ("Rəşad") and course codes are fine."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    if any('LATIN' not in unicodedata.name(c, '') for c in letters):
        return False
    # Azerbaijani letters in a name or two are fine; whole sentences of them are not.
    accented = sum(1 for c in letters if not c.isascii())
    if accented > max(5, len(letters) // 10):
        return False

    words = [w for w in WORD.findall(text.lower()) if w.isalpha()]
    english = sum(1 for w in words if w in ENGLISH_WORDS)
    foreign = sum(1 for w in words if w in FOREIGN_MARKERS or _squeeze(w) in FOREIGN_MARKERS)
    if foreign >= 2 and foreign >= english:
        return False
    # A real English sentence of six or more words almost always has some of the common words above.
    if len(words) >= 6 and english < max(1, len(words) * 0.12):
        return False
    return True
