"""Builds data/biomehanika/questions.json. In Q(...) the FIRST answer is the correct one;
answers are then shuffled deterministically and the index stored in correct_answer (0-3)."""

import json
import random
import sys
from pathlib import Path

CATEGORIES = [
    ("zgodovina", "Zgodovinski razvoj biomehanike"),
    ("osnove", "Fizikalne osnove biomehanike in mehanike"),
    ("sklepi", "Biomehanika sklepov"),
    ("elastomehanika", "Elastomehanika tkiv"),
    ("kinetika", "Kinetične veličine in njihovo merjenje"),
    ("diagnostika", "Biomehanska diagnostika in analiza gibov"),
    ("registracija", "Registracija gibanja in kvantitativna analiza gibanja"),
    ("termoregulacija", "Osnove termoregulacije med fizično obremenitvijo"),
    ("misice", "Biomehanika mišic"),
    ("emg", "Kineziološka elektromiografija (EMG) in analiza signalov"),
    ("mreze", "Anatomske in funkcionalne mreže nevromuskularnega sistema"),
]
QS = []


def Q(cat, text, answers, points=1, image=""):
    assert len(answers) == 4 and len(set(answers)) == 4, text
    QS.append((cat, text, answers, points, image))


# ---------- Zgodovina ----------
Q(
    "zgodovina",
    "Kdo velja za očeta (začetnika) biomehanike?",
    ["Giovanni Alfonso Borelli", "Leonardo da Vinci", "Isaac Newton", "Gaston Carlet"],
)
Q(
    "zgodovina",
    "Kako je naslov Aristotelovega dela o gibanju živali, katerega naslov si je pozneje izposodil tudi Borelli?",
    [
        "De Motu Animalium",
        "De humani corporis fabrica",
        "Philosophiæ Naturalis Principia Mathematica",
        "Biomechanics and Motor Control of Human Movement",
    ],
)
Q(
    "zgodovina",
    "Katero delo je napisal Andreas Vesalius (1514–1564)?",
    [
        "De humani corporis fabrica",
        "De Motu Animalium",
        "Philosophiæ Naturalis Principia Mathematica",
        "Basic Biomechanics",
    ],
)
Q(
    "zgodovina",
    "Kdo je razvil čevelj s tremi tlačnimi pretvorniki v podplatu in naredil prvi posnetek sile reakcije podlage?",
    ["Gaston Carlet", "Étienne-Jules Marey", "Otto Fischer", "Jules Amar"],
)
Q(
    "zgodovina",
    "Kdo sta izvedla prvo 3D analizo hoje?",
    [
        "Wilhelm Braune in Otto Fischer",
        "Étienne-Jules Marey in Eadweard Muybridge",
        "Gage in Perry",
        "Basmajian in Winter",
    ],
)
Q(
    "zgodovina",
    "Kaj sta Étienne-Jules Marey in Eadweard Muybridge prva uporabila za analizo gibanja?",
    [
        "Visokohitrostno filmsko snemanje",
        "Trikomponentno pritiskovno ploščo",
        "Površinsko elektromiografijo",
        "Inercialne senzorje (IMU)",
    ],
)
Q(
    "zgodovina",
    "Po čem je znan Jules Amar (1879–1935)?",
    [
        "Po 3-komponentni pritiskovni plošči in rehabilitaciji vojnih poškodovancev",
        "Po prvi kameri, ki je na eno sliko postavila več posnetkov s časovnim zamikom",
        "Po zakonih gibanja, objavljenih leta 1687",
        "Po prvi analizi možganskih omrežij",
    ],
)
Q(
    "zgodovina",
    "S katerim področjem je v računalniški dobi povezan Basmajian?",
    [
        "Z elektromiografijo (EMG) in razumevanjem mišične funkcije",
        "Z razvojem videoprocesorjev za zajem gibanja",
        "Z vključevanjem analize hoje v ortopedske operacije",
        "Z odkritjem zlatega reza v človeškem telesu",
    ],
)
Q(
    "zgodovina",
    "Katera ugotovitev je značilna za Borellijevo delo?",
    [
        "Mišice delujejo preko mehanskih vzvodov, sklepi so vrtišča, mišične sile ustvarjajo navor",
        "Gibanje je treba opisovati brez upoštevanja sil",
        "Mišica lahko kost tudi potiska, ne le vleče",
        "Biomehanski procesi so v osnovi neizmerljivi",
    ],
)

# ---------- Fizikalne osnove ----------
Q(
    "osnove",
    "Katera trditev o biomehaniki NE DRŽI?",
    [
        "Biomehanika se ukvarja izključno s preučevanjem mehanskih principov v človeškem telesu.",
        "Biomehanika je aplikacija principov mehanike na žive strukture.",
        "V področje biomehanike spada tudi preučevanje delovanja lokomotornega sistema.",
        "Biomehanika preučuje mehanske dejavnike, ki vplivajo na telo v mirovanju in v gibanju.",
    ],
)
Q(
    "osnove",
    "Kaj preučuje kinematika?",
    [
        "Gibanje telesa brez preučevanja sil, ki ga povzročajo",
        "Sile, ki povzročajo gibanje",
        "Telo v stanju ravnovesja",
        "Deformacije tkiv pod obremenitvijo",
    ],
)
Q(
    "osnove",
    "Kaj preučuje kinetika (dinamika)?",
    [
        "Gibanje skupaj s silami, ki ga povzročajo",
        "Le geometrijo gibanja (lego, hitrost, pospešek)",
        "Izključno telesa v mirovanju",
        "Termoregulacijo med obremenitvijo",
    ],
)
Q(
    "osnove",
    "Kaj je značilno za kvantitativno analizo gibanja?",
    [
        "Komponente gibanja štejemo in merimo (numerično)",
        "Komponente gibanja le poimenujemo in ocenimo opisno",
        "Upoštevamo samo sile, ne pa gibanja",
        "Uporabljamo jo samo za telesa v mirovanju",
    ],
)
Q(
    "osnove",
    "Kateri Newtonov zakon pravi: če je vsota vseh zunanjih sil na telo enaka nič, telo miruje ali se giblje premo enakomerno?",
    [
        "1. Newtonov zakon (zakon o vztrajnosti)",
        "2. Newtonov zakon",
        "3. Newtonov zakon (akcija – reakcija)",
        "Zakon o ohranitvi gibalne količine",
    ],
)
Q(
    "osnove",
    "Ko stojimo, delujemo na tla s silo teže, tla pa na nas z enako veliko silo v nasprotni smeri. Kateri zakon to opisuje?",
    ["3. Newtonov zakon", "1. Newtonov zakon", "2. Newtonov zakon", "Hookov zakon"],
)
Q(
    "osnove",
    "Kako imenujemo zunanjo silo, ki NI usmerjena skozi težišče telesa, in kaj povzroči?",
    [
        "Ekscentrična sila; spremeni linearno in kotno gibanje",
        "Centrična sila; spremeni le linearno gibanje",
        "Par sil; spremeni le linearno gibanje",
        "Centrična sila; spremeni le kotno gibanje",
    ],
)
Q(
    "osnove",
    "Kaj povzroči par sil (dve nasprotno enaki sili z različnima premicama delovanja)?",
    [
        "Samo spremembo kotnega gibanja (vrtenje)",
        "Samo spremembo linearnega gibanja",
        "Spremembo linearnega in kotnega gibanja",
        "Nobene spremembe gibanja",
    ],
)
Q(
    "osnove",
    r"Mišica deluje s silo 600 N, pravokotna ročica sile glede na os sklepa je 5 cm. Kolikšen navor ustvari ($M = F \cdot r$)?",
    ["30 N m", "120 N m", "3000 N m", "12 N m"],
    2,
)
Q(
    "osnove",
    "Zakaj se nagnemo vstran, ko v eni roki nosimo težko breme?",
    [
        "Da skupno težišče ostane nad podporno ploskvijo in zmanjšamo navor bremena",
        "Da povečamo ročico bremena",
        "Da zmanjšamo maso bremena",
        "Ker se tako poveča trenje med podplati in tlemi",
    ],
)

# ---------- Biomehanika sklepov ----------
Q(
    "sklepi",
    "Slika prikazuje vzvod, pri katerem mišična sila deluje med vrtiščem in bremenom. Za kateri razred vzvoda gre?",
    [
        "Vzvod 3. razreda",
        "Vzvod 1. razreda",
        "Vzvod 2. razreda",
        "To ni vzvod, ker ni ravnovesja",
    ],
    1,
    "images/vzvod.png",
)
Q(
    "sklepi",
    "Kaj velja za večino vzvodov mišica–kost v človeškem telesu?",
    [
        "So 3. razreda, njihova mehanska prednost je manjša od 1",
        "So 2. razreda, njihova mehanska prednost je večja od 1",
        "So 1. razreda, njihova mehanska prednost je vedno enaka 1",
        "So 3. razreda, mišična sila je zato manjša od sile bremena",
    ],
)
Q(
    "sklepi",
    "Zakaj so mišice pripete tako blizu sklepov?",
    [
        "Majhno skrčenje mišice povzroči velik in hiter gib okončine",
        "Ker tako mišica potrebuje manj sile",
        "Ker se tako zmanjša obremenitev sklepa",
        "Ker se tako zmanjša obseg gibanja in poveča stabilnost",
    ],
)
Q(
    "sklepi",
    "Podlaket je vodoravna, nadlaket navpična (slika). Biceps je pripet 4 cm od komolca, masa podlakti je 1,5 kg (težišče 15 cm od komolca), v dlani je utež 5 kg (35 cm od komolca). Približno kolikšna je sila bicepsa? ($g = 9{,}81$ m/s²)",
    ["≈ 484 N", "≈ 66 N", "≈ 429 N", "≈ 1940 N"],
    2,
    "images/podlaket_biceps.png",
)
Q(
    "sklepi",
    "Športnik z maso 80 kg stoji na prstih ene noge. Vodoravna razdalja med prsti in gležnjem je 13 cm, med gležnjem in prijemališčem Ahilove tetive 3 cm. Približno kolikšna je sila v mečni mišici?",
    ["≈ 3,4 kN", "≈ 0,8 kN", "≈ 0,18 kN", "≈ 10,2 kN"],
    2,
)
Q(
    "sklepi",
    "V poenostavljeni shemi ramenskega sklepa je deltoidna mišica pripeta 12 cm od sklepa pod kotom 15° glede na nadlahtnico. Iztegnjena roka ima maso 3,5 kg, težišče je 30 cm od sklepa. Približno kolikšna je sila v deltoidni mišici?",
    ["≈ 330 N", "≈ 86 N", "≈ 34 N", "≈ 89 N"],
    2,
)
Q(
    "sklepi",
    "Kateri del ramenskega sklepnega kompleksa NI pravi sklep, temveč prostor med prsnim košem in lopatico?",
    [
        "Skapulotorakalni sklep",
        "Glenohumeralni sklep",
        "Sternoklavikularni sklep",
        "Akromioklavikularni sklep",
    ],
)
Q(
    "sklepi",
    "Kateri sklep je najbolj prosto gibljiv sklep v človeškem telesu?",
    [
        "Glenohumeralni sklep",
        "Kolenski sklep",
        "Sternoklavikularni sklep",
        "Korakoklavikularni sklep",
    ],
)
Q(
    "sklepi",
    "Mišično silo lahko razstavimo na komponento, pravokotno na kost, in komponento, vzporedno s kostjo. Katera komponenta povzroči vrtenje kosti okoli sklepa?",
    [
        "Rotacijska (pravokotna na kost)",
        "Dislokacijska (vzporedna s kostjo, stran od sklepa)",
        "Stabilizacijska (vzporedna s kostjo, proti sklepu)",
        "Obe vzporedni komponenti skupaj",
    ],
)
Q(
    "sklepi",
    "Kdaj je telo bolj stabilno?",
    [
        "Ko ima večjo podporno ploskev in nižje težišče",
        "Ko ima manjšo podporno ploskev in višje težišče",
        "Ko ima večjo podporno ploskev in višje težišče",
        "Stabilnost ni odvisna od lege težišča",
    ],
)

# ---------- Elastomehanika ----------
Q(
    "elastomehanika",
    "Kako je definirana mehanska napetost in v kateri enoti jo merimo?",
    [
        "$\\sigma = F/S$, enota Pa (N/m²)",
        "$\\sigma = F \\cdot S$, enota N m",
        "$\\sigma = \\Delta L / L$, brez enote",
        "$\\sigma = m \\cdot a$, enota N",
    ],
)
Q(
    "elastomehanika",
    "Na kost s prečnim presekom 5 cm² deluje tlačna sila 1000 N. Kolikšna je mehanska napetost?",
    ["2 MPa", "200 Pa", "5 kPa", "0,2 MPa"],
    2,
)
Q(
    "elastomehanika",
    "Nadlahtnica dolžine 20 cm se pod obremenitvijo skrči za 0,1 mm. Kolikšen je relativni raztezek?",
    [
        "$5 \\cdot 10^{-4}$ (0,05 %)",
        "$5 \\cdot 10^{-3}$ (0,5 %)",
        "$2 \\cdot 10^{-3}$ (0,2 %)",
        "0,1 mm",
    ],
    2,
)
Q(
    "elastomehanika",
    "Graf prikazuje napetost v nadlahtnici v odvisnosti od relativnega raztezka. Do približno katere napetosti velja območje elastičnosti?",
    ["≈ 85 MPa", "≈ 120 MPa", "≈ 40 MPa", "≈ 140 MPa"],
    1,
    "images/napetost_raztezek.png",
)
Q(
    "elastomehanika",
    "Iz grafa ocenite: za koliko se lahko raztegne 20 cm dolga nadlahtnica, preden pride do zloma?",
    ["≈ 2,8 mm", "≈ 0,28 mm", "≈ 1,0 mm", "≈ 28 mm"],
    2,
    "images/napetost_raztezek.png",
)
Q(
    "elastomehanika",
    "Kaj se zgodi, ko obremenitev preseže mejo elastičnosti (mejo plastičnosti)?",
    [
        "Del deformacije ostane trajen (plastična deformacija)",
        "Struktura se vedno vrne v prvotno obliko",
        "Takoj pride do zloma kosti",
        "Modul elastičnosti se poveča",
    ],
)
Q(
    "elastomehanika",
    "Kakšna obremenitev nastane, ko se konstrukcija zasuka okoli svoje vzdolžne osi (npr. zlom golenice pri smučanju, ko je stopalo fiksirano)?",
    ["Torzijska", "Strižna", "Upogibna", "Kompresijska"],
)
Q(
    "elastomehanika",
    "Sila, ki na kolenski sklep deluje vzporedno s tibialno ploskvijo, povzroča ...",
    [
        "strižno obremenitev",
        "raztezno obremenitev",
        "torzijsko obremenitev",
        "kompresijsko obremenitev",
    ],
)
Q(
    "elastomehanika",
    "Kako imenujemo poškodbo, ki nastane zaradi ponavljajočega se delovanja razmeroma majhnih sil?",
    [
        "Kronična (stresna) poškodba, mehanizem je mikrotravma",
        "Akutna poškodba, mehanizem je makrotravma",
        "Akutna poškodba, mehanizem je mikrotravma",
        "Kronična poškodba, mehanizem je makrotravma",
    ],
)
Q(
    "elastomehanika",
    "Katere celice usmerjajo procese modeliranja in remodeliranja kosti glede na mehansko obremenitev?",
    ["Osteociti", "Hondrociti", "Miociti", "Fibroblasti"],
)
Q(
    "elastomehanika",
    "Pri katerih skupinah je bila ugotovljena izguba kostne mase zaradi premajhne mehanske obremenitve?",
    [
        "Pri bolnikih, priklenjenih na posteljo, in pri astronavtih",
        "Pri dvigovalcih uteži",
        "Pri teniških igralcih v dominantni roki",
        "Pri tekačih na dolge proge",
    ],
)
Q(
    "elastomehanika",
    "Kaj je značilno za viskoelastična biološka tkiva (tetive, ligamente, hrustanec)?",
    [
        "Pri hitrejšem raztezanju se pri enakem raztezku pojavi večja sila",
        "Njihov odziv ni odvisen od hitrosti deformacije",
        "Energije ne shranjujejo, samo jo disipirajo",
        "Pri počasnem raztezanju so bolj toga kot pri hitrem",
    ],
)
Q(
    "elastomehanika",
    "Vretence je glede na navpičnico nagnjeno za 30° in podpira težo zgornjega dela trupa $W$. Kolikšna strižna sila deluje nanj?",
    ["$W/2$", "$W$", "$\\frac{\\sqrt{3}}{2} W$", "$2W$"],
    2,
)
Q(
    "elastomehanika",
    "Zaradi slabe drže se nagib vretenca poveča s 30° na 40°. Za približno koliko se poveča strižna obremenitev?",
    ["Za približno 30 %", "Za približno 10 %", "Za približno 60 %", "Ne spremeni se"],
    2,
)

# ---------- Kinetične veličine ----------
Q(
    "kinetika",
    "Čemu je enak sunek sile?",
    [
        "Spremembi gibalne količine",
        "Spremembi kinetične energije",
        "Opravljenemu delu",
        "Zmnožku sile in poti",
    ],
)
Q(
    "kinetika",
    "Graf prikazuje silo pri udarcu boksarja v 90 kg težko vrečo. S kolikšno hitrostjo se premakne vreča po udarcu?",
    ["≈ 0,89 m/s", "≈ 1,78 m/s", "≈ 8,9 m/s", "≈ 0,44 m/s"],
    2,
    "images/udarec_sila_cas.png",
)
Q(
    "kinetika",
    "Kaj pri analizi teka pomeni hitrost obremenjevanja (loading rate, LR)?",
    [
        "Spremembo sile reakcije podlage na časovno enoto ($\\Delta F/\\Delta t$)",
        "Največjo silo reakcije podlage",
        "Čas stika stopala s podlago",
        "Hitrost teka v m/s",
    ],
)
Q(
    "kinetika",
    "S katero napravo neposredno merimo silo reakcije podlage pri hoji ali skoku?",
    [
        "S tenziometrijsko (silovno) ploščo",
        "Z goniometrom",
        "Z elektromiografom",
        "S pletizmografom",
    ],
)
Q(
    "kinetika",
    "Kako se po raziskavi (Scientific Reports, 2018) spremeni udarna obremenitev pri teku v močno blaženih copatih?",
    [
        "Poveča se togost noge in udarna obremenitev se poveča",
        "Udarna obremenitev se izrazito zmanjša",
        "Udarna obremenitev se ne spremeni",
        "Spremeni se le hitrost teka",
    ],
)
Q(
    "kinetika",
    "Koliko so pri pristanku po navpičnem skoku (meritve košarkarjev) v povprečju znašale sile reakcije podlage?",
    [
        "Več kot 5-kratnik telesne teže",
        "Približno 1-kratnik telesne teže",
        "Približno polovico telesne teže",
        "Približno 2-kratnik telesne teže",
    ],
)
Q(
    "kinetika",
    "Oseba z maso 70 kg se povzpne za 1500 m višinske razlike. Mehansko delo (dvig težišča) predstavlja 20 % celotne porabljene energije. Približno koliko energije porabi?",
    ["≈ 5,2 MJ", "≈ 1,0 MJ", "≈ 0,2 MJ", "≈ 21 MJ"],
    2,
)
Q(
    "kinetika",
    "Kako je definirana moč?",
    [
        "Moč je delo, opravljeno v časovni enoti ($P = A/t$)",
        "Moč je sila na enoto površine",
        "Moč je zmnožek sile in časa",
        "Moč je sprememba gibalne količine",
    ],
)
Q(
    "kinetika",
    "Kolikšen je tipični izkoristek pretvorbe metabolne energije v mehansko delo pri človeku?",
    ["≈ 20–30 %", "≈ 2–3 %", "≈ 50–60 %", "≈ 90 %"],
)

# ---------- Diagnostika / antropometrija ----------
Q(
    "diagnostika",
    "Kaj je antropometrija?",
    [
        "Merjenje človeškega telesa in njegovih mer",
        "Merjenje električne aktivnosti mišic",
        "Merjenje porabe kisika",
        "Merjenje sil reakcije podlage",
    ],
)
Q(
    "diagnostika",
    "Za kakšen namen je Alphonse Bertillon prvotno uvedel antropometrične meritve?",
    [
        "Za lažjo identifikacijo kriminalcev",
        "Za načrtovanje letalskih kabin",
        "Za izbor vrhunskih športnikov",
        "Za izdelavo ortopedskih pripomočkov",
    ],
)
Q(
    "diagnostika",
    "Koliko približno znaša zlato razmerje?",
    ["1,618", "3,142", "2,718", "1,414"],
)
Q(
    "diagnostika",
    "Katera vrstica podaja prvih sedem števil Fibonaccijevega zaporedja?",
    [
        "0, 1, 1, 2, 3, 5, 8",
        "1, 2, 3, 5, 7, 11, 13",
        "0, 1, 2, 4, 8, 16, 32",
        "1, 1, 2, 4, 6, 10, 16",
    ],
)
Q(
    "diagnostika",
    "Prazna plošča dolžine 1,7 m pritiska na obe podpori s silama po 25 N. Ko se nanjo uleže človek, sta sili $F_1 = 340$ N in $F_2 = 280$ N. Kako daleč od podpore 1 je težišče človeka?",
    ["≈ 0,76 m", "≈ 0,94 m", "≈ 0,85 m", "≈ 0,55 m"],
    2,
)
Q(
    "diagnostika",
    "Katero tkivo ima med naštetimi najmanjšo gostoto?",
    [
        "Maščoba (≈ 0,9 kg/l)",
        "Mišično tkivo (≈ 1,0 kg/l)",
        "Lobanja (≈ 1,8 kg/l)",
        "Vsa imajo enako gostoto",
    ],
)
Q(
    "diagnostika",
    "Na čem temelji merjenje telesnega volumna s pletizmografijo (Bod Pod)?",
    [
        "Na spremembah tlaka v zaprti komori (Boylov zakon)",
        "Na izpodrinjenem volumnu vode pri potopitvi",
        "Na rentgenski absorpciji (DEXA)",
        "Na električni prevodnosti tkiv",
    ],
)
Q(
    "diagnostika",
    "Zakaj imajo šprinterji relativno dolge, a ne čim daljše noge?",
    [
        "Predolge noge znižajo frekvenco korakov; hitrost = dolžina koraka × frekvenca koraka",
        "Ker daljše noge vedno pomenijo večjo maso mišic",
        "Ker dolžina nog na hitrost ne vpliva",
        "Ker dolge noge povečajo upor zraka",
    ],
)
Q(
    "diagnostika",
    "Katera antropometrična značilnost je pri vrhunskih plavalcih (npr. M. Phelps) prednost?",
    [
        "Relativno dolg trup, krajše noge in dolge roke",
        "Relativno kratek trup in zelo dolge noge",
        "Visoko težišče in kratke roke",
        "Majhna telesna višina in kratke roke",
    ],
)
Q(
    "diagnostika",
    "Katere metode razločijo maščobno, mišično in kostno tkivo in veljajo za najsodobnejši pristop?",
    [
        "DEXA, CT in MRI",
        "Hidrostatično tehtanje",
        "Goniometrija",
        "Antropometrični meter",
    ],
)

# ---------- Registracija gibanja ----------
Q(
    "registracija",
    "Graf prikazuje vertikalno gibanje težišča med hojo. Kolikšna je amplituda gibanja (razlika med najvišjo in najnižjo lego)?",
    ["≈ 5 cm", "≈ 2,5 cm", "≈ 10 cm", "≈ 100 cm"],
    1,
    "images/tezisce_hoja.png",
)
Q(
    "registracija",
    "Iz istega grafa gibanja težišča določite kadenco hoje (en nihaj težišča ustreza enemu koraku).",
    ["120 korakov/min", "60 korakov/min", "240 korakov/min", "90 korakov/min"],
    2,
    "images/tezisce_hoja.png",
)
Q(
    "registracija",
    "Dolžina koraka je 0,7 m, en korak traja 0,5 s (graf). S kolikšno hitrostjo hodi oseba?",
    ["1,4 m/s", "0,35 m/s", "0,7 m/s", "2,8 m/s"],
    2,
    "images/tezisce_hoja.png",
)
Q(
    "registracija",
    "Graf prikazuje višino glave med navpičnim skokom. Koliko časa je bila oseba v zraku?",
    ["≈ 0,5 s", "≈ 0,3 s", "≈ 1,0 s", "≈ 1,8 s"],
    1,
    "images/navpicni_skok.png",
)
Q(
    "registracija",
    "Oseba je bila pri navpičnem skoku v zraku 0,5 s (graf). Kolikšna je bila vzletna hitrost težišča?",
    ["≈ 2,45 m/s", "≈ 4,9 m/s", "≈ 1,2 m/s", "≈ 9,8 m/s"],
    2,
    "images/navpicni_skok.png",
)
Q(
    "registracija",
    "Za približno koliko se je oseba na grafu počepnila pred odrivom?",
    ["≈ 30 cm", "≈ 15 cm", "≈ 45 cm", "≈ 60 cm"],
    1,
    "images/navpicni_skok.png",
)
Q(
    "registracija",
    "Kaj merimo z goniometrom?",
    [
        "Kote v sklepih",
        "Sile reakcije podlage",
        "Električno aktivnost mišic",
        "Porabo kisika",
    ],
)
Q(
    "registracija",
    "Kaj omogoča inverzna dinamika?",
    [
        "Izračun sklepnih sil in navorov iz izmerjene kinematike in zunanjih sil",
        "Neposredno merjenje mišičnih sil z elektrodami",
        "Merjenje telesne gostote",
        "Filtriranje signalov v frekvenčnem prostoru",
    ],
)
Q(
    "registracija",
    "Katere tehnologije spadajo med nosljive senzorje za analizo gibanja?",
    [
        "IMU, pametni vložki in pametna oblačila",
        "MRI in CT",
        "Hidrostatična tehtnica in Bod Pod",
        "Silovne plošče, vgrajene v tla",
    ],
)
Q(
    "registracija",
    "Kaj je ključna ideja analize gibanja, ki sta jo uvedla Braune in Fischer?",
    [
        "Telo obravnavamo kot sistem povezanih segmentov s težišči in masnimi lastnostmi",
        "Gibanje opisujemo izključno kvalitativno",
        "Merimo le električno aktivnost mišic",
        "Telo obravnavamo kot eno samo togo telo brez segmentov",
    ],
)

# ---------- Termoregulacija in energija ----------
Q(
    "termoregulacija",
    "Kolikšen delež dnevne energijske porabe v povprečju predstavlja bazalni metabolizem?",
    ["50–70 %", "5–10 %", "15–20 %", "90–95 %"],
)
Q(
    "termoregulacija",
    "Kolikšna je tipična mehanska učinkovitost skeletne mišice?",
    ["≈ 20 % (preostanek je toplota)", "≈ 80 %", "≈ 50 %", "≈ 5 %"],
)
Q(
    "termoregulacija",
    "Kaj pomeni kratica EPOC?",
    [
        "Povečana poraba kisika po vadbi",
        "Največja poraba kisika med vadbo",
        "Prag kopičenja laktata v krvi",
        "Bazalni metabolizem v mirovanju",
    ],
)
Q(
    "termoregulacija",
    "Kateri energijski sistem prevladuje pri zelo kratkih, eksplozivnih obremenitvah (prvih nekaj sekund, npr. skok)?",
    [
        "ATP–CP sistem (ATP in kreatinfosfat)",
        "Lipoliza (oksidacija maščob)",
        "Jetrna glikogenoliza",
        "Glukoneogeneza",
    ],
)
Q(
    "termoregulacija",
    "Kateri proces postane prevladujoč približno med 10. in 60. sekundo intenzivne vadbe in proizvaja laktat?",
    ["Anaerobna glikoliza", "Lipoliza", "Glukoneogeneza", "Razpad kreatinfosfata"],
)
Q(
    "termoregulacija",
    "Pri kolikšni intenzivnosti se laktatni prag običajno pojavi pri netreniranih osebah?",
    [
        "Pri 50–60 % VO₂max",
        "Pri 65–80 % VO₂max",
        "Pri 90–100 % VO₂max",
        "Pri 20–30 % VO₂max",
    ],
)
Q(
    "termoregulacija",
    "Kaj pomeni OBLA?",
    [
        "Intenzivnost, pri kateri koncentracija laktata v krvi doseže 4 mM",
        "Največjo porabo kisika",
        "Porabo kisika po vadbi",
        "Bazalni metabolizem",
    ],
)
Q(
    "termoregulacija",
    "V kateri enoti izražamo relativno porabo kisika VO₂, ki je primerljiva med osebami?",
    ["mL/kg/min", "L/min", "kcal/dan", "W"],
)
Q(
    "termoregulacija",
    "Kateri del možganov je glavni center za uravnavanje telesne temperature?",
    [
        "Sprednji del hipotalamusa",
        "Mali možgani",
        "Podaljšana hrbtenjača",
        "Okcipitalni reženj",
    ],
)
Q(
    "termoregulacija",
    "Kateri mehanizem je pri sedeči goli osebi odgovoren za približno 60 % toplotnih izgub?",
    ["Sevanje (radiacija)", "Kondukcija s predmeti", "Izhlapevanje znoja", "Dihanje"],
)
Q(
    "termoregulacija",
    "Kaj se zgodi s kožnimi žilami, ko je telesu prehladno?",
    [
        "Skrčijo se (vazokonstrikcija)",
        "Razširijo se (vazodilatacija)",
        "Ostanejo nespremenjene",
        "Poveča se izločanje znoja",
    ],
)
Q(
    "termoregulacija",
    "Pod katero temperaturo jedra govorimo o hipotermiji?",
    ["Pod 35 °C", "Pod 37 °C", "Pod 30 °C", "Pod 25 °C"],
)
Q(
    "termoregulacija",
    "Koliko toplote telo odda z izhlapevanjem 1 g vode (znoja)?",
    ["≈ 2,4 kJ (0,58 kcal)", "≈ 4,2 kJ", "≈ 0,24 kJ", "≈ 24 kJ"],
)
Q(
    "termoregulacija",
    "Zakaj se pri bolnikih po srčnem zastoju uporablja terapevtska hipotermija?",
    [
        "Ker zniža porabo kisika v možganih in upočasni nastajanje prostih radikalov",
        "Ker poveča srčni utrip",
        "Ker pospeši metabolizem v možganih",
        "Ker poveča pretok krvi skozi kožo",
    ],
)

# ---------- Biomehanika mišic ----------
Q(
    "misice",
    "Katera vedenjska lastnost je edinstvena za mišično tkivo?",
    [
        "Sposobnost aktivnega razvijanja napetosti",
        "Elastičnost",
        "Raztegljivost",
        "Vzdražnost",
    ],
)
Q(
    "misice",
    "Katere mišice uravnava avtonomni živčni sistem in delujejo nezavedno v stenah notranjih organov?",
    [
        "Gladke mišice",
        "Skeletne (progaste) mišice",
        "Vse mišice okončin",
        "Mišice, ki so pripete na kosti",
    ],
)
Q(
    "misice",
    "Kje se nahaja serijska elastična komponenta mišice (SEC), ki shranjuje elastično energijo?",
    ["V tetivah", "V mišičnih membranah", "V kostnem mozgu", "V motoričnih nevronih"],
)
Q(
    "misice",
    "Mišična vlakna pernate mišice ustvarijo silo $F_f = 100$ N in s kito oklepajo kot 60° (slika). Kolikšna je sila v kiti $F_t$?",
    ["50 N", "87 N", "100 N", "200 N"],
    2,
    "images/pernata_misica.png",
)
Q(
    "misice",
    "Mišična vlakna pernate mišice ustvarijo silo 60 N in s kito oklepajo kot 30°. Kaj velja za silo v kiti?",
    [
        "Zagotovo je manjša od 60 N",
        "Enaka je 60 N",
        "Zagotovo je večja od 60 N",
        "Enaka je 0 N",
    ],
)
Q(
    "misice",
    "Kaj sestavlja motorično enoto?",
    [
        "En motorični nevron in vsa mišična vlakna, ki jih oživčuje",
        "En motorični nevron in eno mišično vlakno",
        "Več motoričnih nevronov in eno mišično vlakno",
        "Več motoričnih nevronov in več mišic",
    ],
)
Q(
    "misice",
    "Kakšen je pri šprinterjih na 100 m tipični delež hitrih (FT, tip II) mišičnih vlaken?",
    ["Približno 75 %", "Približno 25 %", "Približno 50 %", "Približno 10 %"],
)
Q(
    "misice",
    "Kaj je glavni mehanizem povečanja mišične mase pri človeku po vadbi za moč?",
    [
        "Hipertrofija – povečanje premera vlaken",
        "Hiperplazija – povečanje števila vlaken",
        "Povečanje števila motoričnih nevronov",
        "Povečanje deleža maščobe v mišici",
    ],
)
Q(
    "misice",
    "Kdaj se po težki vadbi običajno pojavi zakasnela mišična bolečina (DOMS) in katera vrsta kontrakcij jo najbolj povzroča?",
    [
        "12–48 ur po vadbi; ekscentrične kontrakcije",
        "Med vadbo; koncentrične kontrakcije",
        "Takoj po vadbi; izometrične kontrakcije",
        "Po enem tednu; koncentrične kontrakcije",
    ],
)
Q(
    "misice",
    "Kakšno je krčenje, pri katerem se mišica med razvijanjem napetosti podaljšuje (npr. spuščanje bremena)?",
    ["Ekscentrično", "Koncentrično", "Izometrično", "Tetanično"],
)
Q(
    "misice",
    "Kako imenujemo krčenje, pri katerem mišica razvija napetost, njena dolžina pa se ne spreminja?",
    ["Izometrično", "Koncentrično", "Ekscentrično", "Izotonično"],
)
Q(
    "misice",
    "Slika prikazuje odvisnost sile in moči mišice od hitrosti krčenja. Pri kateri točki je mehanska moč največja?",
    [
        "B (pri približno tretjini največje hitrosti)",
        "A (pri zelo majhni hitrosti)",
        "C (pri skoraj največji hitrosti)",
        "Pri hitrosti nič (izometrično)",
    ],
    1,
    "images/sila_hitrost_moc.png",
)
Q(
    "misice",
    "Kaj je tetanus v mišični fiziologiji?",
    [
        "Trajna največja napetost vlakna zaradi hitro ponavljajočih se dražljajev",
        "Popolna sprostitev mišice",
        "Ekscentrično krčenje pod velikim bremenom",
        "Zakasnela bolečina v mišicah",
    ],
)
Q(
    "misice",
    "Katera mišica se skrči pri patelarnem (pogačičnem) refleksu?",
    [
        "Štiriglava stegenska mišica (kvadriceps)",
        "Dvoglava stegenska mišica",
        "Mečna mišica",
        "Prednja golenska mišica",
    ],
)

# ---------- EMG in analiza signalov ----------
Q(
    "emg",
    "Kaj je najmanjša enota živčno-mišičnega sistema, ki jo lahko nadzoruje centralni živčni sistem?",
    ["Motorična enota", "Sarkomera", "Mišični snop", "Senzorični nevron"],
)
Q(
    "emg",
    "Kako se med akcijskim potencialom spremeni membranski potencial mišične celice?",
    [
        "Z okoli −80 mV na okoli +30 mV (depolarizacija)",
        "Z okoli +30 mV na okoli −80 mV",
        "Z 0 mV na +120 mV",
        "Ostane nespremenjen",
    ],
)
Q(
    "emg",
    "Kaj pomeni elektromehanska sklopitev?",
    [
        "Sprostitev kalcijevih ionov sproži skrajšanje kontraktilnih elementov",
        "Pretvorba EMG signala v digitalno obliko",
        "Povezava elektrod z ojačevalnikom",
        "Prenos signala po senzoričnem živcu",
    ],
)
Q(
    "emg",
    "Signal je vsota treh sinusov: $x = \\sin(2\\pi t) + \\sin(10\\pi t) + \\sin(0{,}5\\pi t)$. Pri katerih frekvencah so vrhovi v njegovem spektru (slika)?",
    [
        "0,25 Hz, 1 Hz in 5 Hz",
        "0,5 Hz, 2 Hz in 10 Hz",
        "π Hz, 2π Hz in 10π Hz",
        "1 Hz, 2 Hz in 5 Hz",
    ],
    2,
    "images/spekter.png",
)
Q(
    "emg",
    "Kateri filter iz signala s spektra na sliki ohrani samo komponento pri 1 Hz?",
    [
        "Pasovni filter, ki prepušča 0,5–1,5 Hz",
        "Nizkoprepustni filter z mejo 0,5 Hz",
        "Visokoprepustni filter z mejo 0,5 Hz",
        "Visokoprepustni filter z mejo 2 Hz",
    ],
    2,
    "images/spekter.png",
)
Q(
    "emg",
    "Kaj odstrani visokoprepustni filter?",
    [
        "Počasne komponente (npr. lezenje bazne linije)",
        "Hitre komponente (npr. šum)",
        "Vse komponente razen ene",
        "Nič, le ojača signal",
    ],
)
Q(
    "emg",
    "Kaj naredi nizkoprepustni filter?",
    [
        "Prepusti počasne komponente, odstrani hitre (šum)",
        "Prepusti hitre komponente, odstrani počasne",
        "Odstrani amplitudo signala",
        "Poveča frekvenco vzorčenja",
    ],
)
Q(
    "emg",
    "Zakaj pri EMG signalih običajno uporabimo pasovno filtracijo?",
    [
        "Spodnja meja odreže počasne bazalne variacije, zgornja meja šum",
        "Ker poveča amplitudo signala",
        "Ker iz signala izloči vse frekvence",
        "Ker spremeni signal iz časovnega v prostorski prostor",
    ],
)
Q(
    "emg",
    "Kako deluje glajenje s povprečenjem sosednjih točk (NN averaging)?",
    [
        "Vrednost točke nadomestimo s povprečjem sosednjih točk v izbranem oknu",
        "Odstranimo vsako drugo točko",
        "Točke razvrstimo po velikosti",
        "Signal pomnožimo s konstanto",
    ],
)
Q(
    "emg",
    "Za kaj se elektromiografija NE uporablja?",
    [
        "Za neposredno merjenje telesne gostote",
        "Za ocenjevanje mišične zmogljivosti",
        "Za optimizacijo treninga in rehabilitacije",
        "Za študije mišičnih odzivov v ergonomiji",
    ],
)

# ---------- Mreže ----------
Q(
    "mreze",
    "Iz katerih osnovnih gradnikov je sestavljeno kompleksno omrežje?",
    [
        "Iz vozlov in povezav",
        "Iz signalov in filtrov",
        "Iz sil in navorov",
        "Iz motoričnih enot in tetiv",
    ],
)
Q(
    "mreze",
    "Kaj je matrika sosednosti anatomskega omrežja z N kostmi?",
    [
        "Kvadratna matrika N × N, ki zapisuje, katere kosti so povezane",
        "Seznam N mas kosti",
        "Matrika 2 × N s koordinatami kosti",
        "Spekter EMG signala N mišic",
    ],
)
Q(
    "mreze",
    "Kdaj se v anatomskem omrežju dve kosti štejeta za povezani?",
    [
        "Ko si delita stično površino (šiv, sinhondroza, sinovijski sklep)",
        "Ko ju oživčuje isti živec",
        "Ko imata enako maso",
        "Ko ležita v isti ravnini",
    ],
)
Q(
    "mreze",
    "Kako iz meritev možganske aktivnosti (npr. fMRI) dobimo funkcionalno omrežje?",
    [
        "Izračunamo korelacijsko matriko sinhronosti regij in jo binariziramo s pragom",
        "Preštejemo kosti lobanje",
        "Izmerimo silo reakcije podlage",
        "Izračunamo gostoto možganovine",
    ],
)
Q(
    "mreze",
    "Na koliko modulov je analiza razdelila anatomsko omrežje skeletnih mišic (Kerkman et al., 2018)?",
    [
        "Na 5 modulov: desna roka, leva roka, trup, desna noga, leva noga",
        "Na 2 modula: zgornji in spodnji del telesa",
        "Na 8 modulov lobanje",
        "Omrežje ni modularno",
    ],
)
Q(
    "mreze",
    "Kaj je MoBI (Mobile Brain/Body Imaging)?",
    [
        "Sočasno merjenje možganske aktivnosti in gibanja telesa v naravnih pogojih",
        "Slikanje kosti z magnetno resonanco",
        "Merjenje sil reakcije podlage med tekom",
        "Metoda za merjenje telesne gostote",
    ],
)
Q(
    "mreze",
    "Kaj velja za fNIRS v primerjavi z EEG pri MoBI meritvah?",
    [
        "Je manj občutljiv na artefakte gibanja, a ima slabšo časovno ločljivost",
        "Ima boljšo časovno ločljivost (milisekunde)",
        "Meri neposredno električne potenciale na lasišču",
        "Meri globoke možganske strukture",
    ],
)
Q(
    "mreze",
    "S čim se ukvarja mrežna fiziologija (network physiology)?",
    [
        "Z interakcijami med organi in fiziološkimi sistemi kot celostno mrežo",
        "Z delovanjem posameznega organa ločeno od ostalih",
        "Z gradnjo računalniških omrežij v bolnišnicah",
        "Izključno z anatomijo kosti",
    ],
)
Q(
    "mreze",
    "Kaj so pokazale raziskave o treningu hoje pri bolnikih po možganski kapi?",
    [
        "Večje izboljšanje povezanosti možganskega omrežja je spremljal večji napredek pri hoji",
        "Možganska povezanost se med rehabilitacijo ne spreminja",
        "Napredek pri hoji je obratno sorazmeren z izboljšanjem povezanosti",
        "Trening hoje vpliva le na mišice, ne pa na možgane",
    ],
)
Q(
    "mreze",
    "Od česa je po Boonstri in sodelavcih (2015) odvisna povezanost mišic v omrežju, izračunanem iz EMG?",
    [
        "Od podobnosti frekvenčnih spektrov EMG signalov",
        "Od mase posameznih mišic",
        "Od dolžine tetiv",
        "Od števila kosti, na katere je mišica pripeta",
    ],
)


def build(out_dir: Path) -> None:
    keys = {key for key, _ in CATEGORIES}
    questions = []
    for i, (cat, text, answers, points, image) in enumerate(QS):
        assert cat in keys, cat
        if image:
            assert (out_dir / image).is_file(), image
        order = list(range(4))
        random.Random(f"biomehanika-{i}").shuffle(order)
        shuffled = [answers[j] for j in order]
        questions.append(
            {
                "category": cat,
                "question_text": text,
                "answers": shuffled,
                "correct_answer": order.index(0),
                "points": points,
                "image": image,
            }
        )
    data = {
        "subject": {
            "name": "Biomehanika",
            "description": "Biomehanika – Fizioterapija, 2. letnik (študijsko leto 2025/26). Vprašanja pripravljena po predavanjih.",
        },
        "categories": [{"key": k, "name": n} for k, n in CATEGORIES],
        "questions": questions,
    }
    (out_dir / "questions.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    from collections import Counter

    print(len(questions), "questions;", Counter(q["category"] for q in questions))
    print(
        "correct index distribution:", Counter(q["correct_answer"] for q in questions)
    )


build(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent)
